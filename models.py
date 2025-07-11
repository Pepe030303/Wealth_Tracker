# models.py

import os
from datetime import datetime, timedelta
from sqlalchemy import func, extract
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
import logging
import yfinance as yf
import pandas as pd
import nasdaqdatalink

logger = logging.getLogger(__name__)

# --- Nasdaq API 설정 ---
try:
    nasdaqdatalink.ApiConfig.api_key = os.environ.get("NASDAQ_API_KEY")
except Exception as e:
    logger.error(f"Nasdaq API 키 설정 실패: {e}")

# --- (User, Trade, Holding, StockPrice, DividendUpdateCache 모델은 이전과 동일) ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=False)
    email = db.Column(db.String(120), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    def set_password(self, p): self.password_hash = generate_password_hash(p)
    def check_password(self, p): return check_password_hash(self.password_hash, p)

class Trade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False, index=True)
    trade_type = db.Column(db.String(10), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    price = db.Column(db.Float, nullable=False)
    trade_date = db.Column(db.Date, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)

class Holding(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False, index=True)
    quantity = db.Column(db.Float, nullable=False)
    purchase_price = db.Column(db.Float, nullable=False)
    purchase_date = db.Column(db.DateTime)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)

class Dividend(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False)
    amount_per_share = db.Column(db.Float, nullable=True)
    dividend_date = db.Column(db.Date, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)

class StockPrice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False, unique=True, index=True)
    current_price = db.Column(db.Float, nullable=False)
    change = db.Column(db.Float, default=0.0)
    change_percent = db.Column(db.Float, default=0.0)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

class DividendUpdateCache(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

def recalculate_holdings(user_id):
    Holding.query.filter_by(user_id=user_id).delete()
    symbols = db.session.query(Trade.symbol).filter_by(user_id=user_id).distinct().all()
    for (symbol,) in symbols:
        trades = Trade.query.filter_by(symbol=symbol, user_id=user_id).order_by(Trade.trade_date, Trade.id).all()
        buy_queue = []
        for trade in trades:
            if trade.trade_type == 'buy':
                buy_queue.append({'quantity': trade.quantity, 'price': trade.price, 'date': trade.trade_date})
            elif trade.trade_type == 'sell':
                sell_quantity = trade.quantity
                while sell_quantity > 0 and buy_queue:
                    if buy_queue[0]['quantity'] <= sell_quantity:
                        sell_quantity -= buy_queue[0]['quantity']; buy_queue.pop(0)
                    else:
                        buy_queue[0]['quantity'] -= sell_quantity; sell_quantity = 0
        final_quantity = sum(b['quantity'] for b in buy_queue)
        if final_quantity > 0:
            final_cost = sum(b['quantity'] * b['price'] for b in buy_queue)
            avg_price = final_cost / final_quantity
            latest_buy_date = max(b['date'] for b in buy_queue) if buy_queue else None
            holding = Holding(symbol=symbol, quantity=final_quantity, purchase_price=avg_price, purchase_date=latest_buy_date, user_id=user_id)
            db.session.add(holding)
    db.session.commit()

def calculate_dividend_metrics(user_id):
    holdings = Holding.query.filter_by(user_id=user_id).all()
    dividend_metrics = {}
    from stock_api import stock_api
    for h in holdings:
        try:
            ticker = yf.Ticker(h.symbol)
            info = ticker.info
            annual_dps = 0
            if info.get('quoteType') == 'ETF' and info.get('trailingAnnualDividendRate'):
                annual_dps = info.get('trailingAnnualDividendRate', 0)
            elif info.get('dividendRate'):
                annual_dps = info.get('dividendRate', 0)
            elif not ticker.dividends.empty:
                naive_dividends = ticker.dividends.tz_localize(None)
                last_year_dividends = naive_dividends[naive_dividends.index > datetime.now() - timedelta(days=365)]
                annual_dps = last_year_dividends.sum()
            
            if annual_dps > 0:
                expected_annual_dividend = float(annual_dps) * h.quantity
                price_data = stock_api.get_stock_price(h.symbol)
                if price_data and price_data.get('price') and price_data['price'] > 0:
                    dividend_yield = (annual_dps / price_data['price']) * 100
                else:
                    dividend_yield = info.get('yield', 0) * 100
                dividend_metrics[h.symbol] = {
                    'expected_annual_dividend': expected_annual_dividend,
                    'dividend_yield': dividend_yield
                }
        except Exception as e:
            logger.warning(f"{h.symbol}의 배당 지표 계산 실패: {e}")
            continue
    return dividend_metrics

def get_dividend_allocation_data(dividend_metrics):
    return [{'symbol': s, 'value': m['expected_annual_dividend']} for s, m in dividend_metrics.items() if m.get('expected_annual_dividend', 0) > 0]


# --- 동적 배당 월 조회 기능 (Nasdaq 우선) ---

DIVIDEND_MONTH_CACHE = {}
MONTH_NUMBER_TO_NAME = {1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'}

def get_dividend_months_from_nasdaq(symbol):
    """Nasdaq Data Link API를 사용하여 배당 월 조회"""
    try:
        # Mergent's dividend data (코드: MDB/D) 사용
        data = nasdaqdatalink.get_table('MDB/D', ticker=symbol, paginate=True)
        if data.empty or 'ex_date' not in data.columns:
            return None
        
        # 'ex_date'가 배당락일. 지난 15개월 데이터 필터링
        start_date = pd.to_datetime(datetime.now() - timedelta(days=450))
        recent_dividends = data[data['ex_date'] > start_date]
        if recent_dividends.empty:
            return None
            
        return sorted(list(recent_dividends['ex_date'].dt.month.unique()))
    except Exception as e:
        logger.info(f"Nasdaq API 조회 실패 ({symbol}): {e}")
        return None

def get_dividend_months_from_yfinance(symbol):
    """yfinance를 사용하여 배당 월 조회 (폴백용)"""
    try:
        ticker = yf.Ticker(symbol)
        actions = ticker.actions
        if actions.empty or 'Dividends' not in actions.columns or actions['Dividends'].sum() == 0:
            return None
        ex_dividend_dates = actions[actions['Dividends'] > 0].index
        start_date = pd.to_datetime(datetime.now() - timedelta(days=450))
        ex_dividend_dates_naive = ex_dividend_dates.tz_localize(None)
        recent_ex_dates = ex_dividend_dates_naive[ex_dividend_dates_naive > start_date]
        if recent_ex_dates.empty:
            return None
        return sorted(list(recent_ex_dates.month.unique()))
    except Exception as e:
        logger.warning(f"yfinance 배당 월 정보 조회 실패 ({symbol}): {e}")
        return None

def get_dividend_months(symbol):
    upper_symbol = symbol.upper()
    if upper_symbol in DIVIDEND_MONTH_CACHE:
        return DIVIDEND_MONTH_CACHE[upper_symbol]

    paid_months = None
    # 1. Nasdaq API 먼저 시도
    if nasdaqdatalink.ApiConfig.api_key:
        paid_months = get_dividend_months_from_nasdaq(upper_symbol)
    
    # 2. Nasdaq 실패 시 yfinance로 폴백
    if paid_months is None:
        paid_months = get_dividend_months_from_yfinance(upper_symbol)

    if paid_months:
        month_names = [MONTH_NUMBER_TO_NAME.get(m, '') for m in paid_months]
        DIVIDEND_MONTH_CACHE[upper_symbol] = month_names
        return month_names
    else:
        # 최종 실패 시 빈 리스트 캐싱
        DIVIDEND_MONTH_CACHE[upper_symbol] = []
        return []
