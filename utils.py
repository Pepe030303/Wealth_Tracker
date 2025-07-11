# 📄 utils.py

from datetime import datetime, timedelta
import logging
import yfinance as yf
import pandas as pd
import json
from redis import Redis

# 개선: Redis 연결을 외부에서 주입받아 사용
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

def set_to_redis_cache(key, value):
    if not redis_conn: return
    # 배당 정보는 자주 바뀌지 않으므로 6시간 캐시
    redis_conn.setex(key, timedelta(hours=6), json.dumps(value))


def calculate_dividend_metrics(holdings, price_data_map):
    dividend_metrics = {}
    for h in holdings:
        symbol = h.symbol.upper()
        cache_key = f"dividend_metrics:{symbol}"
        
        cached_data = get_from_redis_cache(cache_key)
        if cached_data:
            # 캐시된 DPS를 사용해 현재 보유량에 맞게 재계산
            annual_dps = cached_data.get('annual_dps', 0)
            if annual_dps > 0:
                current_price = price_data_map.get(symbol, {}).get('price')
                dividend_metrics[symbol] = {
                    'expected_annual_dividend': annual_dps * h.quantity,
                    'dividend_yield': (annual_dps / current_price) * 100 if current_price else 0
                }
            continue

        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            annual_dps = float(info.get('trailingAnnualDividendRate') or info.get('dividendRate') or 0)
            current_price = price_data_map.get(symbol, {}).get('price')

            if annual_dps == 0 and info.get('yield') and current_price:
                annual_dps = float(info['yield']) * current_price

            if annual_dps > 0:
                dividend_yield = (annual_dps / current_price) * 100 if current_price else 0
                dividend_metrics[symbol] = {
                    'expected_annual_dividend': annual_dps * h.quantity,
                    'dividend_yield': dividend_yield
                }
                # 캐시에 주당 배당금(DPS)만 저장하여 재사용
                set_to_redis_cache(cache_key, {'annual_dps': annual_dps})
        except Exception as e:
            logger.warning(f"({symbol}) 배당 지표 계산 실패: {e}")
            continue
            
    return dividend_metrics

def get_dividend_months(symbol):
    upper_symbol = symbol.upper()
    cache_key = f"dividend_months:{upper_symbol}"
    
    cached_data = get_from_redis_cache(cache_key)
    if cached_data: return cached_data

    try:
        ticker = yf.Ticker(upper_symbol)
        actions = ticker.actions
        if actions is not None and not actions.empty and 'Dividends' in actions.columns and actions['Dividends'].sum() > 0:
            ex_dividend_dates = actions[actions['Dividends'] > 0].index
            ex_dividend_dates_naive = ex_dividend_dates.tz_convert(None) if ex_dividend_dates.tz is not None else ex_dividend_dates
            
            one_year_ago = datetime.now() - timedelta(days=365)
            recent_ex_dates = ex_dividend_dates_naive[ex_dividend_dates_naive > pd.to_datetime(one_year_ago)]
            
            if not recent_ex_dates.empty:
                dividend_count_last_year = len(recent_ex_dates)
                paid_months = sorted(list(set(recent_ex_dates.month)))
                MONTH_NUMBER_TO_NAME = {1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'}
                month_names = [MONTH_NUMBER_TO_NAME.get(m, '') for m in paid_months]
                
                result = {"months": month_names, "count": dividend_count_last_year}
                set_to_redis_cache(cache_key, result)
                return result
    except Exception as e:
        logger.warning(f"({upper_symbol}) 배당 월 정보 조회 실패: {e}")

    result = {"months": [], "count": 0}
    set_to_redis_cache(cache_key, result)
    return result

def get_monthly_dividend_distribution(dividend_metrics):
    monthly_totals = [0] * 12
    month_map = {'Jan':0, 'Feb':1, 'Mar':2, 'Apr':3, 'May':4, 'Jun':5, 'Jul':6, 'Aug':7, 'Sep':8, 'Oct':9, 'Nov':10, 'Dec':11}
    for symbol, metrics in dividend_metrics.items():
        dividend_info = get_dividend_months(symbol)
        payout_months = dividend_info.get("months", [])
        payout_count = dividend_info.get("count", 0)
        if payout_months and payout_count > 0 and metrics.get('expected_annual_dividend'):
            amount_per_payout = metrics['expected_annual_dividend'] / payout_count
            for month_str in payout_months:
                if month_str in month_map:
                    monthly_totals[month_map[month_str]] += amount_per_payout
    return {'labels': [f"{i+1}월" for i in range(12)], 'data': [round(m, 2) for m in monthly_totals]}

def get_dividend_allocation_data(dividend_metrics):
    return [{'symbol': s, 'value': m['expected_annual_dividend']} for s, m in dividend_metrics.items() if m.get('expected_annual_dividend', 0) > 0]
