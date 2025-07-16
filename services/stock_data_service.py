# 📄 services/stock_data_service.py
# 🛠️ 신규 파일: utils.py에서 종목 데이터 관련 비즈니스 로직을 분리하여 생성

from datetime import datetime, timedelta
import logging
import yfinance as yf
import pandas as pd
import requests
from utils import get_from_redis_cache, set_to_redis_cache, MANUAL_OVERRIDES

logger = logging.getLogger(__name__)

def calculate_dividend_metrics(holdings, price_data_map):
    """
    보유 종목 목록을 기반으로 각 종목의 배당 관련 지표를 계산합니다.
    - 연간 예상 배당금, 배당수익률, 주당 배당금을 포함합니다.
    - 수동 재정의 값을 우선 적용하고, Redis 캐시를 활용합니다.
    """
    dividend_metrics = {}
    for h in holdings:
        symbol = h.symbol.upper()
        
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

def get_adjusted_dividend_history(symbol):
    """
    액면 분할 이력을 반영하여 보정된 과거 배당금 이력을 조회합니다.
    - 주식 분할이 발생하면, 그 이전의 배당금은 현재 주식 수 기준으로 환산됩니다.
    """
    cache_key = f"adjusted_dividend_history:{symbol.upper()}"
    if cached_data := get_from_redis_cache(cache_key):
        return cached_data

    try:
        actions = yf.Ticker(symbol).actions
        if actions is None or actions.empty:
            return {'status': 'ok', 'history': []}
        actions['adj_factor'] = 1.0
        split_dates = actions[actions['Stock Splits'] != 0].index
        for date in reversed(actions.index):
            current_factor = actions.loc[date, 'adj_factor']
            prev_date_index = actions.index.get_loc(date) - 1
            if prev_date_index >= 0:
                prev_date = actions.index[prev_date_index]
                if date in split_dates:
                    actions.loc[prev_date, 'adj_factor'] = current_factor * actions.loc[date, 'Stock Splits']
                else:
                    actions.loc[prev_date, 'adj_factor'] = current_factor
        dividends = actions[actions['Dividends'] > 0].copy()
        if dividends.empty: return {'status': 'ok', 'history': []}
        dividends['adjusted_dps'] = dividends['Dividends'] / dividends['adj_factor']
        history = [{'date': date.strftime('%Y-%m-%d'), 'amount': row['adjusted_dps']} for date, row in dividends.iterrows()]
        result = {'status': 'ok', 'history': history}
        set_to_redis_cache(cache_key, result)
        return result
    except Exception as e:
        logger.error(f"액면분할 보정 배당 이력 조회 실패 ({symbol}): {e}")
        return {'status': 'error', 'note': '데이터 보정에 실패했습니다.', 'history': []}

def calculate_5yr_avg_dividend_growth(adjusted_history):
    """
    보정된 배당 이력을 바탕으로 5년 연평균 배당 성장률(CAGR)을 계산합니다.
    """
    if not adjusted_history or len(adjusted_history) < 2:
        return None

    try:
        df = pd.DataFrame(adjusted_history)
        df['date'] = pd.to_datetime(df['date'])
        df['year'] = df['date'].dt.year
        
        annual_dividends = df.groupby('year')['amount'].sum()
        
        if len(annual_dividends) < 2: return None
            
        end_year = annual_dividends.index.max()
        start_year_for_period = end_year - 4
        
        relevant_years = annual_dividends.loc[annual_dividends.index >= start_year_for_period]

        if len(relevant_years) < 2 or relevant_years.iloc[0] == 0:
            return None
            
        start_value = relevant_years.iloc[0]
        end_value = relevant_years.iloc[-1]
        num_years = relevant_years.index[-1] - relevant_years.index[0]

        if num_years == 0: return None

        cagr = ((end_value / start_value) ** (1 / num_years)) - 1
        return cagr
    except Exception as e:
        logger.warning(f"DGR 계산 중 오류 발생: {e}")
        return None

def get_dividend_payout_schedule(symbol):
    """
    특정 종목의 최근 1년간의 배당 지급 이력을 기반으로 배당 지급 월과 상세 내역을 조회합니다.
    """
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
