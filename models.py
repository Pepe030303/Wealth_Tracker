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

logger = logging.getLogger(__name__)

# --- (User, Trade, Holding 등 다른 모델들은 이전과 동일) ---
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
    # 이 함수는 수정할 필요 없음
    Holding.query.filter_by(user_id=user_id).delete()
    symbols = db.session.query(Trade.symbol).filter_by(user_id=user_id).distinct().all()
    for (symbol,) in symbols:
        trades = Trade.query.filter_by(symbol=symbol, user_id=user_id).order_by(Trade.trade_date, Trade.id).all()
        buy_queue = []
        for trade in trades:
            if trade.trade_type == 'buy': buy_queue.append({'quantity': trade.quantity, 'price': trade.price, 'date': trade.trade_date})
            elif trade.trade_type == 'sell':
                sell_quantity = trade.quantity
                while sell_quantity > 0 and buy_queue:
                    if buy_queue[0]['quantity'] <= sell_quantity: sell_quantity -= buy_queue[0]['quantity']; buy_queue.pop(0)
                    else: buy_queue[0]['quantity'] -= sell_quantity; sell_quantity = 0
        final_quantity = sum(b['quantity'] for b in buy_queue)
        if final_quantity > 0:
            final_cost = sum(b['quantity'] * b['price'] for b in buy_queue)
            avg_price = final_cost / final_quantity
            latest_buy_date = max(b['date'] for b in buy_queue) if buy_queue else None
            holding = Holding(symbol=symbol, quantity=final_quantity, purchase_price=avg_price, purchase_date=latest_buy_date, user_id=user_id)
            db.session.add(holding)
    db.session.commit()

def calculate_dividend_metrics(user_id):
    # 이 함수는 수정할 필요 없음
    holdings = Holding.query.filter_by(user_id=user_id).all()
    dividend_metrics = {}
    from stock_api import stock_api
    for h in holdings:
        try:
            ticker = yf.Ticker(h.symbol); info = ticker.info; annual_dps = 0
            if info.get('quoteType') == 'ETF' and info.get('trailingAnnualDividendRate'): annual_dps = info.get('trailingAnnualDividendRate', 0)
            elif info.get('dividendRate'): annual_dps = info.get('dividendRate', 0)
            elif not ticker.dividends.empty:
                naive_dividends = ticker.dividends.tz_localize(None)
                last_year_dividends = naive_dividends[naive_dividends.index > datetime.now() - timedelta(days=365)]
                annual_dps = last_year_dividends.sum()
            if annual_dps > 0:
                expected_annual_dividend = float(annual_dps) * h.quantity; price_data = stock_api.get_stock_price(h.symbol)
                if price_data and price_data.get('price') and price_data['price'] > 0: dividend_yield = (annual_dps / price_data['price']) * 100
                else: dividend_yield = info.get('yield', 0) * 100
                dividend_metrics[h.symbol] = {'expected_annual_dividend': expected_annual_dividend, 'dividend_yield': dividend_yield}
        except Exception as e:
            logger.warning(f"{h.symbol}의 배당 지표 계산 실패: {e}")
            continue
    return dividend_metrics

def get_dividend_allocation_data(dividend_metrics):
    return [{'symbol': s, 'value': m['expected_annual_dividend']} for s, m in dividend_metrics.items() if m.get('expected_annual_dividend', 0) > 0]


# --- 동적 배당 월 조회 기능 (최종 수정) ---

DIVIDEND_MONTH_CACHE = {}
MONTH_NUMBER_TO_NAME = {1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'}

def get_dividend_months(symbol):
    """
    yfinance의 과거 배당락일(.actions)을 우선적으로 사용하여 배당 월을 정확하게 추정합니다.
    """
    upper_symbol = symbol.upper()
    if upper_symbol in DIVIDEND_MONTH_CACHE:
        return DIVIDEND_MONTH_CACHE[upper_symbol]

    paid_months = None
    try:
        ticker = yf.Ticker(upper_symbol)
        
        # 1. 과거 배당락일(.actions)을 우선적으로 사용 (가장 안정적)
        actions = ticker.actions
        if not actions.empty and 'Dividends' in actions.columns and actions['Dividends'].sum() > 0:
            ex_dividend_dates = actions[actions['Dividends'] > 0].index
            # 조회 기간을 18개월로 늘려 안정성 확보
            start_date = pd.to_datetime(datetime.now() - timedelta(days=540))
            ex_dividend_dates_naive = ex_dividend_dates.tz_localize(None)
            recent_ex_dates = ex_dividend_dates_naive[ex_dividend_dates_naive > start_date]
            if not recent_ex_dates.empty:
                paid_months = sorted(list(recent_ex_dates.month.unique()))
        
        # 2. .actions에 정보가 없을 경우, .calendar로 폴백
        if not paid_months:
            if hasattr(ticker, 'calendar') and isinstance(ticker.calendar, pd.DataFrame) and not ticker.calendar.empty:
                calendar_df = ticker.calendar.transpose()
                if 'Ex-Dividend Date' in calendar_df.columns:
                    next_ex_div_date = calendar_df.loc['Earnings', 'Ex-Dividend Date']
                    if isinstance(next_ex_div_date, (datetime, pd.Timestamp)):
                        base_month = next_ex_div_date.month
                        # 분기 배당으로 일반화하여 추정
                        paid_months = sorted([(base_month - 1 - 3 * i) % 12 + 1 for i in range(4)])

    except Exception as e:
        logger.warning(f"({upper_symbol}) 배당 월 정보 조회 실패: {e}")
        paid_months = None

    if paid_months:
        month_names = [MONTH_NUMBER_TO_NAME.get(m, '') for m in paid_months]
        DIVIDEND_MONTH_CACHE[upper_symbol] = month_names
        return month_names
    else:
        DIVIDEND_MONTH_CACHE[upper_symbol] = []
        return []
