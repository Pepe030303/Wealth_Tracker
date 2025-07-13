# 📄 utils.py

from datetime import datetime, timedelta
import logging
import yfinance as yf
import pandas as pd
import json
import requests
from redis import Redis
from models import StockPrice
# 🛠️ 변경: Polygon.io API 키를 stock_api 모듈에서 가져옵니다.
from stock_api import POLYGON_API_KEY

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
        
        dividend_data = get_dividend_payout_schedule(symbol)
        payouts = dividend_data.get('payouts', [])
        
        if not payouts:
            continue

        # 🛠️ 개선: 최근 1년간 실제 지급된 배당금의 합으로 연간 배당금(annual_dps)을 계산하여 정확도 향상
        annual_dps = 0
        if payouts:
            one_year_ago = datetime.now() - timedelta(days=365)
            recent_payouts = [p for p in payouts if p.get('pay_date') and datetime.strptime(p['pay_date'], '%Y-%m-%d') > one_year_ago]
            
            if len(recent_payouts) > 0:
                annual_dps = sum(p['amount'] for p in recent_payouts)

        if annual_dps > 0:
            price_data = price_data_map.get(symbol)
            current_price = price_data.get('price') if price_data else h.purchase_price
            
            dividend_yield = (annual_dps / current_price) * 100 if current_price else 0
            dividend_metrics[symbol] = {
                'expected_annual_dividend': annual_dps * h.quantity,
                'dividend_yield': dividend_yield,
                'dividend_per_share': annual_dps,
            }
            
    return dividend_metrics

def get_dividend_payout_schedule(symbol):
    """
    [API 교체] Finnhub 대신 Polygon.io API를 사용하여 배당 정보를 조회합니다.
    이 API는 지급일, 배당락일 등 상세 정보를 제공합니다.
    """
    upper_symbol = symbol.upper()
    # 🛠️ 변경: 캐시 키를 Polygon.io 용으로 변경
    cache_key = f"polygon_dividend_schedule:{upper_symbol}"
    
    cached_data = get_from_redis_cache(cache_key)
    if cached_data: 
        return cached_data

    if not POLYGON_API_KEY:
        logger.warning("Polygon.io API 키가 없어 배당 정보를 조회할 수 없습니다.")
        return {'payouts': [], 'months': []}

    payouts = []
    month_names = []
    
    try:
        # 🛠️ 변경: API 호출 로직을 Polygon.io로 교체
        url = f"https://api.polygon.io/v3/reference/dividends?ticker={upper_symbol}&apiKey={POLYGON_API_KEY}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        polygon_response = response.json()
        polygon_dividends = polygon_response.get('results', [])

        if polygon_dividends:
            for div in polygon_dividends:
                # 🛠️ 변경: Polygon.io 응답 구조에 맞춰 데이터 파싱
                if div.get('pay_date') and div.get('cash_amount'):
                    payouts.append({
                        'ex_date': div.get('ex_dividend_date'),
                        'pay_date': div.get('pay_date'),
                        'amount': div.get('cash_amount')
                    })

            # 월 이름 목록 계산 (정확한 지급일 기준)
            payout_months_num = sorted(list(set(datetime.strptime(p['pay_date'], '%Y-%m-%d').month for p in payouts if p.get('pay_date'))))
            MONTH_MAP = {1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'}
            month_names = [MONTH_MAP[m] for m in payout_months_num]

    except requests.exceptions.RequestException as e:
        status_code = e.response.status_code if e.response else "N/A"
        reason = e.response.reason if e.response else "N/A"
        logger.error(f"Polygon.io API 호출 실패 ({upper_symbol}): {status_code} {reason}")
    except Exception as e:
        logger.warning(f"({upper_symbol}) Polygon.io 배당 지급 일정 조회 실패: {e}")

    result = {'payouts': payouts, 'months': month_names}
    set_to_redis_cache(cache_key, result, ttl_hours=6) # 6시간 캐싱으로 API 호출 최소화
    return result


def get_dividend_allocation_data(dividend_metrics):
    return [{'symbol': s, 'value': m['expected_annual_dividend']} for s, m in dividend_metrics.items() if m.get('expected_annual_dividend', 0) > 0]
