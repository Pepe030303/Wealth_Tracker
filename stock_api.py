# stock_api.py

import os
import requests
import logging
from datetime import datetime, timedelta
from app import db
from models import StockPrice
import yfinance as yf
import json

logger = logging.getLogger(__name__)

# --- EDGAR API 관련 설정 ---
# Ticker -> CIK 매핑 데이터. 앱 시작 시 한 번만 로드됩니다.
TICKER_TO_CIK_MAP = {}
# 각 Ticker별 프로필 정보를 메모리에 캐싱하여 중복 API 호출 방지
PROFILE_CACHE = {}

# SIC 코드를 사람이 이해하기 쉬운 섹터로 매핑 (간소화 버전)
# 출처: https://www.sec.gov/info/edgar/siccodes.htm
SIC_TO_SECTOR_MAP = {
    '1000-1499': 'Mining',
    '1500-1799': 'Construction',
    '2000-3999': 'Manufacturing',
    '4000-4999': 'Transportation & Public Utilities',
    '5000-5199': 'Wholesale Trade',
    '5200-5999': 'Retail Trade',
    '6000-6799': 'Finance, Insurance, Real Estate',
    '7000-8999': 'Services',
    '9100-9729': 'Public Administration',
    '9900-9999': 'Nonclassifiable'
}

def get_sector_from_sic(sic_code):
    """SIC 코드를 기반으로 섹터 이름을 반환합니다."""
    if not sic_code: return 'N/A'
    try:
        sic = int(sic_code)
        for sic_range, sector in SIC_TO_SECTOR_MAP.items():
            start, end = map(int, sic_range.split('-'))
            if start <= sic <= end:
                return sector
    except (ValueError, TypeError):
        return 'N/A'
    return 'N/A'

def load_ticker_to_cik_map():
    """앱 시작 시 SEC로부터 Ticker-CIK 매핑 파일을 다운로드하여 메모리에 로드합니다."""
    global TICKER_TO_CIK_MAP
    if TICKER_TO_CIK_MAP:  # 이미 로드되었다면 실행하지 않음
        return
    try:
        headers = {'User-Agent': 'YourAppName YourEmail@example.com'}
        url = "https://www.sec.gov/files/company_tickers.json"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        # 데이터 구조: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
        all_companies = response.json()
        # Ticker를 key로, CIK를 value로 하는 딕셔너리 생성
        TICKER_TO_CIK_MAP = {
            data['ticker']: str(data['cik_str']).zfill(10) # 10자리로 맞춤
            for key, data in all_companies.items()
        }
        logger.info("Ticker-CIK 매핑 로드 완료.")
    except Exception as e:
        logger.error(f"Ticker-CIK 매핑 파일 로드 실패: {e}")


class StockAPIService:
    def __init__(self):
        self.session = requests.Session()
        # 앱 시작 시 매핑 파일 로드
        load_ticker_to_cik_map()

    def _get_from_cache(self, symbol):
        """DB 캐시에서 주가 정보 확인"""
        cached = StockPrice.query.filter_by(symbol=symbol).first()
        if cached and (datetime.utcnow() - cached.last_updated) < timedelta(minutes=15):
            return {'price': cached.current_price, 'change': cached.change, 'change_percent': cached.change_percent}
        return None

    def _update_cache(self, symbol, price_data):
        """DB 캐시 업데이트"""
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
        """주가 정보 조회 (캐시 -> yfinance)"""
        cached_price = self._get_from_cache(symbol)
        if cached_price:
            return cached_price

        price_data = None
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="2d")
            if not hist.empty and len(hist) >= 2:
                price_data = {
                    'price': hist['Close'].iloc[-1],
                    'change': hist['Close'].iloc[-1] - hist['Close'].iloc[-2],
                    'change_percent': (hist['Close'].iloc[-1] / hist['Close'].iloc[-2] - 1) * 100
                }
            elif not hist.empty: # 데이터가 하나만 있을 경우
                price_data = {'price': hist['Close'].iloc[-1], 'change': 0, 'change_percent': 0}
        except Exception as e:
            logger.error(f"yfinance 가격 조회 실패 ({symbol}): {e}")

        if price_data:
            self._update_cache(symbol, price_data)
        
        return price_data
    
    def get_stock_profile(self, symbol):
        """종목 프로필(섹터) 정보 조회 (EDGAR API 사용)"""
        # 메모리 캐시 확인
        if symbol in PROFILE_CACHE:
            return PROFILE_CACHE[symbol]

        # 1. Ticker를 CIK로 변환
        cik = TICKER_TO_CIK_MAP.get(symbol.upper())
        if not cik:
            logger.warning(f"CIK를 찾을 수 없음: {symbol}")
            return {'sector': 'N/A', 'logo': None}

        # 2. EDGAR API 호출
        try:
            headers = {'User-Agent': 'YourAppName YourEmail@example.com'}
            url = f"https://data.sec.gov/submissions/CIK{cik}.json"
            response = self.session.get(url, headers=headers, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            sic = data.get('sic')
            sector = get_sector_from_sic(sic)

            profile = {'sector': sector, 'logo': None} # EDGAR는 로고를 제공하지 않음
            
            # 메모리 캐시에 저장
            PROFILE_CACHE[symbol] = profile
            return profile

        except Exception as e:
            logger.error(f"EDGAR API 프로필 조회 실패 ({symbol}): {e}")
            return {'sector': 'N/A', 'logo': None}

# 전역 인스턴스 생성
stock_api = StockAPIService()
