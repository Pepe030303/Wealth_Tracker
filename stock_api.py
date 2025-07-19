# 📄 stock_api.py

import os
import requests
import logging
import json
from datetime import datetime, timedelta
# 🛠️ Refactor: app 대신 extensions에서 db, redis_conn 객체를 가져옵니다.
from extensions import db, redis_conn
from models import StockPrice
import yfinance as yf
import pandas as pd
from redis import Redis

logger = logging.getLogger(__name__)

US_STOCKS_LIST = []
US_STOCKS_FILE = 'us_stocks.json'

def load_us_stocks_data():
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
    except requests.exceptions.RequestException as e:
        logger.error(f"SEC API 네트워크 오류: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"SEC API 응답 JSON 파싱 오류: {e}")
    except Exception as e:
        logger.error(f"SEC 기업 티커 데이터 로드 중 예상치 못한 오류: {e}")

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

    def _fetch_data_from_yfinance_bulk(self, symbols: list, data_type: str):
        """
        [내부 헬퍼] yfinance API를 통해 데이터를 일괄 조회하고 파싱합니다.
        - data_type: 'price' 또는 'profile'
        - 개별 종목의 오류가 전체 요청을 중단시키지 않도록 처리합니다.
        """
        if not symbols: return {}
        
        results = {}
        try:
            tickers = yf.Tickers(" ".join(symbols))
            for symbol in symbols:
                try:
                    ticker_obj = tickers.tickers.get(symbol.upper())
                    if not ticker_obj or not hasattr(ticker_obj, 'info'): continue

                    if data_type == 'price':
                        hist = ticker_obj.history(period="2d", auto_adjust=True)
                        if not hist.empty and len(hist) >= 2:
                            results[symbol] = {
                                'price': float(hist['Close'].iloc[-1]),
                                'change': float(hist['Close'].iloc[-1] - hist['Close'].iloc[-2]),
                                'change_percent': float((hist['Close'].iloc[-1] / hist['Close'].iloc[-2] - 1) * 100)
                            }
                        elif not hist.empty:
                            results[symbol] = {'price': float(hist['Close'].iloc[-1]), 'change': 0, 'change_percent': 0}
                    
                    elif data_type == 'profile':
                        info = ticker_obj.info
                        if info and info.get('quoteType'):
                            results[symbol] = {
                                'name': info.get('longName', symbol),
                                'sector': info.get('sector', 'ETF' if info.get('quoteType') == 'ETF' else 'N/A'),
                                'logo_url': info.get('logo_url')
                            }
                        else: # 프로필 정보가 비어있을 경우 기본값 제공
                            results[symbol] = {'name': symbol, 'sector': 'N/A', 'logo_url': None}

                except (KeyError, IndexError, TypeError) as e:
                    logger.warning(f"yfinance 벌크 파싱 오류 ({data_type}, {symbol}): {e}")
                except Exception as e:
                    logger.error(f"yfinance 벌크 조회 중 예상치 못한 내부 오류 ({data_type}, {symbol}): {e}")

        except Exception as e:
            logger.error(f"yfinance 벌크 API 호출 실패 ({data_type}, {symbols}): {e}")
        
        return results

    def get_stock_prices_bulk(self, symbols: list):
        if not symbols: return {}
        
        results = {}
        symbols_to_fetch = []

        # 1. Redis 캐시에서 데이터 조회
        for symbol in symbols:
            if cached_data := self._get_from_redis_cache(f"price:{symbol}"):
                results[symbol] = cached_data
            else:
                symbols_to_fetch.append(symbol)
        
        # 2. 캐시에 없는 데이터는 API를 통해 조회
        if symbols_to_fetch:
            api_results = self._fetch_data_from_yfinance_bulk(symbols_to_fetch, 'price')
            
            # 3. API 결과를 캐시(Redis, DB)에 저장하고 최종 결과에 통합
            for symbol, price_data in api_results.items():
                self._set_to_redis_cache(f"price:{symbol}", price_data)
                self._update_db_cache(symbol, price_data)
                results[symbol] = price_data

        return results
        
    def get_stock_profiles_bulk(self, symbols: list):
        if not symbols: return {}

        results = {}
        symbols_to_fetch = []

        # 1. Redis 캐시에서 데이터 조회
        for symbol in symbols:
            if cached_data := self._get_from_redis_cache(f"profile:{symbol}"):
                results[symbol] = cached_data
            else:
                symbols_to_fetch.append(symbol)

        # 2. 캐시에 없는 데이터는 API를 통해 조회
        if symbols_to_fetch:
            api_results = self._fetch_data_from_yfinance_bulk(symbols_to_fetch, 'profile')
            
            # 3. API 결과를 캐시(Redis)에 저장하고 최종 결과에 통합
            for symbol, profile_data in api_results.items():
                self._set_to_redis_cache(f"profile:{symbol}", profile_data)
                results[symbol] = profile_data
        
        # 4. 프로필 조회 실패한 경우에도 기본값 제공
        for symbol in symbols_to_fetch:
            if symbol not in results:
                results[symbol] = {'name': symbol, 'sector': 'N/A', 'logo_url': None}

        return results

    def get_stock_price(self, symbol):
        cache_key = f"price:{symbol}"
        if cached := self._get_from_redis_cache(cache_key): 
            return cached
        
        api_result_map = self.get_stock_prices_bulk([symbol])
        if api_result := api_result_map.get(symbol):
            return api_result

        if db_cached := StockPrice.query.filter_by(symbol=symbol).first():
            if (datetime.utcnow() - db_cached.last_updated) < self.cache_ttl:
                price_data = {'price': db_cached.current_price, 'change': db_cached.change, 'change_percent': db_cached.change_percent}
                self._set_to_redis_cache(cache_key, price_data) 
                return price_data
            
        return None

    def get_stock_profile(self, symbol):
        cache_key = f"profile:{symbol}"
        if cached := self._get_from_redis_cache(cache_key): 
            return cached

        api_result_map = self.get_stock_profiles_bulk([symbol])
        return api_result_map.get(symbol)

    def get_price_history(self, symbol, period='6mo'):
        cache_key = f"history:{symbol}:{period}"
        if cached := self._get_from_redis_cache(cache_key): return cached
        try:
            hist = yf.Ticker(symbol).history(period=period, auto_adjust=True)
            if hist.empty: return None
            hist.index = hist.index.strftime('%Y-%m-%d')
            price_history = {'dates': list(hist.index), 'prices': [round(p, 2) for p in hist['Close']]}
        except requests.exceptions.HTTPError as http_err:
            logger.warning(f"yfinance 시세 기록 조회 실패 (HTTP 오류) ({symbol}): {http_err}")
            return None
        except Exception as e:
            logger.error(f"yfinance 시세 기록 조회 중 예상치 못한 오류 ({symbol}): {e}")
            return None
        self._set_to_redis_cache(cache_key, price_history)
        return price_history

stock_api = StockAPIService(redis_conn)
