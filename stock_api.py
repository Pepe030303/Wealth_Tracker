import os
import requests
import logging
from datetime import datetime, timedelta
from app import db
from models import StockPrice

logger = logging.getLogger(__name__)

class StockAPIService:
    def __init__(self):
        # Try different API services with fallback
        self.alpha_vantage_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
        self.iex_cloud_key = os.environ.get("IEX_CLOUD_API_KEY")
        self.finnhub_key = os.environ.get("FINNHUB_API_KEY")
        
    def get_stock_price(self, symbol):
        """주식 가격 조회 (캐시된 데이터 먼저 확인)"""
        try:
            # 캐시된 데이터 확인 (5분 이내)
            cached_price = StockPrice.query.filter_by(symbol=symbol).first()
            if cached_price and (datetime.utcnow() - cached_price.last_updated) < timedelta(minutes=5):
                return {
                    'symbol': symbol,
                    'price': cached_price.current_price,
                    'change': cached_price.change,
                    'change_percent': cached_price.change_percent
                }
            
            # API에서 실시간 데이터 가져오기
            price_data = self._fetch_from_api(symbol)
            if price_data:
                # 캐시 업데이트
                self._update_cache(symbol, price_data)
                return price_data
            
            # API 실패 시 캐시된 데이터 반환
            if cached_price:
                return {
                    'symbol': symbol,
                    'price': cached_price.current_price,
                    'change': cached_price.change,
                    'change_percent': cached_price.change_percent
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting stock price for {symbol}: {e}")
            return None
    
    def _fetch_from_api(self, symbol):
        """외부 API에서 주가 데이터 가져오기"""
        # Alpha Vantage API 시도
        if self.alpha_vantage_key:
            try:
                return self._fetch_alpha_vantage(symbol)
            except Exception as e:
                logger.error(f"Alpha Vantage API error: {e}")
        
        # IEX Cloud API 시도
        if self.iex_cloud_key:
            try:
                return self._fetch_iex_cloud(symbol)
            except Exception as e:
                logger.error(f"IEX Cloud API error: {e}")
        
        # Finnhub API 시도
        if self.finnhub_key:
            try:
                return self._fetch_finnhub(symbol)
            except Exception as e:
                logger.error(f"Finnhub API error: {e}")
        
        # 무료 API 사용 (제한적)
        try:
            return self._fetch_free_api(symbol)
        except Exception as e:
            logger.error(f"Free API error: {e}")
        
        return None
    
    def _fetch_alpha_vantage(self, symbol):
        """Alpha Vantage API"""
        url = f"https://www.alphavantage.co/query"
        params = {
            'function': 'GLOBAL_QUOTE',
            'symbol': symbol,
            'apikey': self.alpha_vantage_key
        }
        
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if 'Global Quote' in data:
            quote = data['Global Quote']
            return {
                'symbol': symbol,
                'price': float(quote['05. price']),
                'change': float(quote['09. change']),
                'change_percent': float(quote['10. change percent'].replace('%', ''))
            }
        
        return None
    
    def _fetch_iex_cloud(self, symbol):
        """IEX Cloud API"""
        url = f"https://cloud.iexapis.com/stable/stock/{symbol}/quote"
        params = {'token': self.iex_cloud_key}
        
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        return {
            'symbol': symbol,
            'price': float(data['latestPrice']),
            'change': float(data['change']),
            'change_percent': float(data['changePercent']) * 100
        }
    
    def _fetch_finnhub(self, symbol):
        """Finnhub API"""
        url = f"https://finnhub.io/api/v1/quote"
        params = {
            'symbol': symbol,
            'token': self.finnhub_key
        }
        
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        current_price = float(data['c'])
        previous_close = float(data['pc'])
        change = current_price - previous_close
        change_percent = (change / previous_close) * 100
        
        return {
            'symbol': symbol,
            'price': current_price,
            'change': change,
            'change_percent': change_percent
        }
    
    def _fetch_free_api(self, symbol):
        """무료 API (제한적이지만 기본 기능용)"""
        # Yahoo Finance 무료 API 사용
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        
        if 'chart' in data and 'result' in data['chart'] and data['chart']['result']:
            result = data['chart']['result'][0]
            meta = result['meta']
            
            current_price = float(meta['regularMarketPrice'])
            previous_close = float(meta['previousClose'])
            change = current_price - previous_close
            change_percent = (change / previous_close) * 100
            
            return {
                'symbol': symbol,
                'price': current_price,
                'change': change,
                'change_percent': change_percent
            }
        
        return None
    
    def _update_cache(self, symbol, price_data):
        """캐시 업데이트"""
        try:
            stock_price = StockPrice.query.filter_by(symbol=symbol).first()
            if not stock_price:
                stock_price = StockPrice(symbol=symbol)
                db.session.add(stock_price)
            
            stock_price.current_price = price_data['price']
            stock_price.change = price_data['change']
            stock_price.change_percent = price_data['change_percent']
            stock_price.last_updated = datetime.utcnow()
            
            db.session.commit()
            
        except Exception as e:
            logger.error(f"Error updating cache for {symbol}: {e}")
            db.session.rollback()

# 전역 인스턴스
stock_api = StockAPIService()
