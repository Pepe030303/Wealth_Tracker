# models.py

from datetime import datetime
from sqlalchemy import func, extract
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
import logging

logger = logging.getLogger(__name__)

# --- 사용자 모델 ---
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

# --- 데이터 모델 (user_id 추가) ---
class Trade(db.Model):
    """거래 기록"""
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False)
    trade_type = db.Column(db.String(10), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    trade_date = db.Column(db.Date, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('trades', lazy='dynamic'))

    def __repr__(self):
        return f'<Trade {self.symbol}: {self.trade_type} {self.quantity} @ ${self.price}>'

class Holding(db.Model):
    """보유 종목 정보"""
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    purchase_price = db.Column(db.Float, nullable=False)
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('holdings', lazy='dynamic'))

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
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('dividends', lazy='dynamic'))

    def __repr__(self):
        return f'<Dividend {self.symbol}: ${self.amount} on {self.dividend_date}>'
    
    def get_amount_per_share(self):
        return self.amount_per_share if self.amount_per_share is not None else self.amount

class StockPrice(db.Model):
    """주가 캐시"""
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False, unique=True)
    current_price = db.Column(db.Float, nullable=False)
    change = db.Column(db.Float, default=0.0)
    change_percent = db.Column(db.Float, default=0.0)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<StockPrice {self.symbol}: ${self.current_price}>'

# --- 계산 함수 ---
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
                    buy_record = buy_queue[0]
                    if buy_record['quantity'] <= sell_quantity:
                        sell_quantity -= buy_record['quantity']
                        buy_queue.pop(0)
                    else:
                        buy_record['quantity'] -= sell_quantity
                        sell_quantity = 0

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
    for holding in holdings:
        recent_dividend = Dividend.query.filter_by(symbol=holding.symbol, user_id=user_id).order_by(Dividend.dividend_date.desc()).first()
        if recent_dividend:
            from stock_api import stock_api
            amount_per_share = recent_dividend.get_amount_per_share() or 0
            expected_annual_dividend = amount_per_share * holding.quantity * recent_dividend.payout_frequency
            price_data = stock_api.get_stock_price(holding.symbol)
            if price_data and price_data.get('price'):
                current_market_value = price_data['price'] * holding.quantity
                dividend_yield = (expected_annual_dividend / current_market_value) * 100 if current_market_value > 0 else 0
            else:
                current_market_value = 0; dividend_yield = 0
            dividend_metrics[holding.symbol] = {'expected_annual_dividend': expected_annual_dividend, 'dividend_yield': dividend_yield}
    return dividend_metrics

def get_dividend_allocation_data(user_id):
    dividend_metrics = calculate_dividend_metrics(user_id)
    return [{'symbol': s, 'expected_annual_dividend': m['expected_annual_dividend']} for s, m in dividend_metrics.items() if m['expected_annual_dividend'] > 0]

# --- 템플릿용 헬퍼 함수들 ---
STOCK_COMPANY_MAPPING = {'AAPL': {'domain': 'apple.com', 'name': 'Apple Inc.'}, 'MSFT': {'domain': 'microsoft.com', 'name': 'Microsoft Corporation'}, 'GOOGL': {'domain': 'google.com', 'name': 'Alphabet Inc.'}, 'GOOG': {'domain': 'google.com', 'name': 'Alphabet Inc.'}, 'AMZN': {'domain': 'amazon.com', 'name': 'Amazon.com Inc.'}, 'TSLA': {'domain': 'tesla.com', 'name': 'Tesla Inc.'}, 'META': {'domain': 'meta.com', 'name': 'Meta Platforms Inc.'}, 'NVDA': {'domain': 'nvidia.com', 'name': 'NVIDIA Corporation'}, 'NFLX': {'domain': 'netflix.com', 'name': 'Netflix Inc.'}, 'V': {'domain': 'visa.com', 'name': 'Visa Inc.'}, 'JPM': {'domain': 'jpmorganchase.com', 'name': 'JPMorgan Chase & Co.'}, 'JNJ': {'domain': 'jnj.com', 'name': 'Johnson & Johnson'}, 'WMT': {'domain': 'walmart.com', 'name': 'Walmart Inc.'}, 'PG': {'domain': 'pg.com', 'name': 'Procter & Gamble'}, 'UNH': {'domain': 'unitedhealthgroup.com', 'name': 'UnitedHealth Group'}, 'HD': {'domain': 'homedepot.com', 'name': 'The Home Depot'}, 'BAC': {'domain': 'bankofamerica.com', 'name': 'Bank of America'}, 'MA': {'domain': 'mastercard.com', 'name': 'Mastercard Inc.'}, 'DIS': {'domain': 'disney.com', 'name': 'The Walt Disney Company'}, 'ADBE': {'domain': 'adobe.com', 'name': 'Adobe Inc.'}, 'CRM': {'domain': 'salesforce.com', 'name': 'Salesforce Inc.'}, 'XOM': {'domain': 'exxonmobil.com', 'name': 'Exxon Mobil Corporation'}, 'CVX': {'domain': 'chevron.com', 'name': 'Chevron Corporation'}, 'KO': {'domain': 'coca-cola.com', 'name': 'The Coca-Cola Company'}, 'PEP': {'domain': 'pepsico.com', 'name': 'PepsiCo Inc.'}, 'T': {'domain': 'att.com', 'name': 'AT&T Inc.'}, 'VZ': {'domain': 'verizon.com', 'name': 'Verizon Communications'}, 'INTC': {'domain': 'intel.com', 'name': 'Intel Corporation'}, 'IBM': {'domain': 'ibm.com', 'name': 'International Business Machines'}, 'ORCL': {'domain': 'oracle.com', 'name': 'Oracle Corporation'}, 'CZR': {'domain': 'caesars.com', 'name': 'Caesars Entertainment'},}
DIVIDEND_MONTHS = {'AAPL': ['Feb', 'May', 'Aug', 'Nov'], 'MSFT': ['Mar', 'Jun', 'Sep', 'Dec'], 'GOOGL': [], 'GOOG': [], 'AMZN': [], 'TSLA': [], 'META': [], 'NVDA': ['Mar', 'Jun', 'Sep', 'Dec'], 'NFLX': [], 'V': ['Mar', 'Jun', 'Sep', 'Dec'], 'JPM': ['Jan', 'Apr', 'Jul', 'Oct'], 'JNJ': ['Mar', 'Jun', 'Sep', 'Dec'], 'WMT': ['Jan', 'Apr', 'Jul', 'Oct'], 'PG': ['Feb', 'May', 'Aug', 'Nov'], 'UNH': ['Mar', 'Jun', 'Sep', 'Dec'], 'HD': ['Mar', 'Jun', 'Sep', 'Dec'], 'BAC': ['Mar', 'Jun', 'Sep', 'Dec'], 'MA': ['Feb', 'May', 'Aug', 'Nov'], 'DIS': ['Jan', 'Jul'], 'ADBE': ['Mar', 'Jun', 'Sep', 'Dec'], 'CRM': [], 'XOM': ['Mar', 'Jun', 'Sep', 'Dec'], 'CVX': ['Mar', 'Jun', 'Sep', 'Dec'], 'KO': ['Apr', 'Jul', 'Oct', 'Dec'], 'PEP': ['Jan', 'Apr', 'Jun', 'Oct'], 'T': ['Feb', 'May', 'Aug', 'Nov'], 'VZ': ['Feb', 'May', 'Aug', 'Nov'], 'INTC': ['Mar', 'Jun', 'Sep', 'Dec'], 'IBM': ['Mar', 'Jun', 'Sep', 'Dec'], 'ORCL': ['Jan', 'Apr', 'Jul', 'Oct'],}

def get_stock_logo_url(symbol):
    if symbol in STOCK_COMPANY_MAPPING: return f"https://logo.clearbit.com/{STOCK_COMPANY_MAPPING[symbol]['domain']}"
    return None

def get_company_name(symbol):
    if symbol in STOCK_COMPANY_MAPPING: return STOCK_COMPANY_MAPPING[symbol]['name']
    return symbol

def get_dividend_months(symbol):
    return DIVIDEND_MONTHS.get(symbol, [])
