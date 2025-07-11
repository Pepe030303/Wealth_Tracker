# utils.py

from datetime import datetime, timedelta
import logging
import yfinance as yf
import pandas as pd
from models import Holding

logger = logging.getLogger(__name__)

# --- 배당금 계산 관련 헬퍼 함수 ---

def calculate_dividend_metrics(user_id):
    """
    특정 사용자의 모든 보유 종목에 대한 예상 연간 배당금 및 수익률을 계산합니다.
    """
    holdings = Holding.query.filter_by(user_id=user_id).all()
    if not holdings:
        return {}
        
    dividend_metrics = {}
    # stock_api를 여기서 직접 import하여 순환 참조 방지
    from stock_api import stock_api

    for h in holdings:
        try:
            ticker = yf.Ticker(h.symbol)
            info = ticker.info
            
            annual_dps = 0.0 # 연간 주당 배당금
            # ETF와 일반 주식에 대한 배당 정보 추출 방식 분기
            if info.get('quoteType') == 'ETF' and info.get('trailingAnnualDividendRate'):
                annual_dps = info.get('trailingAnnualDividendRate', 0)
            elif info.get('dividendRate'):
                annual_dps = info.get('dividendRate', 0)
            # 폴백: 과거 1년치 배당금 합산
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
                    # 가격 정보가 없을 경우, yfinance의 수익률 정보를 사용
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


# --- 동적 배당 월 조회 기능 ---

DIVIDEND_MONTH_CACHE = {}
MONTH_NUMBER_TO_NAME = {1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'}

def get_dividend_months(symbol):
    """
    yfinance API를 통해 종목의 배당 월을 동적으로 조회하고 캐싱합니다.
    (calendar -> actions 순으로 조회)
    """
    upper_symbol = symbol.upper()
    if upper_symbol in DIVIDEND_MONTH_CACHE:
        return DIVIDEND_MONTH_CACHE[upper_symbol]

    paid_months = None
    try:
        ticker = yf.Ticker(upper_symbol)
        
        # 1. calendar 정보에서 다음 배당락일 확인 (가장 정확)
        if hasattr(ticker, 'calendar') and ticker.calendar is not None and not ticker.calendar.empty:
            calendar_df = ticker.calendar.transpose() # 행/열 전환
            if 'Ex-Dividend Date' in calendar_df.columns:
                next_ex_div_date = calendar_df.loc['Earnings', 'Ex-Dividend Date']
                # 날짜/시간 객체인지 확인
                if isinstance(next_ex_div_date, (datetime, pd.Timestamp)):
                    base_month = next_ex_div_date.month
                    # 배당 주기를 추정 (월배당 또는 분기배당)
                    info = ticker.info
                    # Realty Income(O)와 같은 월배당 종목 판별
                    if upper_symbol == 'O' or (info.get('payoutRatio') and len(ticker.dividends) > 9):
                         paid_months = list(range(1, 13))
                    # 분기 배당으로 추정
                    else:
                        paid_months = sorted([(base_month - 1 - 3 * i) % 12 + 1 for i in range(4)])

        # 2. calendar 정보가 없으면 actions 데이터로 폴백
        if not paid_months:
            actions = ticker.actions
            if not actions.empty and 'Dividends' in actions.columns and actions['Dividends'].sum() > 0:
                ex_dividend_dates = actions[actions['Dividends'] > 0].index
                start_date = pd.to_datetime(datetime.now() - timedelta(days=450))
                ex_dividend_dates_naive = ex_dividend_dates.tz_localize(None)
                recent_ex_dates = ex_dividend_dates_naive[ex_dividend_dates_naive > start_date]
                if not recent_ex_dates.empty:
                    paid_months = sorted(list(recent_ex_dates.month.unique()))

    except Exception as e:
        logger.warning(f"({upper_symbol}) 배당 월 정보 조회 실패: {e}")
        paid_months = None

    if paid_months:
        month_names = [MONTH_NUMBER_TO_NAME.get(m, '') for m in paid_months]
        DIVIDEND_MONTH_CACHE[upper_symbol] = month_names
        return month_names
    else:
        # 최종 실패 시 빈 리스트 캐싱
        DIVIDEND_MONTH_CACHE[upper_symbol] = []
        return []
