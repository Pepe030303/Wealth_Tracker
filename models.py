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
import numpy as np

logger = logging.getLogger(__name__)

# --- (다른 모델 클래스와 함수는 이전과 동일) ---
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
            logger.warning(f"({h.symbol}) 배당 지표 계산 실패: {e}")
            continue
    return dividend_metrics

def get_dividend_allocation_data(dividend_metrics):
    return [{'symbol': s, 'value': m['expected_annual_dividend']} for s, m in dividend_metrics.items() if m.get('expected_annual_dividend', 0) > 0]


# --- 동적 배당 월 조회 기능 (최종 디버깅 및 수정) ---

DIVIDEND_MONTH_CACHE = {}
MONTH_NUMBER_TO_NAME = {1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'}

def get_dividend_months(symbol):
    upper_symbol = symbol.upper()
    if upper_symbol in DIVIDEND_MONTH_CACHE:
        return DIVIDEND_MONTH_CACHE[upper_symbol]

    paid_months = set() # 중복을 허용하지 않는 set으로 변경
    try:
        ticker = yf.Ticker(upper_symbol)
        
        # 1. 과거 배당락일(.actions)을 우선적으로 사용
        actions = ticker.actions
        if actions is not None and not actions.empty and 'Dividends' in actions.columns:
            ex_dividend_dates = actions[actions['Dividends'] > 0].index
            
            # --- 디버깅 로그 추가 ---
            logger.info(f"[{upper_symbol}] yfinance .actions에서 가져온 배당락일: {ex_dividend_dates.month.tolist()}")
            
            # 시간대 정보 제거
            ex_dividend_dates_naive = ex_dividend_dates.tz_convert(None) if ex_dividend_dates.tz is not None else ex_dividend_dates
            
            # 기간 필터링 없이 모든 과거 데이터의 월을 집계
            for date in ex_dividend_dates_naive:
                paid_months.add(date.month)
        
        # 2. 로직 보강: 분기 배당주인데 월이 3개만 잡히는 경우 (예: 3, 6, 12)
        if len(paid_months) == 3:
            # 월 간의 차이를 계산
            sorted_months = sorted(list(paid_months))
            diffs = np.diff(sorted_months)
            # 대부분의 차이가 3 (분기)인데, 하나만 다른 경우
            if np.count_nonzero(diffs == 3) >= 1:
                # 누락된 분기를 찾아 추가
                for i in range(4):
                    # 기준 월(예: 3월)에서 3개월씩 더해봄
                    expected_month = (sorted_months[0] - 1 + 3 * i) % 12 + 1
                    paid_months.add(expected_month)
                logger.info(f"[{upper_symbol}] 분기 배당 보정 적용 후: {sorted(list(paid_months))}")

    except Exception as e:
        logger.warning(f"({upper_symbol}) 배당 월 정보 조회 실패: {e}")
    
    final_months = sorted(list(paid_months))
    if final_months:
        month_names = [MONTH_NUMBER_TO_NAME.get(m, '') for m in final_months]
        DIVIDEND_MONTH_CACHE[upper_symbol] = month_names
        return month_names
    else:
        DIVIDEND_MONTH_CACHE[upper_symbol] = []
        return []
