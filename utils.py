# 📄 utils.py

from datetime import datetime, timedelta
import logging
import json
import requests
from redis import Redis
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

def set_to_redis_cache(key, value, ttl_hours=24): # 캐시 시간 24시간으로 연장
    if not redis_conn: return
    redis_conn.setex(key, timedelta(hours=ttl_hours), json.dumps(value))

def _get_split_history(symbol):
    """주식 분할 이력을 조회하는 헬퍼 함수"""
    upper_symbol = symbol.upper()
    cache_key = f"polygon_split_history:{upper_symbol}"
    
    cached_data = get_from_redis_cache(cache_key)
    if cached_data:
        return cached_data

    if not POLYGON_API_KEY:
        return []

    splits = []
    try:
        url = f"https://api.polygon.io/v3/reference/splits?ticker={upper_symbol}&apiKey={POLYGON_API_KEY}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        for s in data.get('results', []):
            splits.append({
                'execution_date': s['execution_date'],
                'ratio': s['for'] / s['from']
            })
    except Exception as e:
        logger.error(f"Polygon.io 스플릿 이력 조회 실패 ({upper_symbol}): {e}")

    set_to_redis_cache(cache_key, splits)
    return splits

def _adjust_dividends_for_splits(dividends, splits):
    """주식 분할을 고려하여 과거 배당금을 조정하는 헬퍼 함수"""
    if not splits:
        return dividends

    adjusted_dividends = []
    for div in dividends:
        pay_date = datetime.strptime(div['pay_date'], '%Y-%m-%d')
        adjusted_amount = div['amount']
        for split in splits:
            split_date = datetime.strptime(split['execution_date'], '%Y-%m-%d')
            if pay_date < split_date:
                adjusted_amount /= split['ratio']
        
        adjusted_div = div.copy()
        adjusted_div['amount'] = adjusted_amount
        adjusted_dividends.append(adjusted_div)
        
    return adjusted_dividends


def calculate_dividend_metrics(holdings, price_data_map):
    dividend_metrics = {}
    for h in holdings:
        symbol = h.symbol.upper()
        
        dividend_data = get_projected_dividend_schedule(symbol)
        payouts = dividend_data.get('payouts', [])
        
        if not payouts:
            continue

        annual_dps = 0
        if payouts:
            one_year_ago = datetime.now() - timedelta(days=365)
            recent_payouts = [p for p in payouts if p.get('pay_date') and datetime.strptime(p['pay_date'], '%Y-%m-%d') > one_year_ago]
            if recent_payouts:
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

def get_projected_dividend_schedule(symbol):
    """
    [로직 전면 개편 v2] 액면분할을 보정하고, 분기별/월별 패턴을 더 정확히 예측합니다.
    """
    upper_symbol = symbol.upper()
    cache_key = f"projected_dividend_schedule_v5:{upper_symbol}"
    
    cached_data = get_from_redis_cache(cache_key)
    if cached_data:
        return cached_data

    historical_data = get_dividend_payout_schedule(symbol)
    splits = _get_split_history(symbol)
    
    # 🛠️ 기능 추가: 액면분할 보정된 배당금 사용
    adjusted_dividends = _adjust_dividends_for_splits(historical_data.get('payouts', []), splits)
    
    if not adjusted_dividends:
        return {'payouts': [], 'months': [], 'payout_count_last_12m': 0}

    current_year = datetime.now().year
    
    # 1. 현재 연도에 확정된 배당금 (API 기준)
    actual_payouts = {
        (datetime.strptime(p['pay_date'], '%Y-%m-%d').month, datetime.strptime(p['pay_date'], '%Y-%m-%d').day): {**p, 'is_estimated': False}
        for p in adjusted_dividends if p.get('pay_date') and datetime.strptime(p['pay_date'], '%Y-%m-%d').year == current_year
    }

    # 2. 과거 데이터를 기반으로 분기별 패턴 분석 (SCHD 문제 해결)
    quarterly_pattern = defaultdict(list)
    for p in adjusted_dividends:
        if p.get('pay_date'):
            pay_dt = datetime.strptime(p['pay_date'], '%Y-%m-%d')
            quarter = (pay_dt.month - 1) // 3 + 1
            quarterly_pattern[quarter].append(p)
    
    # 각 분기별 가장 최근 배당을 대표 패턴으로 사용
    latest_quarterly_pattern = {}
    for quarter, divs in quarterly_pattern.items():
        latest_quarterly_pattern[quarter] = max(divs, key=lambda x: x['pay_date'])

    # 3. 예측 배당 생성 및 실제 데이터와 병합
    final_payouts = list(actual_payouts.values())
    processed_quarters = set((datetime.strptime(p['pay_date'], '%Y-%m-%d').month - 1) // 3 + 1 for p in final_payouts)

    for quarter, pattern in latest_quarterly_pattern.items():
        if quarter in processed_quarters:
            continue
        
        pay_dt = datetime.strptime(pattern['pay_date'], '%Y-%m-%d')
        ex_dt = datetime.strptime(pattern['ex_date'], '%Y-%m-%d')
        
        # 🛠️ 개선: TLT 12월 다중배당과 같은 패턴을 허용하기 위해 단순 날짜 투영
        try:
            # 과거 날짜를 현재 연도로 투영
            projected_pay_date = pay_dt.replace(year=current_year)
            projected_ex_date = ex_dt.replace(year=current_year)
            # 만약 ex_date가 pay_date보다 뒤라면, ex_date의 연도를 1년 뺌
            if projected_ex_date > projected_pay_date:
                projected_ex_date = projected_ex_date.replace(year=current_year -1)

            final_payouts.append({
                'pay_date': projected_pay_date.strftime('%Y-%m-%d'),
                'ex_date': projected_ex_date.strftime('%Y-%m-%d'),
                'amount': pattern['amount'],
                'is_estimated': True
            })
        except ValueError: # 2월 29일 등 예외처리
            continue

    final_payouts.sort(key=lambda p: p['pay_date'])
    
    payout_count_last_12m = len(set(
        datetime.strptime(p['pay_date'], '%Y-%m-%d').strftime('%Y-%m')
        for p in adjusted_dividends if datetime.strptime(p['pay_date'], '%Y-%m-%d') > (datetime.now() - timedelta(days=365))
    ))
    
    payout_months_num = sorted(list(set(datetime.strptime(p['pay_date'], '%Y-%m-%d').month for p in final_payouts)))
    MONTH_MAP = {1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'}
    month_names = [MONTH_MAP[m] for m in payout_months_num]

    result = {'payouts': final_payouts, 'months': month_names, 'payout_count_last_12m': payout_count_last_12m}
    set_to_redis_cache(cache_key, result)
    return result


def get_dividend_payout_schedule(symbol):
    upper_symbol = symbol.upper()
    cache_key = f"polygon_dividend_schedule:{upper_symbol}"
    
    cached_data = get_from_redis_cache(cache_key)
    if cached_data: 
        return cached_data

    if not POLYGON_API_KEY:
        logger.warning("Polygon.io API 키가 없어 배당 정보를 조회할 수 없습니다.")
        return {'payouts': []}

    payouts = []
    
    try:
        url = f"https://api.polygon.io/v3/reference/dividends?ticker={upper_symbol}&limit=60&apiKey={POLYGON_API_KEY}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        polygon_response = response.json()
        polygon_dividends = polygon_response.get('results', [])

        if polygon_dividends:
            for div in polygon_dividends:
                if div.get('pay_date') and div.get('cash_amount') and div.get('ex_dividend_date'):
                    payouts.append({
                        'ex_date': div.get('ex_dividend_date'),
                        'pay_date': div.get('pay_date'),
                        'amount': div.get('cash_amount')
                    })
        
        payouts.sort(key=lambda p: p['pay_date'], reverse=True)

    except requests.exceptions.RequestException as e:
        status_code = e.response.status_code if e.response else "N/A"
        reason = e.response.reason if e.response else "N/A"
        logger.error(f"Polygon.io API 호출 실패 ({upper_symbol}): {status_code} {reason}")
    except Exception as e:
        logger.warning(f"({upper_symbol}) Polygon.io 배당 지급 일정 조회 실패: {e}")

    result = {'payouts': payouts}
    set_to_redis_cache(cache_key, result)
    return result


def get_dividend_allocation_data(dividend_metrics):
    return [{'symbol': s, 'value': m['expected_annual_dividend']} for s, m in dividend_metrics.items() if m.get('expected_annual_dividend', 0) > 0]
