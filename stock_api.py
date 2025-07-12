# 📄 stock_api.py

import os
import requests
import logging
from datetime import datetime, timedelta
from app import db
from models import StockPrice
import yfinance as yf
import pandas as pd

logger = logging.getLogger(__name__)

# 개선: Ticker-CIK 맵 대신 미국 주식 전체 리스트(티커, 이름)를 저장
US_STOCKS_LIST = []
PROFILE_CACHE = {}

SIC_TO_SECTOR_MAP = {
    '1000-1499': 'Mining', '1500-1799': 'Construction', '2000-3999': 'Manufacturing',
    '4000-4999': 'Transportation & Public Utilities', '5000-5199': 'Wholesale Trade',
    '5200-5999': 'Retail Trade', '6000-6799': 'Finance, Insurance, Real Estate',
    '7000-8999': 'Services', '9100-9729': 'Public Administration', '9900-9999': 'N/A'
}

def get_sector_from_sic(sic_code):
    if not sic_code: return 'N/A'
    try:
        sic = int(sic_code)
        for sic_range, sector in SIC_TO_SECTOR_MAP.items():
            start, end = map(int, sic_range.split('-'))
            if start <= sic <= end: return sector
    except (ValueError, TypeError): return 'N/A'
    return 'N/A'

# 개선: SEC 데이터를 로드하여 미국 전체 주식 리스트를 구축하는 함수
def load_us_stocks_data():
    global US_STOCKS_LIST
    if US_STOCKS_LIST: return
    try:
        headers = {'User-Agent': 'WealthTracker/1.0 (dev@example.com)'}
        url = "https://www.sec.gov/files/company_tickers.json"
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # SEC 데이터는 "0": {"cik_str": ..., "ticker": ..., "title": ...} 형식
        all_companies = response.json()
        
        # 티커와 회사 이름만 추출하여 리스트로 저장
        # 티커에 '.' 이나 공백이 들어간 경우(보통주가 아닌 우선주 등)는 제외하여 검색 품질 향상
        US_STOCKS_LIST = [
            {'ticker': data['ticker'], 'name': data['title']}
            for data in all_companies.values()
            if '.' not in data['ticker'] and ' ' not in data['ticker']
        ]
        logger.info(f"미국 주식 검색을 위한 데이터 {len(US_STOCKS_LIST)}개 로드 완료.")
    except Exception as e:
        logger.error(f"SEC 기업 티커 데이터 로드 실패: {e}")


class StockAPIService:
    def __init__(self): self.session = requests.Session()

    def _get_from_cache(self, symbol):
        cached = StockPrice.query.filter_by(symbol=symbol).first()
        if cached and (datetime.utcnow() - cached.last_updated) < timedelta(minutes=15):
            return {'price': cached.current_price, 'change': cached.change, 'change_percent': cached.change_percent}
        return None

    def _update_cache(self, symbol, price_data):
        with db.session.no_autoflush:
            cached = StockPrice.query.filter_by(symbol=symbol).first()
            if not cached:
                cached = StockPrice(symbol=symbol)
                db.session.add(cached)
            cached.current_price = float(price_data['price'])
            cached.change = float(price_data.get('change', 0))
            cached.change_percent = float(price_data.get('change_percent', 0))
            cached.last_updated = datetime.utcnow()
            db.session.commit()

    def get_stock_price(self, symbol):
        cached_price = self._get_from_cache(symbol)
        if cached_price: return cached_price
        price_data = None
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="2d", auto_adjust=True)
            if not hist.empty and len(hist) >= 2:
                price_data = {
                    'price': float(hist['Close'].iloc[-1]),
                    'change': float(hist['Close'].iloc[-1] - hist['Close'].iloc[-2]),
                    'change_percent': float((hist['Close'].iloc[-1] / hist['Close'].iloc[-2] - 1) * 100)
                }
            elif not hist.empty:
                price_data = {'price': float(hist['Close'].iloc[-1]), 'change': 0, 'change_percent': 0}
        except Exception as e:
            logger.error(f"yfinance 가격 조회 실패 ({symbol}): {e}")
        
        if price_data: 
            self._update_cache(symbol, price_data)
        
        return price_data
    
    def get_stock_profile(self, symbol):
        if symbol in PROFILE_CACHE and (datetime.now() - PROFILE_CACHE[symbol].get('timestamp', datetime.min)).days < 1:
            return PROFILE_CACHE[symbol]

        profile_data = {'sector': 'N/A', 'name': symbol, 'logo': None}
        try:
            info = yf.Ticker(symbol).info
            profile_data['name'] = info.get('longName', symbol)
            profile_data['sector'] = info.get('sector', 'N/A')
            if info.get('quoteType') == 'ETF':
                profile_data['sector'] = 'ETF'
            
            profile_data['timestamp'] = datetime.now()
            PROFILE_CACHE[symbol] = profile_data
            
        except Exception as e:
            logger.warning(f"프로필 조회 실패 ({symbol}): {e}")
            # 실패 시에도 기본값 캐싱 (짧은 시간)
            profile_data['timestamp'] = datetime.now()
            PROFILE_CACHE[symbol] = profile_data

        return profile_data

    # 신규 기능: 특정 기간의 시세 기록을 가져오는 함수
    def get_price_history(self, symbol, period='6mo'):
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period, auto_adjust=True)
            if hist.empty:
                return None
            
            # Chart.js가 사용할 수 있는 형식으로 데이터 가공
            hist.index = hist.index.strftime('%Y-%m-%d')
            return {
                'dates': list(hist.index),
                'prices': [round(p, 2) for p in hist['Close']]
            }
        except Exception as e:
            logger.error(f"시세 기록 조회 실패 ({symbol}): {e}")
            return None


stock_api = StockAPIService()```

#### 📄 utils.py
*(변경 사항: SCHD와 같은 ETF의 배당금 계산을 위해 `yield`를 활용하는 폴백 로직 추가)*

```python
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
            
            # 1. 'dividendRate' (연간 주당 배당금) 직접 조회
            annual_dps = float(info.get('trailingAnnualDividendRate') or info.get('dividendRate') or 0)
            current_price = price_data_map.get(symbol, {}).get('price')

            # 2. [SCHD 문제 해결] dividendRate가 없는 ETF를 위한 폴백 로직
            #    yield 값과 현재가를 곱해 연간 주당 배당금을 추정
            if annual_dps == 0 and info.get('yield') and current_price:
                annual_dps = float(info['yield']) * current_price

            if annual_dps > 0:
                expected_annual_dividend = annual_dps * h.quantity
                
                # 수익률 계산: 추정된 DPS를 현재가로 나눔
                dividend_yield = (annual_dps / current_price) * 100 if current_price and current_price > 0 else 0
                
                dividend_metrics[symbol] = {
                    'expected_annual_dividend': expected_annual_dividend,
                    'dividend_yield': dividend_yield
                }
        except Exception as e:
            logger.warning(f"({symbol}) 배당 지표 계산 실패: {e}")
            # 실패 시 빈 딕셔너리 추가 방지
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
        actions = ticker.actions
        if actions is not None and not actions.empty and 'Dividends' in actions.columns and actions['Dividends'].sum() > 0:
            ex_dividend_dates = actions[actions['Dividends'] > 0].index
            
            ex_dividend_dates_naive = ex_dividend_dates.tz_convert(None) if ex_dividend_dates.tz is not None else ex_dividend_dates
            
            start_date = pd.to_datetime(datetime.now() - timedelta(days=540))
            recent_ex_dates = ex_dividend_dates_naive[ex_dividend_dates_naive > start_date]
            
            if not recent_ex_dates.empty:
                paid_months = sorted(list(set(recent_ex_dates.month)))
                
                # 분기 배당주 보정 로직 (e.g. 3,6,9,12월 배당인데 최근 1-2번만 잡힐 경우)
                if len(paid_months) > 0 and len(paid_months) < 4:
                    # 월 간격이 3에 가까운지 확인
                    intervals = [j-i for i, j in zip(paid_months[:-1], paid_months[1:])]
                    if all(i % 3 == 0 for i in intervals):
                         # 대표적인 분기 배당월(3,6,9,12) 중 하나라도 포함되면 강제 지정
                        if any(m in [3,6,9,12] for m in paid_months):
                            paid_months = [3, 6, 9, 12]

                month_names = [MONTH_NUMBER_TO_NAME.get(m, '') for m in paid_months]
                DIVIDEND_MONTH_CACHE[upper_symbol] = month_names
                return month_names
    except Exception as e:
        logger.warning(f"({upper_symbol}) 배당 월 정보 조회 실패: {e}")

    DIVIDEND_MONTH_CACHE[upper_symbol] = []
    return []
