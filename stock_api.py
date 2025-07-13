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
import time

try:
    from app import conn as redis_conn
except ImportError:
    redis_conn = None
    logging.warning("Redis 연결을 가져오지 못했습니다. 캐싱이 비활성화됩니다.")

logger = logging.getLogger(__name__)

US_STOCKS_LIST = []
US_STOCKS_FILE = 'us_stocks.json'

def load_us_stocks_data():
    global US_STOCKS_LIST
    if US_STOCKS_LIST: return
    try:
        # ... (기존과 동일)
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
        if not US_STOCKS_LIST and os.path.exists(US_STOCKS_FILE):
             with open(US_STOCKS_FILE, 'r') as f:
                US_STOCKS_LIST = json.load(f)
             logger.warning("API 실패. 기존 로컬 캐시 파일을 사용합니다.")


class StockAPIService:
    def __init__(self, redis_client: Redis):
        self.session = requests.Session()
        self.cache = redis_client
        self.cache_ttl = timedelta(minutes=30)

    def _get_from_redis_cache(self, key):
        if not self.cache: return None
        cached = self.cache.get(key)
        return json.loads(cached) if cached else None

    def _set_to_redis_cache(self, key, value):
        if not self.cache: return
        self.cache.setex(key, self.cache_ttl, json.dumps(value))

    # 🛠️ 개선: 여러 종목의 가격 정보를 한번에 가져오는 벌크 메서드
    def get_stock_prices_bulk(self, symbols: list):
        if not symbols: return {}
        
        # Redis에서 캐시된 데이터를 먼저 확인
        results = {}
        symbols_to_fetch = []
        for symbol in symbols:
            cache_key = f"price:{symbol}"
            cached_price = self._get_from_redis_cache(cache_key)
            if cached_price:
                results[symbol] = cached_price
            else:
                symbols_to_fetch.append(symbol)
        
        if not symbols_to_fetch:
            return results

        # 캐시가 없는 종목들에 대해 yfinance 벌크 호출
        try:
            tickers_str = " ".join(symbols_to_fetch)
            tickers = yf.Tickers(tickers_str)
            for symbol, ticker_obj in tickers.tickers.items():
                hist = ticker_obj.history(period="2d", auto_adjust=True, progress=False)
                if not hist.empty and len(hist) >= 2:
                    price_data = {
                        'price': float(hist['Close'].iloc[-1]),
                        'change': float(hist['Close'].iloc[-1] - hist['Close'].iloc[-2]),
                        'change_percent': float((hist['Close'].iloc[-1] / hist['Close'].iloc[-2] - 1) * 100)
                    }
                elif not hist.empty:
                    price_data = {'price': float(hist['Close'].iloc[-1]), 'change': 0, 'change_percent': 0}
                else:
                    continue # 데이터가 없으면 건너뜀

                results[symbol] = price_data
                self._set_to_redis_cache(f"price:{symbol}", price_data)
                self._update_db_cache(symbol, price_data)

        except Exception as e:
            logger.error(f"yfinance 벌크 가격 조회 실패 ({symbols_to_fetch}): {e}")

        return results
        
    # 🛠️ 개선: 여러 종목의 프로필 정보를 한번에 가져오는 벌크 메서드
    def get_stock_profiles_bulk(self, symbols: list):
        if not symbols: return {}

        results = {}
        symbols_to_fetch = []
        for symbol in symbols:
            cache_key = f"profile:{symbol}"
            cached_profile = self._get_from_redis_cache(cache_key)
            if cached_profile:
                results[symbol] = cached_profile
            else:
                symbols_to_fetch.append(symbol)

        if not symbols_to_fetch:
            return results
        
        try:
            tickers_str = " ".join(symbols_to_fetch)
            tickers = yf.Tickers(tickers_str)
            for symbol, ticker_obj in tickers.tickers.items():
                try:
                    # 개별 티커에 대한 .info 호출은 여전히 필요
                    info = ticker_obj.info
                    profile_data = {
                        'name': info.get('longName', symbol),
                        'sector': info.get('sector', 'ETF' if info.get('quoteType') == 'ETF' else 'N/A'),
                        'logo_url': info.get('logo_url')
                    }
                except Exception:
                     profile_data = {'name': symbol, 'sector': 'N/A', 'logo_url': None}

                results[symbol] = profile_data
                self._set_to_redis_cache(f"profile:{symbol}", profile_data)
        except Exception as e:
            logger.error(f"yfinance 벌크 프로필 조회 실패 ({symbols_to_fetch}): {e}")

        return results

    # 단일 조회 메서드는 검색 상세 페이지 등을 위해 유지
    def get_stock_price(self, symbol):
        # ... (기존 로직 유지, 단 Rate limit 방지를 위해 sleep 추가)
        time.sleep(0.1) # 짧은 딜레이 추가
        cache_key = f"price:{symbol}"
        # ... (이하 로직 동일)
        cached_price = self._get_from_redis_cache(cache_key)
        if cached_price: return cached_price
        
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
            # 🛠️ Fixed: API 실패 시 DB 캐시 객체를 그대로 반환하도록 수정
            if db_cached:
                return {'price': db_cached.current_price, 'change': db_cached.change, 'change_percent': db_cached.change_percent}
            return None

        self._set_to_redis_cache(cache_key, price_data)
        self._update_db_cache(symbol, price_data)
        return price_data

    def get_stock_profile(self, symbol):
        # ... (기존 로직 유지, 단 Rate limit 방지를 위해 sleep 추가)
        time.sleep(0.1) # 짧은 딜레이 추가
        cache_key = f"profile:{symbol}"
        # ... (이하 로직 동일)
        cached_profile = self._get_from_redis_cache(cache_key)
        if cached_profile: return cached_profile

        try:
            info = yf.Ticker(symbol).info
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

    # ... (기타 메서드)
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
