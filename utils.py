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
    보유 종목의 예상 연간 배당금과 수익률을 yfinance 데이터를 기반으로 계산합니다.
    """
    holdings = Holding.query.filter_by(user_id=user_id).all()
    if not holdings: return {}
    
    dividend_metrics = {}
    from stock_api import stock_api

    for h in holdings:
        symbol = h.symbol.upper()
        logger.info(f"--- [{symbol}] 배당 지표 계산 시작 ---")
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            annual_dps = 0.0 # 연간 주당 배당금 (Annual Dividends Per Share)
            
            # --- 신뢰도 순서대로 연간 DPS 조회 ---
            # 1. Trailing Annual Dividend Rate (ETF와 대부분 주식에 가장 신뢰도 높음)
            rate1 = info.get('trailingAnnualDividendRate')
            if rate1 is not None and rate1 > 0:
                annual_dps = float(rate1)
                logger.info(f"[{symbol}] trailingAnnualDividendRate 사용: {annual_dps}")
            else:
                # 2. Forward Annual Dividend Rate (미래 예상치)
                rate2 = info.get('dividendRate')
                if rate2 is not None and rate2 > 0:
                    annual_dps = float(rate2)
                    logger.info(f"[{symbol}] dividendRate 사용: {annual_dps}")
                else:
                    # 3. 과거 1년치 배당금 합산 (폴백)
                    if not ticker.dividends.empty:
                        naive_dividends = ticker.dividends.tz_localize(None)
                        last_year_dividends = naive_dividends[naive_dividends.index > datetime.now() - timedelta(days=365)]
                        if not last_year_dividends.empty:
                            annual_dps = float(last_year_dividends.sum())
                            logger.info(f"[{symbol}] 과거 1년 배당금 합산 사용: {annual_dps}")

            price_data = stock_api.get_stock_price(symbol)
            current_price = price_data.get('price') if price_data else None

            # --- 최종 계산 및 추가 ---
            logger.info(f"[{symbol}] 최종 결정된 연간 DPS: {annual_dps}")
            if annual_dps > 0:
                expected_annual_dividend = annual_dps * h.quantity
                
                if current_price and current_price > 0:
                    dividend_yield = (annual_dps / current_price) * 100
                else: # 가격 정보가 없을 경우 info의 yield 사용
                    dividend_yield = float(info.get('yield', 0.0) or 0.0) * 100

                logger.info(f"[{symbol}] 최종 결과: 보유량({h.quantity}), 연간 배당금(${expected_annual_dividend:.2f}), 수익률({dividend_yield:.2f}%)")
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

# --- 배당 월 조회 로직 (SCHD 하드코딩 유지) ---
DIVIDEND_MONTH_CACHE = {}
MONTH_NUMBER_TO_NAME = {1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'}
HARDCODED_DIVIDEND_MONTHS = {'SCHD': [3, 6, 9, 12]}

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
            for date in ex_dividend_dates_naive:
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
