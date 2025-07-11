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
    보유 종목의 예상 연간 배당금과 수익률만 계산합니다. (월별 계산은 라우트에서 처리)
    """
    holdings = Holding.query.filter_by(user_id=user_id).all()
    if not holdings: return {}
    
    dividend_metrics = {}
    from stock_api import stock_api

    for h in holdings:
        try:
            ticker = yf.Ticker(h.symbol)
            info = ticker.info
            
            annual_dps = float(info.get('trailingAnnualDividendRate') or info.get('dividendRate') or 0)
            
            if annual_dps > 0:
                expected_annual_dividend = annual_dps * h.quantity
                price_data = stock_api.get_stock_price(h.symbol)
                
                dividend_yield = (annual_dps / price_data['price']) * 100 if price_data and price_data.get('price') and price_data['price'] > 0 else info.get('yield', 0) * 100
                
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
    """
    과거 배당락일(.actions)을 기준으로 배당 월을 정확하게 추정합니다.
    """
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
            start_date = pd.to_datetime(datetime.now() - timedelta(days=540))
            ex_dividend_dates_naive = ex_dividend_dates.tz_convert(None) if ex_dividend_dates.tz is not None else ex_dividend_dates
            recent_ex_dates = ex_dividend_dates_naive[ex_dividend_dates_naive > start_date]
            if not recent_ex_dates.empty:
                for date in recent_ex_dates:
                    paid_months.add(date.month)
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
