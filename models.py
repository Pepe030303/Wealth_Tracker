from datetime import datetime
from sqlalchemy import func
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
import yfinance as yf # 배당금 자동 업데이트를 위해 추가
import logging

logger = logging.getLogger(__name__)

# User 모델 추가 (Flask-Login과 호환되도록)
class User(UserMixin, db.Model):
    """사용자 정보"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=False)
    email = db.Column(db.String(120), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(256))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

# 기존 모델에 user_id 외래 키 추가
class Trade(db.Model):
    """거래 기록"""
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False)
    trade_type = db.Column(db.String(10), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    trade_date = db.Column(db.Date, nullable=False)
    # 사용자 연결
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('trades', lazy=True))

    def __repr__(self):
        return f'<Trade {self.symbol}: {self.trade_type} {self.quantity} @ ${self.price}>'

class Holding(db.Model):
    """보유 종목 정보"""
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    purchase_price = db.Column(db.Float, nullable=False)
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow)
    # 사용자 연결
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('holdings', lazy=True))

    def __repr__(self):
        return f'<Holding {self.symbol}: {self.quantity} shares at ${self.purchase_price}>'

class Dividend(db.Model):
    """배당금 기록"""
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    amount_per_share = db.Column(db.Float, nullable=True)
    dividend_date = db.Column(db.Date, nullable=False)
    ex_dividend_date = db.Column(db.Date, nullable=True)
    payout_frequency = db.Column(db.Integer, default=4)
    # 사용자 연결
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('dividends', lazy=True))

    def __repr__(self):
        return f'<Dividend {self.symbol}: ${self.amount} on {self.dividend_date}>'

    def get_amount_per_share(self):
        return self.amount_per_share if self.amount_per_share is not None else self.amount

class StockPrice(db.Model):
    """주가 캐시 (사용자별 데이터가 아니므로 변경 없음)"""
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False, unique=True)
    current_price = db.Column(db.Float, nullable=False)
    change = db.Column(db.Float, default=0.0)
    change_percent = db.Column(db.Float, default=0.0)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<StockPrice {self.symbol}: ${self.current_price}>'

# 모든 계산 함수가 user_id를 받도록 수정
def recalculate_holdings(user_id):
    """특정 사용자의 거래 기록으로부터 현재 보유 종목 재계산"""
    # 기존 보유 종목 데이터 삭제 (해당 사용자의 것만)
    Holding.query.filter_by(user_id=user_id).delete()
    
    # 심볼별 처리
    symbols = db.session.query(Trade.symbol).filter_by(user_id=user_id).distinct().all()
    
    for (symbol,) in symbols:
        trades = Trade.query.filter_by(symbol=symbol, user_id=user_id).order_by(Trade.trade_date, Trade.id).all()
        
        buy_queue = []
        total_quantity = 0
        total_cost = 0
        
        for trade in trades:
            if trade.trade_type == 'buy':
                buy_queue.append({'quantity': trade.quantity, 'price': trade.price, 'date': trade.trade_date})
            elif trade.trade_type == 'sell':
                sell_quantity = trade.quantity
                while sell_quantity > 0 and buy_queue:
                    buy_record = buy_queue[0]
                    if buy_record['quantity'] <= sell_quantity:
                        sell_quantity -= buy_record['quantity']
                        buy_queue.pop(0)
                    else:
                        buy_record['quantity'] -= sell_quantity
                        sell_quantity = 0

        # 남은 buy_queue로 현재 보유량과 평단가 계산
        final_quantity = sum(b['quantity'] for b in buy_queue)
        final_cost = sum(b['quantity'] * b['price'] for b in buy_queue)

        if final_quantity > 0:
            avg_price = final_cost / final_quantity
            latest_buy_date = max(b['date'] for b in buy_queue) if buy_queue else None

            holding = Holding(
                symbol=symbol,
                quantity=final_quantity,
                purchase_price=avg_price,
                purchase_date=latest_buy_date,
                user_id=user_id  # user_id 저장
            )
            db.session.add(holding)
    
    db.session.commit()

def calculate_dividend_metrics(user_id):
    """특정 사용자의 배당 관련 지표 계산"""
    holdings = Holding.query.filter_by(user_id=user_id).all()
    dividend_metrics = {}
    
    for holding in holdings:
        recent_dividend = Dividend.query.filter_by(symbol=holding.symbol, user_id=user_id).order_by(
            Dividend.dividend_date.desc()
        ).first()
        
        if recent_dividend:
            from stock_api import stock_api # 순환 참조 방지
            amount_per_share = recent_dividend.get_amount_per_share()
            expected_annual_dividend = amount_per_share * holding.quantity * recent_dividend.payout_frequency
            
            price_data = stock_api.get_stock_price(holding.symbol)
            if price_data:
                current_market_value = price_data['price'] * holding.quantity
                dividend_yield = (expected_annual_dividend / current_market_value) * 100 if current_market_value > 0 else 0
            else:
                current_market_value = 0
                dividend_yield = 0
            
            dividend_metrics[holding.symbol] = {
                'expected_annual_dividend': expected_annual_dividend,
                'dividend_yield': dividend_yield
            }
    
    return dividend_metrics

def get_dividend_allocation_data(user_id):
    """특정 사용자의 배당 배분 차트용 데이터"""
    dividend_metrics = calculate_dividend_metrics(user_id)
    return [{'symbol': symbol, 'expected_annual_dividend': metrics['expected_annual_dividend']}
            for symbol, metrics in dividend_metrics.items() if metrics['expected_annual_dividend'] > 0]


# --- 기존 함수들은 그대로 유지 ---
# Stock to Company Domain Mapping for Logo API
STOCK_COMPANY_MAPPING = { ... }
DIVIDEND_MONTHS = { ... }
def get_stock_logo_url(symbol): ...
def get_company_name(symbol): ...
def get_dividend_months(symbol): ...
