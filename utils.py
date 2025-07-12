# utils.py

from datetime import datetime, timedelta
import logging
import yfinance as yf
import pandas as pd
import numpy as np
from models import Holding

logger = logging.getLogger(__name__)

# --- 하드코딩 데이터 추가 ---
HARDCODED_ANNUAL_DPS = {
    'SCHD': 2.70 # 2024년 기준 예상 연간 주당 배당금 (필요시 이 값을 업데이트)
}
HARDCODED_DIVIDEND_MONTHS = {'SCHD': [3, 6, 9, 12]}


def calculate_dividend_metrics(user_id):
    holdings = Holding.query.filter_by(user_id=user_id).all()
    if not holdings: return {}
    
    dividend_metrics = {}
    from stock_api import stock_api

    for h in holdings:
        symbol = h.symbol.upper()
        logger.info(f"--- [{symbol}] 배당 지표 계산 시작 ---")
        try:
            # 1. 하드코딩된 연간 DPS가 있는지 먼저 확인
            if symbol in HARDCODED_ANNUAL_DPS:
                annual_dps = HARDCODED_ANNUAL_DPS[symbol]
                logger.info(f"[{symbol}] 하드코딩된 연간 DPS 사용: {annual_dps}")
            else:
                ticker = yf.Ticker(symbol)
                info = ticker.info
                annual_dps = 0.0
                
                # 2. .info 객체에서 정보 조회
                rate_from_info = info.get('trailingAnnualDividendRate') or info.get('dividendRate')
                if rate_from_info:
                    annual_dps = float(rate_from_info)
                
                # 3. 과거 1년치 배당금 합산 (폴백)
                if annual_dps == 0 and not ticker.dividends.empty:
                    naive_dividends = ticker.dividends.tz_localize(None)
                    last_year_dividends = naive_dividends[naive_dividends.index > datetime.now() - timedelta(days=365)]
                    if not last_year_dividends.empty:
                        annual_dps = last_year_dividends.sum()
            
            # --- 최종 계산 ---
            if annual_dps > 0:
                expected_annual_dividend = annual_dps * h.quantity
                price_data = stock_api.get_stock_price(symbol)
                current_price = price_data.get('price') if price_data else None
                
                if current_price and current_price > 0:
                    dividend_yield = (annual_dps / current_price) * 100
                else:
                    info = yf.Ticker(symbol).info
                    dividend_yield = info.get('yield', 0) * 100

                logger.info(f"[{symbol}] 최종 결과: 연간 배당금 ${expected_annual_dividend:.2f}, 수익률 {dividend_yield:.2f}%")
                dividend_metrics[symbol] = {
                    'expected_annual_dividend': expected_annual_dividend,
                    'dividend_yield': dividend_yield
                }
            logger.info(f"--- [{symbol}] 배당 지표 계산 종료 ---")
        except Exception as e:
            logger.warning(f"({symbol}) 배당 지표 계산 중 예외 발생: {e}")
            logger.info(f"--- [{symbol}] 배당 지표 계산 종료 (실패) ---")
            continue
            
    return dividend_metrics

def get_dividend_allocation_data(dividend_metrics):
    return [{'symbol': s, 'value': m['expected_annual_dividend']} for s, m in dividend_metrics.items() if m.get('expected_annual_dividend', 0) > 0]

DIVIDEND_MONTH_CACHE = {}
MONTH_NUMBER_TO_NAME = {1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'}

def get_dividend_months(symbol):
    upper_symbol = symbol.upper()
    if upper_symbol in DIVIDEND_MONTH_CACHE: return DIVIDEND_MONTH_CACHE[upper_symbol]
    if upper_symbol in HARDCODED_DIVIDEND_MONTHS:
        return [MONTH_NUMBER_TO_NAME.get(m, '') for m in HARDCODED_DIVIDEND_MONTHS[upper_symbol]]
    paid_months = set()
    try:
        ticker = yf.Ticker(upper_symbol)
        actions = ticker.actions
        if actions is not None and not actions.empty and 'Dividends' in actions.columns:
            ex_dividend_dates = actions[actions['Dividends'] > 0].index
            ex_dividend_dates_naive = ex_dividend_dates.tz_convert(None) if ex_dividend_dates.tz is not None else ex_dividend_dates
            for date in ex_dividend_dates_naive: paid_months.add(date.month)
        if len(paid_months) == 3:
            sorted_months = sorted(list(paid_months))
            if np.diff(sorted_months).mean() > 2.5: # 분기 배당 패턴인지 확인
                base_month = sorted_months[0]
                paid_months.update([(base_month - 1 + 3 * i) % 12 + 1 for i in range(4)])
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
