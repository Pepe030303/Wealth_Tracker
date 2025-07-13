# 📄 utils.py

from datetime import datetime, timedelta
import logging
import yfinance as yf
import pandas as pd
import json
from redis import Redis
from models import StockPrice

try:
    from app import conn as redis_conn
except ImportError:
    redis_conn = None
    logging.warning("Redis 연결을 가져오지 못했습니다. 캐싱이 비활성화됩니다.")

logger = logging.getLogger(__name__)

def get_from_redis_cache(key):
    if not redis_conn: return None
    cached = redis_conn.get(key)
    return json.loads(cached) if cached else None

def set_to_redis_cache(key, value, ttl_hours=6):
    if not redis_conn: return
    redis_conn.setex(key, timedelta(hours=ttl_hours), json.dumps(value))


def calculate_dividend_metrics(holdings, price_data_map):
    dividend_metrics = {}
    for h in holdings:
        symbol = h.symbol.upper()
        cache_key = f"dividend_metrics:{symbol}"
        
        annual_dps = 0
        cached_data = get_from_redis_cache(cache_key)

        if cached_data:
            annual_dps = cached_data.get('annual_dps', 0)
        else:
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info
                annual_dps = float(info.get('trailingAnnualDividendRate') or info.get('dividendRate') or 0)
                
                if annual_dps == 0 and info.get('yield'):
                    price_data = price_data_map.get(symbol)
                    current_price = 0
                    if isinstance(price_data, dict):
                        current_price = price_data.get('price')
                    elif hasattr(price_data, 'current_price'):
                        current_price = price_data.current_price
                    
                    if current_price:
                        annual_dps = float(info['yield']) * current_price

                if annual_dps > 0:
                    set_to_redis_cache(cache_key, {'annual_dps': annual_dps})
            except Exception as e:
                logger.warning(f"({symbol}) 배당 지표 계산 실패: {e}")
                continue

        if annual_dps > 0:
            price_data = price_data_map.get(symbol)
            current_price = 0
            if isinstance(price_data, dict):
                current_price = price_data.get('price')
            elif hasattr(price_data, 'current_price'): 
                current_price = price_data.current_price
            
            if not current_price:
                current_price = h.purchase_price

            dividend_yield = (annual_dps / current_price) * 100 if current_price else 0
            dividend_metrics[symbol] = {
                'expected_annual_dividend': annual_dps * h.quantity,
                'dividend_yield': dividend_yield,
                'dividend_per_share': annual_dps,
            }
            
    return dividend_metrics

# 🛠️ 개선: 함수명을 더 명확하게 변경하고, 상세 배당일과 주당 금액을 반환하도록 개선
def get_dividend_payout_schedule(symbol):
    """
    과거 1년간의 배당금 지급 내역(배당락일, 주당 배당금)을 조회.
    """
    upper_symbol = symbol.upper()
    cache_key = f"dividend_payout_schedule:{upper_symbol}"
    
    cached_data = get_from_redis_cache(cache_key)
    if cached_data: 
        return cached_data

    payouts = []
    try:
        ticker = yf.Ticker(upper_symbol)
        actions = ticker.actions
        if actions is not None and not actions.empty and 'Dividends' in actions.columns:
            dividends_data = actions[actions['Dividends'] > 0]
            if not dividends_data.empty:
                one_year_ago = datetime.now() - timedelta(days=365)
                # 타임존 정보가 있을 경우 제거
                if dividends_data.index.tz is not None:
                    dividends_data.index = dividends_data.index.tz_convert(None)
                
                recent_dividends = dividends_data[dividends_data.index > pd.to_datetime(one_year_ago)]
                for ex_date, row in recent_dividends.iterrows():
                    payouts.append({
                        'date': ex_date.strftime('%Y-%m-%d'),
                        'amount': row['Dividends']
                    })
    except Exception as e:
        logger.warning(f"({upper_symbol}) 배당 지급 일정 조회 실패: {e}")

    set_to_redis_cache(cache_key, payouts)
    return payouts

def get_dividend_allocation_data(dividend_metrics):
    return [{'symbol': s, 'value': m['expected_annual_dividend']} for s, m in dividend_metrics.items() if m.get('expected_annual_dividend', 0) > 0]
