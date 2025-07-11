# utils.py

from datetime import datetime, timedelta
import logging
import yfinance as yf
import pandas as pd
import numpy as np
from models import Holding # models에서 Holding만 가져옴

logger = logging.getLogger(__name__)

def calculate_dividend_metrics(user_id):
    """
    특정 사용자의 모든 보유 종목에 대한 예상 연간 배당금 및 수익률을 계산합니다.
    """
    holdings = Holding.query.filter_by(user_id=user_id).all()
    if not holdings:
        return {}
        
    dividend_metrics = {}
    from stock_api import stock_api

    for h in holdings:
        try:
            ticker = yf.Ticker(h.symbol)
            info = ticker.info
            
            annual_dps = 0.0
            if info.get('quoteType') == 'ETF' and info.get('trailingAnnualDividendRate'):
                annual_dps = info.get('trailingAnnualDividendRate', 0)
            elif info.get('dividendRate'):
                annual_dps = info.get('dividendRate', 0)
            elif not ticker.dividends.empty:
                naive_dividends = ticker.dividends.tz_localize(None)
                last_year_dividends = naive_dividends[naive_dividends.index > datetime.now() - timedelta(days=365)]
                if not last_year_dividends.empty:
                    annual_dps = last_year_dividends.sum()
            
            if annual_dps > 0:
                expected_annual_dividend = float(annual_dps) * h.quantity
                price_data = stock_api.get_stock_price(h.symbol)
                
                if price_data and price_data.get('price') and price_data['price'] > 0:
                    dividend_yield = (annual_dps / price_data['price']) * 100
                else:
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
    """
    배당금 지표에서 차트용 배분 데이터를 생성합니다.
    """
    return [{'symbol': s, 'value': m['expected_annual_dividend']} for s, m in dividend_metrics.items() if m.get('expected_annual_dividend', 0) > 0]


# --- 동적 배당 월 조회 기능 (최종 디버깅 및 하드코딩 포함) ---

DIVIDEND_MONTH_CACHE = {}
MONTH_NUMBER_TO_NAME = {1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'}

# 문제가 발생하는 특정 종목에 대한 예외 처리 (하드코딩)
HARDCODED_DIVIDEND_MONTHS = {
    'SCHD': [3, 6, 9, 12]
}

def get_dividend_months(symbol):
    """
    yfinance의 다양한 소스를 통해 배당 월을 추정하고, 특정 종목은 하드코딩된 값을 사용합니다.
    """
    upper_symbol = symbol.upper()
    if upper_symbol in DIVIDEND_MONTH_CACHE:
        return DIVIDEND_MONTH_CACHE[upper_symbol]

    # 1. 하드코딩된 종목인지 먼저 확인 (가장 확실)
    if upper_symbol in HARDCODED_DIVIDEND_MONTHS:
        paid_months = HARDCODED_DIVIDEND_MONTHS[upper_symbol]
        month_names = [MONTH_NUMBER_TO_NAME.get(m, '') for m in paid_months]
        DIVIDEND_MONTH_CACHE[upper_symbol] = month_names
        logger.info(f"[{upper_symbol}] 하드코딩된 배당 월 정보 사용: {paid_months}")
        return month_names

    paid_months = set()
    try:
        ticker = yf.Ticker(upper_symbol)
        
        # --- 디버깅을 위한 원시 데이터 로깅 ---
        logger.info(f"--- [{upper_symbol}] 배당 월 정보 조회 시작 ---")
        try: logger.info(f"[{upper_symbol}] .calendar 정보: {ticker.calendar}")
        except Exception: logger.info(f"[{upper_symbol}] .calendar 정보 없음")
        try: logger.info(f"[{upper_symbol}] .actions 정보 (최근 5개): \n{ticker.actions.tail()}")
        except Exception: logger.info(f"[{upper_symbol}] .actions 정보 없음")
        logger.info(f"-------------------------------------------------")

        # 2. 과거 배당락일(.actions)을 우선적으로 사용
        actions = ticker.actions
        if actions is not None and not actions.empty and 'Dividends' in actions.columns:
            ex_dividend_dates = actions[actions['Dividends'] > 0].index
            ex_dividend_dates_naive = ex_dividend_dates.tz_convert(None) if ex_dividend_dates.tz is not None else ex_dividend_dates
            for date in ex_dividend_dates_naive:
                paid_months.add(date.month)
        
        # 3. 분기 배당주인데 월이 3개만 잡히는 경우 보정 로직
        if len(paid_months) == 3:
            sorted_months = sorted(list(paid_months))
            diffs = np.diff(sorted_months)
            # 월 간의 차이가 대부분 3개월(분기)인지 확인
            if np.count_nonzero(diffs == 3) >= 1 or np.count_nonzero(diffs % 3 == 0) >=1:
                base_month = sorted_months[0]
                expected_months = set([(base_month - 1 + 3 * i) % 12 + 1 for i in range(4)])
                # 기존에 찾은 월들과 합집합하여 누락된 월 추가
                paid_months.update(expected_months)
                logger.info(f"[{upper_symbol}] 분기 배당 보정 적용 후: {sorted(list(paid_months))}")

    except Exception as e:
        logger.warning(f"({upper_symbol}) 배당 월 정보 조회 중 예외 발생: {e}")
    
    final_months = sorted(list(paid_months))
    if final_months:
        month_names = [MONTH_NUMBER_TO_NAME.get(m, '') for m in final_months]
        DIVIDEND_MONTH_CACHE[upper_symbol] = month_names
        return month_names
    else:
        DIVIDEND_MONTH_CACHE[upper_symbol] = []
        return []
