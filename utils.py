# utils.py

from datetime import datetime, timedelta
import logging
import yfinance as yf
import pandas as pd
import numpy as np
from models import Holding

logger = logging.getLogger(__name__)

def calculate_dividend_metrics(user_id):
    """
    보유 종목의 예상 연간 배당금과 수익률을 다각도로 계산합니다.
    """
    holdings = Holding.query.filter_by(user_id=user_id).all()
    if not holdings: return {}
    
    dividend_metrics = {}
    from stock_api import stock_api

    for h in holdings:
        try:
            ticker = yf.Ticker(h.symbol)
            info = ticker.info
            
            annual_dps = 0.0 # 연간 주당 배당금 (Annual Dividends Per Share)
            
            # --- 1순위: info 객체에서 직접적인 연간 배당금 정보 조회 ---
            if info.get('trailingAnnualDividendRate'): # ETF와 일부 주식에 사용
                annual_dps = float(info['trailingAnnualDividendRate'])
            elif info.get('dividendRate'): # 일반 주식에 주로 사용
                annual_dps = float(info['dividendRate'])
            
            # --- 2순위: 과거 1년치 배당금 합산 ---
            if annual_dps == 0 and not ticker.dividends.empty:
                naive_dividends = ticker.dividends.tz_localize(None)
                last_year_dividends = naive_dividends[naive_dividends.index > datetime.now() - timedelta(days=365)]
                if not last_year_dividends.empty:
                    annual_dps = last_year_dividends.sum()

            price_data = stock_api.get_stock_price(h.symbol)
            current_price = price_data.get('price') if price_data else None

            # --- 3순위: 수익률(yield)과 현재가로 역산 ---
            if annual_dps == 0 and info.get('yield') and current_price:
                annual_dps = current_price * info.get('yield')

            # --- 최종 계산 및 추가 ---
            if annual_dps > 0:
                expected_annual_dividend = annual_dps * h.quantity
                
                if current_price and current_price > 0:
                    dividend_yield = (annual_dps / current_price) * 100
                else: # 가격 정보가 없을 경우 info의 yield 사용
                    dividend_yield = info.get('yield', 0) * 100

                dividend_metrics[h.symbol] = {
                    'expected_annual_dividend': expected_annual_dividend,
                    'dividend_yield': dividend_yield
                }
        except Exception as e:
            logger.warning(f"({h.symbol}) 배당 지표 계산 실패: {e}")
            continue
            
    return dividend_metrics

def get_dividend_allocation_data(dividend_metrics):
    return [{'symbol': s, 'value': m['expected_annual_dividend']} for s, m in dividend_metrics.items() if m.get('expected_annual_dividend', 0) > 0]


DIVIDEND_MONTH_CACHE = {}
MONTH_NUMBER_TO_NAME = {1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'}
HARDCODED_DIVIDEND_MONTHS = {'SCHD': [3, 6, 9, 12]}

def get_dividend_months(symbol):
    upper_symbol = symbol.upper()
    if upper_symbol in DIVIDEND_MONTH_CACHE: return DIVIDEND_MONTH_CACHE[upper_symbol]
    if upper_symbol in HARDCODED_DIVIDEND_MONTHS:
        paid_months = HARDCODED_DIVIDEND_MONTHS[upper_symbol]
        month_names = [MONTH_NUMBER_TO_NAME.get(m, '') for m in paid_months]
        DIVIDEND_MONTH_CACHE[upper_symbol] = month_names
        return month_names
    paid_months = set()
    try:
        ticker = yf.Ticker(upper_symbol)
        actions = ticker.actions
        if actions is not None and not actions.empty and 'Dividends' in actions.columns:
            ex_dividend_dates = actions[actions['Dividends'] > 0].index
            ex_dividend_dates_naive = ex_dividend_dates.tz_convert(None) if ex_dividend_dates.tz is not None else ex_dividend_dates
            for date in ex_dividend_dates_naive:
                paid_months.add(date.month)
        if len(paid_months) == 3:
            sorted_months = sorted(list(paid_months))
            diffs = np.diff(sorted_months)
            if np.count_nonzero(diffs % 3 == 0) >= 1:
                base_month = sorted_months[0]
                expected_months = set([(base_month - 1 + 3 * i) % 12 + 1 for i in range(4)])
                paid_months.update(expected_months)
    except Exception as e:
        logger.warning(f"({upper_symbol}) 배당 월 정보 조회 실패: {e}")
    final_months_list = sorted(list(paid_months))
    if final_months_list:
        month_names = [MONTH_NUMBER_TO_NAME.get(m, '') for m in final_months_list]
        DIVIDEND_MONTH_CACHE[upper_symbol] = month_names
        return month_names
    else:
        DIVIDEND_MONTH_CACHE[upper_symbol] = []
        return []
