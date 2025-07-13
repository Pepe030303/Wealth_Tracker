# 📄 utils.py

from datetime import datetime, timedelta
import logging
import pandas as pd
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

def set_to_redis_cache(key, value, ttl_hours=6):
    if not redis_conn: return
    redis_conn.setex(key, timedelta(hours=ttl_hours), json.dumps(value))


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
            else: 
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
    [로직 전면 개편] 과거 배당 이력(최대 5년)을 분석하여 현재 연도의 미래 배당을 예측하고,
    실제 공시된 배당과 통합하여 반환합니다. 월배당 및 특별배당 패턴을 자동으로 처리합니다.
    """
    upper_symbol = symbol.upper()
    cache_key = f"projected_dividend_schedule_v2:{upper_symbol}"
    
    cached_data = get_from_redis_cache(cache_key)
    if cached_data:
        return cached_data

    historical_data = get_dividend_payout_schedule(symbol)
    historical_payouts = historical_data.get('payouts', [])
    
    if not historical_payouts:
        return {'payouts': [], 'months': []}

    current_year = datetime.now().year
    
    actual_payouts = {
        (datetime.strptime(p['pay_date'], '%Y-%m-%d').month, datetime.strptime(p['pay_date'], '%Y-%m-%d').day): {**p, 'is_estimated': False}
        for p in historical_payouts if p.get('pay_date') and datetime.strptime(p['pay_date'], '%Y-%m-%d').year == current_year
    }

    monthly_pattern = defaultdict(lambda: {'pay_days': [], 'ex_days': [], 'amounts': []})
    for p in historical_payouts:
        if p.get('pay_date') and p.get('ex_date'):
            pay_dt = datetime.strptime(p['pay_date'], '%Y-%m-%d')
            ex_dt = datetime.strptime(p['ex_date'], '%Y-%m-%d')
            monthly_pattern[pay_dt.month]['pay_days'].append(pay_dt.day)
            monthly_pattern[pay_dt.month]['ex_days'].append(ex_dt.day)
            monthly_pattern[pay_dt.month]['amounts'].append(p['amount'])

    final_payouts = list(actual_payouts.values())
    
    for month, data in monthly_pattern.items():
        avg_pay_day = int(sum(data['pay_days']) / len(data['pay_days']))
        
        if (month, avg_pay_day) in actual_payouts:
            continue
            
        avg_ex_day = int(sum(data['ex_days']) / len(data['ex_days']))
        avg_amount = sum(data['amounts']) / len(data['amounts'])
        
        try:
            # 🛠️ 버그 수정: avg_pay_ay를 avg_pay_day로 수정
            pay_date_obj = datetime(current_year, month, avg_pay_day)
            est_ex_date_month = month - 1 if month > 1 else 12
            est_ex_date_year = current_year if month > 1 else current_year -1
            projected_ex_date = datetime(est_ex_date_year, est_ex_date_month, avg_ex_day).strftime('%Y-%m-%d')
        except ValueError:
            projected_ex_date = datetime(current_year, month, 1).strftime('%Y-%m-%d')


        final_payouts.append({
            'pay_date': datetime(current_year, month, avg_pay_day).strftime('%Y-%m-%d'),
            'ex_date': projected_ex_date,
            'amount': avg_amount,
            'is_estimated': True
        })


    final_payouts.sort(key=lambda p: p['pay_date'])
    
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
        url = f"https://api.polygon.io/v3/reference/dividends?ticker={upper_symbol}&limit=60&apiKey={POLYGON_API_KEY}"
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
        
        payouts.sort(key=lambda p: p['pay_date'], reverse=True)

    except requests.exceptions.RequestException as e:
        status_code = e.response.status_code if e.response else "N/A"
        reason = e.response.reason if e.response else "N/A"
        logger.error(f"Polygon.io API 호출 실패 ({upper_symbol}): {status_code} {reason}")
    except Exception as e:
        logger.warning(f"({upper_symbol}) Polygon.io 배당 지급 일정 조회 실패: {e}")

    result = {'payouts': payouts, 'months': []}
    set_to_redis_cache(cache_key, result, ttl_hours=6)
    return result


def get_dividend_allocation_data(dividend_metrics):
    return [{'symbol': s, 'value': m['expected_annual_dividend']} for s, m in dividend_metrics.items() if m.get('expected_annual_dividend', 0) > 0]
