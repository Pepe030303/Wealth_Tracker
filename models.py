# models.py

from datetime import datetime, timedelta
from sqlalchemy import func, extract
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
import logging
import yfinance as yf
import pandas as pd

logger = logging.getLogger(__name__)

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
    Holding.query.filter_by(queue:
                    if buy_queue[0]['quantity'] <= sell_quantity:
                        sell_quantity -=user_id=user_id).delete()
    symbols = db.session.query(Trade.symbol).filter_by buy_queue[0]['quantity']
                        buy_queue.pop(0)
                    else:
                        (user_id=user_id).distinct().all()
    for (symbol,) in symbols:
        buy_queue[0]['quantity'] -= sell_quantity
                        sell_quantity = 0
        final_trades = Trade.query.filter_by(symbol=symbol, user_id=user_id).order_quantity = sum(b['quantity'] for b in buy_queue)
        if final_quantity > 0by(Trade.trade_date, Trade.id).all()
        buy_queue = []
        for:
            final_cost = sum(b['quantity'] * b['price'] for b in buy_queue trade in trades:
            if trade.trade_type == 'buy':
                buy_queue.append({')
            avg_price = final_cost / final_quantity
            latest_buy_date = max(quantity': trade.quantity, 'price': trade.price, 'date': trade.trade_date})
            b['date'] for b in buy_queue) if buy_queue else None
            holding = Holding(symbolelif trade.trade_type == 'sell':
                sell_quantity = trade.quantity
                while sell_=symbol, quantity=final_quantity, purchase_price=avg_price, purchase_date=latest_buy_datequantity > 0 and buy_queue:
                    if buy_queue[0]['quantity'] <= sell_quantity:
                        sell_quantity -= buy_queue[0]['quantity']; buy_queue.pop(0)
, user_id=user_id)
            db.session.add(holding)
    db.session                    else:
                        buy_queue[0]['quantity'] -= sell_quantity; sell_quantity = 0.commit()

def calculate_dividend_metrics(user_id):
    holdings = Holding.query.
        final_quantity = sum(b['quantity'] for b in buy_queue)
        if final_quantity > filter_by(user_id=user_id).all()
    dividend_metrics = {}
    from0:
            final_cost = sum(b['quantity'] * b['price'] for b in buy_ stock_api import stock_api
    for h in holdings:
        try:
            ticker = yfqueue)
            avg_price = final_cost / final_quantity
            latest_buy_date = max.Ticker(h.symbol)
            info = ticker.info
            annual_dps = 0
(b['date'] for b in buy_queue) if buy_queue else None
            holding = Holding(            if info.get('quoteType') == 'ETF' and info.get('trailingAnnualDividendRate'):
symbol=symbol, quantity=final_quantity, purchase_price=avg_price, purchase_date=latest_buy_date, user_id=user_id)
            db.session.add(holding)
                    annual_dps = info.get('trailingAnnualDividendRate', 0)
            elif info.getdb.session.commit()

def get_dividend_allocation_data(dividend_metrics):
    return [{'symbol': s, 'value': m['expected_annual_dividend']} for s, m in dividend_metrics.items() if m.get('expected_annual_dividend', 0) > 0]


# --- 동적 배당 월 조회 기능 (배당락일 기준) ---

DIVIDEND_MONTH_CACHE = {}
MONTH_NUMBER_TO_NAME = {1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'}

def get_dividend_months(symbol):
    """
    API를 통해 종목의 배당락일(ex-dividend date)을 기준으로 배당 월을 동적으로 조회하고 캐싱합니다.
    """
    upper_symbol = symbol.upper()
    if upper_symbol in DIVIDEND_MONTH_CACHE:
        return DIVIDEND_MONTH_CACHE[upper_symbol]

    try:
        ticker = yf.Ticker(upper_symbol)
        
        # .actions는 배당(Dividends)과 주식 분할(Stock Splits) 정보를 모두 포함
        actions = ticker.actions
        if actions.empty or 'Dividends' not in actions.columns or actions['Dividends'].sum() == 0:
            DIVIDEND_MONTH_CACHE[upper_symbol] = []
            return []

        # 배당금이 0보다 큰 경우의 데이터만 필터링 (배당락일만 추출)
        ex_dividend_dates = actions[actions['Dividends'] > 0].index
        
        # 지난 15개월간의 배당락일만 필터링
        start_date = pd.to_datetime(datetime.now() - timedelta(days=450))
        # Pandas 인덱스는 시간대 정보가 있을 수 있으므로, 비교 전에 통일
        ex_dividend_dates_naive = ex_dividend_dates.tz_localize(None)
        recent_ex_dates = ex_dividend_dates_naive[ex_dividend_dates_naive > start_date]
        
        if recent_ex_dates.empty:
            DIVIDEND_MONTH_CACHE[upper_symbol] = []
            return []

        # 날짜에서 월(month)만 추출하여 중복을 제거하고 정렬합니다.
        paid_months = sorted(list(recent_ex_dates.month.unique()))
        
        # 월 숫자를 영문 이름으로 변환합니다.
        month_names = [MONTH_NUMBER_TO_NAME.get(m, '') for m in paid_months]
        
        # 결과를 캐시에 저장하고 반환합니다.
        DIVIDEND_MONTH_CACHE[upper_symbol] = month_names
        return month_names
        
    except Exception as e:
        logger.warning(f"{upper_symbol}의 배당 월 정보 조회 실패: {e}")
        # 실패 시 빈 리스트를 캐시에 저장하여 반복적인 실패 방지
        DIVIDEND_MONTH_CACHE[upper_symbol] = []
        return []
