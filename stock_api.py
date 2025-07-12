# 📄 stock_api.py

import os
import requests
import logging
import json
from datetime import datetime, timedelta
from app import db
from models import StockPrice
import yfinance as yf
import pandas as pd
from redis import Redis

# 개선: Redis 연결을 외부에서 주입받아 사용
# app.py 에서 생성된 conn(Redis 클라이언트)을 가져옴
try:
    from app import conn as redis_conn
except ImportError:
    redis_conn = None
    logging.warning("Redis 연결을 가져오지 못했습니다. 캐싱이 비활성화됩니다.")


logger = logging.getLogger(__name__)

US_STOCKS_LIST = []
US_STOCKS_FILE = 'us_stocks.json'

def load_us_stocks_data():
    """
    개선: 앱 시작 안정성을 위해 SEC 데이터를 로컬 파일에 캐싱.
    - 파일이 존재하고 24시간 이내에 생성되었다면 파일에서 로드.
    - 그렇지 않으면 SEC API에서 가져와 파일에 저장 후 로드.
    """
    global US_STOCKS_LIST
    if US_STOCKS_LIST: return

    try:
        file_exists = os.path.exists(US_STOCKS_FILE)
        if file_exists:
            file_mod_time = datetime.fromtimestamp(os.path.getmtime(US_STOCKS_FILE))
            if (datetime.now() - file_mod_time) < timedelta(days=1):
                with open(US_STOCKS_FILE, 'r') as f:
                    US_STOCKS_LIST = json.load(f)
                logger.info(f"로컬 캐시 파일({US_STOCKS_FILE})에서 주식 데이터 {len(US_STOCKS_LIST)}개 로드 완료.")
                return

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
        
        with open(US_STOCKS_FILE, 'w') as f:
            json.dump(US_STOCKS_LIST, f)

        logger.info(f"SEC에서 주식 데이터 {len(US_STOCKS_LIST)}개 로드 및 파일 캐시 완료.")
    except Exception as e:
        logger.error(f"SEC 기업 티커 데이터 로드 실패: {e}")
        # API 실패 시에도 기존 파일이 있으면 사용
        if not US_STOCKS_LIST and os.path.exists(US_STOCKS_FILE):
             with open(US_STOCKS_FILE, 'r') as f:
                US_STOCKS_LIST = json.load(f)
             logger.warning("API 실패. 기존 로컬 캐시 파일을 사용합니다.")


class StockAPIService:
    def __init__(self, redis_client: Redis):
        self.session = requests.Session()
        # 개선: Redis 클라이언트를 생성자에서 주입받아 사용
        self.cache = redis_client
        # 캐시 만료 시간: 30분
        self.cache_ttl = timedelta(minutes=30)

    def _get_from_redis_cache(self, key):
        if not self.cache: return None
        cached = self.cache.get(key)
        return json.loads(cached) if cached else None

    def _set_to_redis_cache(self, key, value):
        if not self.cache: return
        self.cache.setex(key, self.cache_ttl, json.dumps(value))

    def get_stock_price(self, symbol):
        cache_key = f"price:{symbol}"
        cached_price = self._get_from_redis_cache(cache_key)
        if cached_price: return cached_price
        
        # DB 캐시 (폴백)
        db_cached = StockPrice.query.filter_by(symbol=symbol).first()
        if db_cached and (datetime.utcnow() - db_cached.last_updated) < self.cache_ttl:
            return {'price': db_cached.current_price, 'change': db_cached.change, 'change_percent': db_cached.change_percent}

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
            else:
                return None
        except Exception as e:
            logger.error(f"yfinance 가격 조회 실패 ({symbol}): {e}")
            return db_cached or None # API 실패 시 DB 캐시라도 반환

        # Redis와 DB에 모두 캐싱
        self._set_to_redis_cache(cache_key, price_data)
        self._update_db_cache(symbol, price_data)
        return price_data
    
    def _update_db_cache(self, symbol, price_data):
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
    
    def get_stock_profile(self, symbol):
        cache_key = f"profile:{symbol}"
        cached_profile = self._get_from_redis_cache(cache_key)
        if cached_profile: return cached_profile

        try:
            info = yf.Ticker(symbol).info
            # 🛠️ 기능 추가: 종목 프로필에 로고 URL을 포함하여 반환
            profile_data = {
                'name': info.get('longName', symbol),
                'sector': info.get('sector', 'ETF' if info.get('quoteType') == 'ETF' else 'N/A'),
                'logo_url': info.get('logo_url')
            }
        except Exception as e:
            logger.warning(f"프로필 조회 실패 ({symbol}): {e}")
            profile_data = {'name': symbol, 'sector': 'N/A', 'logo_url': None}

        self._set_to_redis_cache(cache_key, profile_data)
        return profile_data

    def get_price_history(self, symbol, period='6mo'):
        cache_key = f"history:{symbol}:{period}"
        cached_history = self._get_from_redis_cache(cache_key)
        if cached_history: return cached_history
        try:
            hist = yf.Ticker(symbol).history(period=period, auto_adjust=True)
            if hist.empty: return None
            
            hist.index = hist.index.strftime('%Y-%m-%d')
            price_history = {
                'dates': list(hist.index),
                'prices': [round(p, 2) for p in hist['Close']]
            }
        except Exception as e:
            logger.error(f"시세 기록 조회 실패 ({symbol}): {e}")
            return None
        
        self._set_to_redis_cache(cache_key, price_history)
        return price_history


stock_api = StockAPIService(redis_conn)
