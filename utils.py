# utils.py

from datetime import datetime, timedelta
import logging
import yfinance as yf
import pandas as pd
import numpy as np
from models import Holding

logger = logging.getLogger(__name__)

def calculate_dividend_metrics(user_id):
    # 이 함수는 수정할 필요 없음
    holdings = Holding.query.filter_by(user_id=user_id).all()
    if not holdings: return {}
    dividend_metrics = {}
    from stock_api import stock_api
    for h in holdings:
        try:
            ticker = yf.Ticker(h.symbol); info = ticker.info; annual_dps = 0.0
            if info.get('quoteType') == 'ETF' and info.get('trailingAnnualDividendRate'):
                annual_dps = info.get('trailingAnnualDividendRate', 0)
            elif info.get('dividendRate'):
                annual_dps = info.get('dividendRate', 0)
            elif not ticker.dividends.empty:
                naive_dividends = ticker.dividends.tz_localize(None)
                last_year_dividends = naive_dividends[naive_dividends.index > datetime.now() - timedelta(days=365)]
                if not last_year_dividends.empty: annual_dps = last_year_dividends.sum()
            if annual_dps > 0:
                expected_annual_dividend = float(annual_dps) * h.quantity
                price_data = stock_api.get_stock_price(h.symbol)
                dividend_yield = (annual_dps / price_data['price']) * 100 if price_data and price_data.get('price') and price_data['price'] > 0 else info.get('yield', 0) * 100
                dividend_metrics[h.symbol] = {'expected_annual_dividend': expected_annual_dividend, 'dividend_yield': dividend_yield}
        except Exception as e:
            logger.warning(f"({h.symbol}) 배당 지표 계산 실패: {e}")
            continue
    return dividend_metrics

def get_dividend_allocation_data(dividend_metrics):
    return [{'symbol': s, 'value': m['expected_annual_dividend']} for s, m in dividend_metrics.items() if m.get('expected_annual_dividend', 0) > 0]


# --- 동적 배당 월 조회 기능 (조건부 하드코딩 추가) ---

DIVIDEND_MONTH_CACHE = {}
MONTH_NUMBER_TO_NAME = {1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'}

def get_dividend_months(symbol):
    """
    API를 통해 배당 월을 조회하되, SCHD에 특정 문제가 발생하면 하드코딩된 값으로 보정합니다.
    """
    upper_symbol = symbol.upper()
    if upper_symbol in DIVIDEND_MONTH_CACHE:
        return DIVIDEND_MONTH_CACHE[upper_symbol]

    paid_months = set()
    try:
        ticker = yf.Ticker(upper_symbol)
        
        # 1. 과거 배당락일(.actions)을 우선적으로 사용
        actions = ticker.actions
        if actions is not None and not actions.empty and 'Dividends' in actions.columns:
            ex_dividend_dates = actions[actions['Dividends'] > 0].index
            
            # 시간대 정보 제거
            ex_dividend_dates_naive = ex_dividend_dates.tz_convert(None) if ex_dividend_dates.tz is not None else ex_dividend_dates
            
            # 모든 과거 데이터의 월을 집계
            for date in ex_dividend_dates_naive:
                paid_months.add(date.month)
            
            logger.info(f"[{upper_symbol}] API에서 조회된 배당 월: {sorted(list(paid_months))}")

    except Exception as e:
        logger.warning(f"({upper_symbol}) 배당 월 정보 조회 중 예외 발생: {e}")
    
    # --- 조건부 하드코딩 (보정 로직) ---
    final_months_list = sorted(list(paid_months))
    
    # 만약 조회된 종목이 SCHD이고, 6월이 빠져있다면 강제로 보정
    if upper_symbol == 'SCHD' and 6 not in final_months_list and len(final_months_list) > 0:
        logger.warning(f"[{upper_symbol}] 6월 배당이 누락되어 하드코딩 값으로 보정합니다. (API 결과: {final_months_list})")
        final_months_list = [3, 6, 9, 12]

    # ------------------------------------

    if final_months_list:
        month_names = [MONTH_NUMBER_TO_NAME.get(m, '') for m in final_months_list]
        DIVIDEND_MONTH_CACHE[upper_symbol] = month_names
        return month_names
    else:
        DIVIDEND_MONTH_CACHE[upper_symbol] = []
        return []
