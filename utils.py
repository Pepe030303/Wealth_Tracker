# 📄 utils.py

from datetime import datetime, timedelta
import logging
import yfinance as yf
import pandas as pd
import json
import requests
from redis import Redis
from models import StockPrice
# 🛠️ 변경: Finnhub API 키를 stock_api 모듈에서 가져옵니다.
from stock_api import FINNHUB_API_KEY

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
        # 🛠️ 변경: 배당금 계산 로직을 yfinance가 아닌 Finnhub 데이터 기반으로 변경합니다.
        # 연간 주당 배당금(annual_dps)을 Finnhub 데이터에서 직접 가져오거나, 최근 1년치 배당을 합산하여 계산합니다.
        
        # 1. Finnhub에서 배당 데이터 가져오기
        dividend_data = get_dividend_payout_schedule(symbol)
        payouts = dividend_data.get('payouts', [])
        
        if not payouts:
            continue

        # 2. 연간 주당 배당금(annual_dps) 계산
        # 가장 최근 배당금과 빈도를 사용하여 연간 배당금 추정
        annual_dps = 0
        if payouts:
            # Finnhub 응답은 최신순으로 오므로 첫번째 항목 사용
            last_payout = payouts[0]
            frequency = last_payout.get('frequency', 'quarterly') # 기본값을 분기로 설정
            
            multiplier = 4 # 분기
            if frequency == 'semi-annual': multiplier = 2
            elif frequency == 'annual': multiplier = 1
            elif frequency == 'monthly': multiplier = 12
            
            # 일부 데이터는 frequency가 없어, 최근 1년치 합산으로 대체
            one_year_ago = datetime.now() - timedelta(days=365)
            recent_payouts = [p for p in payouts if datetime.strptime(p.get('pay_date', p.get('ex_date')), '%Y-%m-%d') > one_year_ago]
            
            if len(recent_payouts) > 0:
                annual_dps = sum(p['amount'] for p in recent_payouts)
            elif 'amount' in last_payout: # 1년치 데이터가 없으면 추정
                 annual_dps = last_payout['amount'] * multiplier


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
    [API 교체] yfinance 대신 Finnhub API를 사용하여 배당 정보를 조회합니다.
    과거 배당금 지급 내역(지급일, 배당락일 포함)과 월 이름 목록을 함께 반환합니다.
    """
    upper_symbol = symbol.upper()
    # 🛠️ 변경: 캐시 키를 Finnhub용으로 변경
    cache_key = f"finnhub_dividend_schedule:{upper_symbol}"
    
    cached_data = get_from_redis_cache(cache_key)
    if cached_data: 
        return cached_data

    if not FINNHUB_API_KEY:
        logger.warning("Finnhub API 키가 없어 배당 정보를 조회할 수 없습니다.")
        return {'payouts': [], 'months': []}

    payouts = []
    month_names = []
    
    # 🛠️ 변경: API 호출 로직을 Finnhub으로 교체
    try:
        # Finnhub API는 3년치 데이터를 제공하므로, 최근 데이터만 필터링할 필요가 거의 없음
        one_year_ago = datetime.now() - timedelta(days=365*3)
        start_date = one_year_ago.strftime('%Y-%m-%d')
        
        url = f"https://finnhub.io/api/v1/stock/dividend2?symbol={upper_symbol}&token={FINNHUB_API_KEY}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        finnhub_dividends = response.json()

        if finnhub_dividends:
            for div in finnhub_dividends:
                # 🛠️ 변경: Finnhub 응답 구조에 맞춰 데이터 파싱
                if div.get('payDate') and div.get('amount'):
                    payouts.append({
                        'ex_date': div.get('exDate'),
                        'pay_date': div.get('payDate'),
                        'amount': div.get('amount'),
                        'frequency': div.get('frequency')
                    })

            # 월 이름 목록 계산 (지급일 기준)
            payout_months_num = sorted(list(set(datetime.strptime(p['pay_date'], '%Y-%m-%d').month for p in payouts)))
            MONTH_MAP = {1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'}
            month_names = [MONTH_MAP[m] for m in payout_months_num]

    except requests.exceptions.RequestException as e:
        logger.error(f"Finnhub API 호출 실패 ({upper_symbol}): {e}")
    except Exception as e:
        logger.warning(f"({upper_symbol}) Finnhub 배당 지급 일정 조회 실패: {e}")

    result = {'payouts': payouts, 'months': month_names}
    set_to_redis_cache(cache_key, result, ttl_hours=6) # 캐시 TTL 6시간으로 설정
    return result


def get_dividend_allocation_data(dividend_metrics):
    return [{'symbol': s, 'value': m['expected_annual_dividend']} for s, m in dividend_metrics.items() if m.get('expected_annual_dividend', 0) > 0]
