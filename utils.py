# utils.py

from datetime import datetime, timedelta
import logging
import yfinance as yf
import pandas as pd
from models import Holding

logger = logging.getLogger(__name__)

def calculate_dividend_metrics(holdings, price_data_map):
    """
    보유 종목 목록과 가격 정보를 받아, 예상 연간 배당금과 수익률을 계산합니다.
    """
    if not holdings: return {}
    
    dividend_metrics = {}
    for h in holdings:
        symbol = h.symbol.upper()
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            annual_dps = float(info.get('trailingAnnualDividendRate') or info.get('dividendRate') or 0)
            
            if annual_dps > 0:
                expected_annual_dividend = annual_dps * h.quantity
                current_price = price_data_map.get(symbol, {}).get('price')
                
                dividend_yield = (annual_dps / current_price) * 100 if current_price and current_price > 0 else info.get('yield', 0) * 100
                
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
    upper_symbol = symbol.upper()
    if upper_symbol in DIVIDEND_MONTH_CACHE: return DIVIDEND_MONTH_CACHE[upper_symbol]

    try:
        ticker = yf.Ticker(upper_symbol)
        # 배당락일이 포함된 .actions 데이터를 가져옵니다.
        actions = ticker.actions
        if actions is not None and not actions.empty and 'Dividends' in actions.columns and actions['Dividends'].sum() > 0:
            ex_dividend_dates = actions[actions['Dividends'] > 0].index
            
            # 시간대 정보 제거
            ex_dividend_dates_naive = ex_dividend_dates.tz_convert(None) if ex_dividend_dates.tz is not None else ex_dividend_dates
            
            # 최근 18개월 데이터만 사용
            start_date = pd.to_datetime(datetime.now() - timedelta(days=540))
            recent_ex_dates = ex_dividend_dates_naive[ex_dividend_dates_naive > start_date]
            
            if not recent_ex_dates.empty:
                paid_months = sorted(list(recent_ex_dates.month.unique()))
                # SCHD와 같은 분기 배당주 보정 로직
                if len(paid_months) < 4 and any(m in [3,6,9,12] for m in paid_months):
                    paid_months = [3, 6, 9, 12]

                month_names = [MONTH_NUMBER_TO_NAME.get(m, '') for m in paid_months]
                DIVIDEND_MONTH_CACHE[upper_symbol] = month_names
                return month_names
    except Exception as e:
        logger.warning(f"({upper_symbol}) 배당 월 정보 조회 실패: {e}")

    DIVIDEND_MONTH_CACHE[upper_symbol] = []
    return []
