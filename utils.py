# 📄 utils.py

from datetime import datetime, timedelta
import logging
import yfinance as yf
import pandas as pd
from models import Holding

logger = logging.getLogger(__name__)

def calculate_dividend_metrics(holdings, price_data_map):
    """
    보유 종목 목록과 가격 정보를 받아, 예상 연간 배당금과 수익률을 계산합니다.
    SCHD와 같은 ETF를 위해 yield 기반 계산 로직을 추가했습니다.
    """
    if not holdings: return {}
    
    dividend_metrics = {}
    for h in holdings:
        symbol = h.symbol.upper()
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            annual_dps = float(info.get('trailingAnnualDividendRate') or info.get('dividendRate') or 0)
            current_price = price_data_map.get(symbol, {}).get('price')

            if annual_dps == 0 and info.get('yield') and current_price:
                annual_dps = float(info['yield']) * current_price

            if annual_dps > 0:
                expected_annual_dividend = annual_dps * h.quantity
                
                dividend_yield = (annual_dps / current_price) * 100 if current_price and current_price > 0 else 0
                
                dividend_metrics[symbol] = {
                    'expected_annual_dividend': expected_annual_dividend,
                    'dividend_yield': dividend_yield
                }
        except Exception as e:
            logger.warning(f"({symbol}) 배당 지표 계산 실패: {e}")
            continue
            
    return dividend_metrics

def get_dividend_allocation_data(dividend_metrics):
    return [{'symbol': s, 'value': m['expected_annual_dividend']} for s, m in dividend_metrics.items() if m.get('expected_annual_dividend', 0) > 0]

DIVIDEND_MONTH_CACHE = {}
MONTH_NUMBER_TO_NAME = {1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'}

def get_dividend_months(symbol):
    """
    [TLT 배당 문제 해결]
    기존: 배당 월 목록만 반환
    변경: 배당 월 목록과 '연간 실제 배당 횟수'를 함께 반환하여, 
          한 달에 여러 번 배당하는 경우(특별 배당 등)를 정확히 계산할 수 있도록 함.
    """
    upper_symbol = symbol.upper()
    if upper_symbol in DIVIDEND_MONTH_CACHE: return DIVIDEND_MONTH_CACHE[upper_symbol]

    try:
        ticker = yf.Ticker(upper_symbol)
        actions = ticker.actions
        if actions is not None and not actions.empty and 'Dividends' in actions.columns and actions['Dividends'].sum() > 0:
            ex_dividend_dates = actions[actions['Dividends'] > 0].index
            
            ex_dividend_dates_naive = ex_dividend_dates.tz_convert(None) if ex_dividend_dates.tz is not None else ex_dividend_dates
            
            # 최근 1년 데이터만 사용
            one_year_ago = datetime.now() - timedelta(days=365)
            recent_ex_dates = ex_dividend_dates_naive[ex_dividend_dates_naive > pd.to_datetime(one_year_ago)]
            
            if not recent_ex_dates.empty:
                # 연간 배당 횟수 (예: TLT는 12가 아닌 13 이상이 될 수 있음)
                dividend_count_last_year = len(recent_ex_dates)
                # 배당금을 지급한 월 목록 (중복 제거)
                paid_months = sorted(list(set(recent_ex_dates.month)))

                month_names = [MONTH_NUMBER_TO_NAME.get(m, '') for m in paid_months]
                
                result = {
                    "months": month_names,
                    "count": dividend_count_last_year
                }
                DIVIDEND_MONTH_CACHE[upper_symbol] = result
                return result
    except Exception as e:
        logger.warning(f"({upper_symbol}) 배당 월 정보 조회 실패: {e}")

    # 실패하거나 배당 정보가 없는 경우 기본값 반환
    result = {"months": [], "count": 0}
    DIVIDEND_MONTH_CACHE[upper_symbol] = result
    return result
