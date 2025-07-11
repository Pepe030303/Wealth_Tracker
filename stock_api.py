# stock_api.py

import os
import requests
import logging
from datetime import datetime, timedelta
from app import db
from models import StockPrice
import yfinance as yf

logger = logging.getLogger(__name__)

TICKER_TO_CIK_MAP = {}
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

def load_ticker_to_cik_map():
    global TICKER_TO_CIK_MAP
    if TICKER_TO_CIK_MAP: return
    try:
        headers = {'User-Agent': 'WealthTracker/1.0 (dev@example.com)'}
        url = "https://www.sec.gov/files/company_tickers.json"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        all_companies = response.json()
        TICKER_TO_CIK_MAP = {data['ticker']: str(data['cik_str']).zfill(10) for data in all_companies.values()}
        logger.info(f"Ticker-CIK 매핑 {len(TICKER_TO_CIK_MAP)}개 로드 완료.")
    except Exception as e:
        logger.error(f"Ticker-CIK 매핑 파일 로드 실패: {e}")

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
            cached.current_price = price_data['price']
            cached.change = price_data.get('change', 0)
            cached.change_percent = price_data.get('change_percent', 0)
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
        if price_data: self._update_cache(symbol, price_data)
        return price_data
    
    def get_stock_profile(self, symbol):
        if symbol in PROFILE_CACHE: return PROFILE_CACHE[symbol]
        cik = TICKER_TO_CIK_MAP.get(symbol.upper())
        if not cik: return {'sector': 'N/A', 'logo': None}
        try:
            headers = {'User-Agent': 'WealthTracker/1.0 (dev@example.com)'}
            url = f"https://data.sec.gov/submissions/CIK{cik}.json"
            response = self.session.get(url, headers=headers, timeout=5)
            response.raise_for_status()
            data = response.json()
            profile = {'sector': get_sector_from_sic(data.get('sic')), 'logo': None}
            PROFILE_CACHE[symbol] = profile
            return profile
        except Exception as e:
            logger.error(f"EDGAR API 프로필 조회 실패 ({symbol}): {e}")
            return {'sector': 'N/A', 'logo': None}

stock_api = StockAPIService()
