# models.py

from datetime import datetime
from sqlalchemy import func, extract
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
import logging
import yfinance as yf

logger = logging.getLogger(__name__)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=False)
    email = db.Column(db.String(120), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    def set_password(self, p): self.password_hash = generate_password_hash(p)
    def check_password(self, p): return check_password_hash(self.password_hash, p)
    def __repr__(self): return f'<User {self.username}>'

class Trade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False, index=True)
    trade_type = db.Column(db.String(10), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    price = db.Column(db.Float, nullable=False)
    trade_date = db.Column(db.Date, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    user = db.relationship('User', backref=db.backref('trades', lazy='dynamic'))

class Holding(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False, index=True)
    quantity = db.Column(db.Float, nullable=False)
    purchase_price = db.Column(db.Float, nullable=False)
    purchase_date = db.Column(db.DateTime)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    user = db.relationship('User', backref=db.backref('holdings', lazy='dynamic'))

class Dividend(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False)
    amount_per_share = db.Column(db.Float, nullable=True)
    dividend_date = db.Column(db.Date, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    user = db.relationship('User', backref=db.backref('dividends', lazy='dynamic'))

class StockPrice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False, unique=True, index=True)
    current_price = db.Column(db.Float, nullable=False)
    change = db.Column(db.Float, default=0.0)
    change_percent = db.Column(db.Float, default=0.0)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

class DividendUpdateCache(db.Model):
    """사용자별 배당금 업데이트 시점을 기록하는 캐시 테이블"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', name='_user_id_uc'),)

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
        # yfinance에서 직접 최신 배당 정보를 가져옵니다 (DB 의존성 제거)
        try:
            ticker = yf.Ticker(h.symbol)
            # 가장 최근의 주당 배당금
            dps = ticker.dividends.iloc[-1] if not ticker.dividends.empty else 0
            # 연간 배당 횟수 (보통 4회로 가정, REITs 등은 다를 수 있음)
            payout_frequency = 4
            if dps > 0:
                expected_annual_dividend = float(dps) * h.quantity * payout_frequency
                price_data = stock_api.get_stock_price(h.symbol)
                if price_data and price_data.get('price'):
                    current_market_value = price_data['price'] * h.quantity
                    dividend_yield = (expected_annual_dividend / current_market_value) * 100 if current_market_value > 0 else 0
                else:
                    dividend_yield = 0
                dividend_metrics[h.symbol] = {'expected_annual_dividend': expected_annual_dividend, 'dividend_yield': dividend_yield}
        except Exception as e:
            logger.warning(f"{h.symbol}의 배당 지표 계산 실패: {e}")
            continue
    return dividend_metrics

def get_dividend_allocation_data(user_id):
    metrics = calculate_dividend_metrics(user_id)
    return [{'symbol': s, 'value': m['expected_annual_dividend']} for s, m in metrics.items() if m['expected_annual_dividend'] > 0]

DIVIDEND_MONTHS = {'AAPL': ['Feb', 'May', 'Aug', 'Nov'], 'MSFT': ['Mar', 'Jun', 'Sep', 'Dec'], 'JPM': ['Jan', 'Apr', 'Jul', 'Oct'], 'JNJ': ['Mar', 'Jun', 'Sep', 'Dec'], 'KO': ['Apr', 'Jul', 'Oct', 'Dec'], 'O': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']}
def get_dividend_months(symbol): return DIVIDEND_MONTHS.get(symbol, [])
