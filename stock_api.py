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

def load_us_stocks_data():
    global US_STOCKS_LIST
    if US_STOCKS_LIST: return
    try:
        headers = {'User-Agent': 'WealthTracker/1.0 (dev@example.com)'}
        url = "https://www.sec.gov/files/company_tickers.json"
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        all_companies = response.json()
        
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
            profile_data['timestamp'] = datetime.now()
            PROFILE_CACHE[symbol] = profile_data

        return profile_data

    def get_price_history(self, symbol, period='6mo'):
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period, auto_adjust=True)
            if hist.empty:
                return None
            
            hist.index = hist.index.strftime('%Y-%m-%d')
            return {
                'dates': list(hist.index),
                'prices': [round(p, 2) for p in hist['Close']]
            }
        except Exception as e:
            logger.error(f"시세 기록 조회 실패 ({symbol}): {e}")
            return None


stock_api = StockAPIService()
