# 📄 utils.py

from datetime import datetime, timedelta
import logging
import yfinance as yf
import pandas as pd
import json
from redis import Redis
from models import StockPrice
import requests
import os # 🛠️ os 모듈 임포트

try:
    from app import conn as redis_conn
except ImportError:
    redis_conn = None
    logging.warning("Redis 연결을 가져오지 못했습니다. 캐싱이 비활성화됩니다.")

logger = logging.getLogger(__name__)

# 🛠️ 기능 추가: 수동 재정의 데이터 저장을 위한 전역 변수
MANUAL_OVERRIDES = {}

def load_manual_overrides():
    """ 앱 시작 시 manual_overrides.json 파일을 로드합니다. """
    global MANUAL_OVERRIDES
    override_file = 'manual_overrides.json'
    if os.path.exists(override_file):
        try:
            with open(override_file, 'r') as f:
                MANUAL_OVERRIDES = json.load(f)
            logger.info(f"수동 재정의 데이터({override_file}) 로드 완료: {list(MANUAL_OVERRIDES.keys())}")
        except json.JSONDecodeError as e:
            logger.error(f"수동 재정의 파일 JSON 파싱 오류: {e}")
        except Exception as e:
            logger.error(f"수동 재정의 파일 로드 중 오류 발생: {e}")

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
        
        # 🛠️ 기능 추가: 수동 재정의 데이터 우선 확인
        if symbol in MANUAL_OVERRIDES and 'trailingAnnualDividendRate' in MANUAL_OVERRIDES[symbol]:
            annual_dps = MANUAL_OVERRIDES[symbol]['trailingAnnualDividendRate']
            logger.info(f"({symbol})에 대해 수동 재정의된 배당률 ${annual_dps} 적용.")
        else:
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
                except (requests.exceptions.HTTPError, KeyError, TypeError, ValueError) as e:
                    logger.warning(f"배당 지표 계산/파싱 실패 ({symbol}): {e}")
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

# 🛠️ 기능 추가: 액면분할을 보정한 배당 이력을 가져오는 함수
def get_adjusted_dividend_history(symbol):
    """
    yfinance에서 배당금과 액면분할 이력을 함께 조회하여,
    과거 배당금을 현재 주식 수 기준으로 보정한 리스트를 반환합니다.
    """
    cache_key = f"adjusted_dividend_history:{symbol.upper()}"
    if cached_data := get_from_redis_cache(cache_key):
        return cached_data

    try:
        actions = yf.Ticker(symbol).actions
        if actions is None or actions.empty:
            return {'status': 'ok', 'history': []}

        actions['adj_factor'] = 1.0
        
        # 액면분할 정보 처리
        split_dates = actions[actions['Stock Splits'] != 0].index
        for date in reversed(actions.index):
            current_factor = actions.loc[date, 'adj_factor']
            prev_date_index = actions.index.get_loc(date) - 1
            if prev_date_index >= 0:
                prev_date = actions.index[prev_date_index]
                if date in split_dates:
                    split_ratio = actions.loc[date, 'Stock Splits']
                    actions.loc[prev_date, 'adj_factor'] = current_factor * split_ratio
                else:
                    actions.loc[prev_date, 'adj_factor'] = current_factor
        
        dividends = actions[actions['Dividends'] > 0].copy()
        if dividends.empty:
            return {'status': 'ok', 'history': []}
            
        dividends['adjusted_dps'] = dividends['Dividends'] / dividends['adj_factor']
        
        history = [
            {'date': date.strftime('%Y-%m-%d'), 'amount': row['adjusted_dps']}
            for date, row in dividends.iterrows()
        ]
        
        result = {'status': 'ok', 'history': history}
        set_to_redis_cache(cache_key, result)
        return result

    except Exception as e:
        logger.error(f"액면분할 보정 배당 이력 조회 실패 ({symbol}): {e}")
        return {'status': 'error', 'note': '데이터 보정에 실패했습니다.', 'history': []}

# 🛠️ 기능 추가: 5년 연평균 배당성장률 계산 함수
def calculate_5yr_avg_dividend_growth(adjusted_history):
    """ 보정된 배당 이력을 바탕으로 5년 연평균 성장률(CAGR)을 계산합니다. """
    if not adjusted_history:
        return None

    df = pd.DataFrame(adjusted_history)
    df['date'] = pd.to_datetime(df['date'])
    df['year'] = df['date'].dt.year
    
    annual_dividends = df.groupby('year')['amount'].sum()
    
    # 최근 6개년 데이터 확보 (5년간의 성장률 계산을 위해)
    end_year = annual_dividends.index.max()
    start_year = end_year - 5

    relevant_years = annual_dividends.loc[start_year:end_year]
    
    # 유효한 데이터가 2개 미만이면 CAGR 계산 불가
    if len(relevant_years) < 2 or relevant_years.iloc[0] == 0:
        return None
        
    start_value = relevant_years.iloc[0]
    end_value = relevant_years.iloc[-1]
    num_years = len(relevant_years) - 1

    cagr = ((end_value / start_value) ** (1 / num_years)) - 1
    return cagr


def get_dividend_payout_schedule(symbol):
    upper_symbol = symbol.upper()
    cache_key = f"dividend_payout_schedule:{upper_symbol}"
    if cached_data := get_from_redis_cache(cache_key): return cached_data

    payouts, month_names = [], []
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
    except (requests.exceptions.HTTPError, AttributeError, KeyError, TypeError) as e:
        logger.warning(f"배당 지급 일정 조회/파싱 실패 ({upper_symbol}): {e}")
    except Exception as e:
        logger.error(f"배당 지급 일정 조회 중 예상치 못한 오류 ({upper_symbol}): {e}")

    result = {'payouts': payouts, 'months': month_names}
    set_to_redis_cache(cache_key, result)
    return result

def get_dividend_allocation_data(dividend_metrics):
    return [{'symbol': s, 'value': m['expected_annual_dividend']} for s, m in dividend_metrics.items() if m.get('expected_annual_dividend', 0) > 0]
