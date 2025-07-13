# 📄 utils.py

from datetime import datetime, timedelta
import logging
import yfinance as yf
import pandas as pd
import json
import requests
from redis import Redis
from models import StockPrice
from stock_api import POLYGON_API_KEY
from collections import defaultdict

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
        
        # 🛠️ 변경: 예측된 데이터를 포함한 스케줄을 사용하여 연간 배당금 계산
        dividend_data = get_projected_dividend_schedule(symbol)
        payouts = dividend_data.get('payouts', [])
        
        if not payouts:
            continue

        # 최근 1년치 실제/예측 배당금의 합으로 연간 배당금(annual_dps)을 계산
        annual_dps = 0
        if payouts:
            # 배당금액이 가장 높은 4개(보통 1년치 분기배당)를 합산하여 연간 배당금 추정
            payouts.sort(key=lambda x: x['amount'], reverse=True)
            annual_dps = sum(p['amount'] for p in payouts[:4])


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

def get_projected_dividend_schedule(symbol):
    """
    [기능 개선] 과거 배당 이력을 분석하여 현재 연도의 미래 배당을 예측하고,
    실제 공시된 배당과 통합하여 반환합니다.
    """
    upper_symbol = symbol.upper()
    cache_key = f"projected_dividend_schedule:{upper_symbol}"
    
    cached_data = get_from_redis_cache(cache_key)
    if cached_data:
        return cached_data

    historical_data = get_dividend_payout_schedule(symbol)
    historical_payouts = historical_data.get('payouts', [])
    
    if not historical_payouts:
        return {'payouts': [], 'months': []}

    current_year = datetime.now().year
    
    # 1. 실제 공시된 현재 연도 배당금 추출
    actual_payouts_current_year = {
        datetime.strptime(p['pay_date'], '%Y-%m-%d').month: {**p, 'is_estimated': False}
        for p in historical_payouts if p.get('pay_date') and datetime.strptime(p['pay_date'], '%Y-%m-%d').year == current_year
    }

    # 2. 과거 데이터를 기반으로 배당 패턴 분석
    payout_months_days = defaultdict(list)
    for p in historical_payouts:
        if p.get('pay_date'):
            pay_date = datetime.strptime(p['pay_date'], '%Y-%m-%d')
            payout_months_days[pay_date.month].append(pay_date.day)

    # 3. 배당 월 및 평균 지급일 계산
    # 가장 빈번하게 배당이 있었던 월들을 패턴으로 간주 (보통 4개)
    payout_pattern_months = sorted([month for month, days in payout_months_days.items() if len(days) >= 2], 
                                   key=lambda m: len(payout_months_days[m]), reverse=True)[:4]

    avg_days = {month: int(sum(days) / len(days)) for month, days in payout_months_days.items() if month in payout_pattern_months}
    
    # 4. 가장 최근 배당액을 예측 금액으로 사용
    latest_amount = historical_payouts[0]['amount'] if historical_payouts else 0

    # 5. 예측된 배당 생성 및 실제 데이터와 병합
    final_payouts = list(actual_payouts_current_year.values())
    processed_months = set(actual_payouts_current_year.keys())

    for month in payout_pattern_months:
        if month not in processed_months:
            day = avg_days.get(month, 15) # 평균일이 없으면 15일로
            projected_date = datetime(current_year, month, day).strftime('%Y-%m-%d')
            final_payouts.append({
                'pay_date': projected_date,
                'ex_date': None, # 예측치는 배당락일 정보 없음
                'amount': latest_amount,
                'is_estimated': True
            })

    final_payouts.sort(key=lambda p: p['pay_date'])
    
    # 월 이름 목록 계산 (최종 데이터 기준)
    payout_months_num = sorted(list(set(datetime.strptime(p['pay_date'], '%Y-%m-%d').month for p in final_payouts)))
    MONTH_MAP = {1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'}
    month_names = [MONTH_MAP[m] for m in payout_months_num]

    result = {'payouts': final_payouts, 'months': month_names}
    set_to_redis_cache(cache_key, result, ttl_hours=6)
    return result


def get_dividend_payout_schedule(symbol):
    """
    Polygon.io API를 사용하여 과거 배당 정보를 조회합니다. (최대 5년치)
    """
    upper_symbol = symbol.upper()
    cache_key = f"polygon_dividend_schedule:{upper_symbol}"
    
    cached_data = get_from_redis_cache(cache_key)
    if cached_data: 
        return cached_data

    if not POLYGON_API_KEY:
        logger.warning("Polygon.io API 키가 없어 배당 정보를 조회할 수 없습니다.")
        return {'payouts': [], 'months': []}

    payouts = []
    
    try:
        url = f"https://api.polygon.io/v3/reference/dividends?ticker={upper_symbol}&limit=60&apiKey={POLYGON_API_KEY}" # 60개면 5년*12개월
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        polygon_response = response.json()
        polygon_dividends = polygon_response.get('results', [])

        if polygon_dividends:
            for div in polygon_dividends:
                if div.get('pay_date') and div.get('cash_amount'):
                    payouts.append({
                        'ex_date': div.get('ex_dividend_date'),
                        'pay_date': div.get('pay_date'),
                        'amount': div.get('cash_amount')
                    })
        
        # 지급일 기준 내림차순 정렬 (최신이 위로)
        payouts.sort(key=lambda p: p['pay_date'], reverse=True)

    except requests.exceptions.RequestException as e:
        status_code = e.response.status_code if e.response else "N/A"
        reason = e.response.reason if e.response else "N/A"
        logger.error(f"Polygon.io API 호출 실패 ({upper_symbol}): {status_code} {reason}")
    except Exception as e:
        logger.warning(f"({upper_symbol}) Polygon.io 배당 지급 일정 조회 실패: {e}")

    # 월 이름 목록 계산은 get_projected_dividend_schedule에서 수행하므로 여기서는 payouts만 반환
    result = {'payouts': payouts, 'months': []}
    set_to_redis_cache(cache_key, result, ttl_hours=6)
    return result


def get_dividend_allocation_data(dividend_metrics):
    return [{'symbol': s, 'value': m['expected_annual_dividend']} for s, m in dividend_metrics.items() if m.get('expected_annual_dividend', 0) > 0]
