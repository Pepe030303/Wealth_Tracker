# 📄 utils.py

from datetime import datetime, timedelta
import logging
import yfinance as yf
import pandas as pd
import json
from redis import Redis
from models import StockPrice
import requests # 🛠️ 예외 처리를 위해 임포트

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
        if cached_data := get_from_redis_cache(cache_key):
            annual_dps = cached_data.get('annual_dps', 0)
        else:
            try:
                info = yf.Ticker(symbol).info
                annual_dps = float(info.get('trailingAnnualDividendRate') or info.get('dividendRate') or 0)
                
                if annual_dps == 0 and info.get('yield'):
                    price_data = price_data_map.get(symbol)
                    current_price = price_data.get('price') if isinstance(price_data, dict) else (getattr(price_data, 'current_price', 0))
                    
                    if current_price:
                        annual_dps = float(info['yield']) * current_price

                if annual_dps > 0:
                    set_to_redis_cache(cache_key, {'annual_dps': annual_dps})
            # 🛠️ 예외 처리 강화: 네트워크, 데이터 파싱 등 구체적인 예외 처리
            except requests.exceptions.HTTPError as http_err:
                logger.warning(f"배당 지표 계산 실패 (HTTP 오류) ({symbol}): {http_err}")
                continue # 다음 종목으로
            except (KeyError, TypeError, ValueError) as e:
                logger.warning(f"배당 지표 파싱 오류 ({symbol}): {e}")
                continue
            except Exception as e:
                logger.error(f"배당 지표 계산 중 예상치 못한 오류 ({symbol}): {e}")
                continue

        if annual_dps > 0:
            price_data = price_data_map.get(symbol)
            current_price = price_data.get('price') if isinstance(price_data, dict) else (getattr(price_data, 'current_price', h.purchase_price))
            
            dividend_yield = (annual_dps / current_price) * 100 if current_price else 0
            dividend_metrics[symbol] = {
                'expected_annual_dividend': annual_dps * h.quantity,
                'dividend_yield': dividend_yield,
                'dividend_per_share': annual_dps,
            }
            
    return dividend_metrics

def get_dividend_payout_schedule(symbol):
    """
    과거 1년간의 배당금 지급 내역과 월 이름 목록을 함께 반환.
    """
    upper_symbol = symbol.upper()
    cache_key = f"dividend_payout_schedule:{upper_symbol}"
    
    if cached_data := get_from_redis_cache(cache_key): return cached_data

    payouts = []
    month_names = []
    try:
        actions = yf.Ticker(upper_symbol).actions
        if actions is not None and not actions.empty and 'Dividends' in actions.columns:
            dividends_data = actions[actions['Dividends'] > 0]
            if not dividends_data.empty:
                one_year_ago = datetime.now() - timedelta(days=365)
                if dividends_data.index.tz is not None:
                    dividends_data.index = dividends_data.index.tz_convert(None)
                
                recent_dividends = dividends_data[dividends_data.index > pd.to_datetime(one_year_ago)]
                for ex_date, row in recent_dividends.iterrows():
                    payouts.append({'date': ex_date.strftime('%Y-%m-%d'), 'amount': row['Dividends']})

                payout_months_num = sorted(list(set(datetime.strptime(p['date'], '%Y-%m-%d').month for p in payouts)))
                MONTH_MAP = {1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'}
                month_names = [MONTH_MAP.get(m) for m in payout_months_num if m in MONTH_MAP]
    # 🛠️ 예외 처리 강화: 네트워크, 데이터 파싱 등 구체적인 예외 처리
    except requests.exceptions.HTTPError as http_err:
        logger.warning(f"배당 지급 일정 조회 실패 (HTTP 오류) ({upper_symbol}): {http_err}")
    except (AttributeError, KeyError, TypeError) as e:
        logger.warning(f"배당 지급 일정 파싱 오류 ({upper_symbol}): {e}")
    except Exception as e:
        logger.error(f"배당 지급 일정 조회 중 예상치 못한 오류 ({upper_symbol}): {e}")

    result = {'payouts': payouts, 'months': month_names}
    set_to_redis_cache(cache_key, result)
    return result

def get_dividend_allocation_data(dividend_metrics):
    return [{'symbol': s, 'value': m['expected_annual_dividend']} for s, m in dividend_metrics.items() if m.get('expected_annual_dividend', 0) > 0]
