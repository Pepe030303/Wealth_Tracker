# routes.py

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from datetime import datetime
from sqlalchemy import func, extract
from app import db
from models import User, Holding, Dividend, Trade, recalculate_holdings, calculate_dividend_metrics, get_dividend_allocation_data
from stock_api import stock_api
from flask_login import login_user, logout_user, current_user, login_required
import logging
import yfinance as yf
from datetime import datetime, timedelta
from models import DividendUpdateCache 

logger = logging.getLogger(__name__)
main_bp = Blueprint('main', __name__)

def _update_dividends_for_symbol(symbol, user_id):
    try:
        holding = Holding.query.filter_by(user_id=user_id, symbol=symbol).first()
        if not holding: return 0
        
        ticker = yf.Ticker(symbol)
        hist_dividends = ticker.dividends
        if hist_dividends.empty: return 0

        new_dividend_count = 0
        for pay_date, amount_per_share in hist_dividends.items():
            pay_date_obj = pay_date.date()
            if holding.purchase_date and pay_date_obj > holding.purchase_date.date():
                exists = Dividend.query.filter_by(symbol=symbol, dividend_date=pay_date_obj, user_id=user_id).first()
                if not exists:
                    new_dividend = Dividend(
                        symbol=symbol, amount=amount_per_share * holding.quantity,
                        amount_per_share=amount_per_share, dividend_date=pay_date_obj, user_id=user_id
                    )
                    db.session.add(new_dividend)
                    new_dividend_count += 1
        
        if new_dividend_count > 0:
            db.session.commit()
            logger.info(f"User {user_id}, Symbol {symbol}: {new_dividend_count}개의 배당금 추가.")
        return new_dividend_count
    except Exception as e:
        logger.error(f"'{symbol}' 배당금 업데이트 중 오류: {e}")
        db.session.rollback()
        return 0

@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.check_password(request.form.get('password')):
            login_user(user, remember=True)
            return redirect(url_for('main.dashboard'))
        flash('아이디 또는 비밀번호가 올바르지 않습니다.', 'error')
    return render_template('login.html')

@main_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.login'))

@main_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated: return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        username, email, password = request.form.get('username'), request.form.get('email'), request.form.get('password')
        if not all([username, email, password]):
            flash('모든 필드를 입력해주세요.', 'error')
        elif User.query.filter_by(username=username).first():
            flash('이미 사용 중인 아이디입니다.', 'error')
        elif User.query.filter_by(email=email).first():
            flash('이미 사용 중인 이메일입니다.', 'error')
        else:
            user = User(username=username, email=email); user.set_password(password)
            db.session.add(user); db.session.commit()
            flash('회원가입이 완료되었습니다! 로그인해주세요.', 'success')
            return redirect(url_for('main.login'))
    return render_template('signup.html')

# --- 대시보드 라우트 (UI 개선을 위해 평단가 추가) ---
@main_bp.route('/')
@login_required
def dashboard():
    holdings = Holding.query.filter_by(user_id=current_user.id).all()
    holdings_data = []
    total_investment = 0
    total_current_value = 0

    for h in holdings:
        total_investment += h.quantity * h.purchase_price
        price_data = stock_api.get_stock_price(h.symbol)
        current_price = price_data['price'] if price_data and price_data.get('price') else h.purchase_price
        current_value = h.quantity * current_price
        total_current_value += current_value
        
        holdings_data.append({
            'holding': h,
            'current_price': current_price,
            'current_value': current_value,
            'profit_loss': current_value - (h.quantity * h.purchase_price),
            'profit_loss_percent': ((current_value / (h.quantity * h.purchase_price)) - 1) * 100 if h.purchase_price > 0 and h.quantity > 0 else 0,
            'change': price_data.get('change', 0) if price_data else 0,
            'change_percent': price_data.get('change_percent', 0) if price_data else 0,
            'purchase_price': h.purchase_price # 대시보드 테이블에 평단가 전달
        })
        
    total_profit_loss = total_current_value - total_investment
    total_return_percent = (total_profit_loss / total_investment * 100) if total_investment > 0 else 0
    
    # 월별 배당금 차트 데이터 (기존과 동일)
    cy = datetime.now().year
    monthly_dividends = db.session.query(extract('month', Dividend.dividend_date), func.sum(Dividend.amount)).filter(Dividend.user_id == current_user.id, extract('year', Dividend.dividend_date) == cy).group_by(extract('month', Dividend.dividend_date)).all()
    dividend_data = [0]*12
    for month, total in monthly_dividends: dividend_data[int(month)-1] = float(total) if month else 0

    return render_template('dashboard.html', 
                           holdings_data=holdings_data, 
                           total_investment=total_investment, 
                           total_current_value=total_current_value, 
                           total_profit_loss=total_profit_loss, 
                           total_return_percent=total_return_percent, 
                           dividend_data=dividend_data)

@main_bp.route('/holdings')
@login_required
def holdings():
    holdings = Holding.query.filter_by(user_id=current_user.id).all()
    holdings_data = []
    for h in holdings:
        price_data = stock_api.get_stock_price(h.symbol)
        current_price = price_data['price'] if price_data else h.purchase_price
        current_value = h.quantity * current_price
        holdings_data.append({
            'holding': h, 'current_price': current_price, 'current_value': current_value,
            'profit_loss': current_value - (h.quantity * h.purchase_price),
            'profit_loss_percent': (current_value - (h.quantity * h.purchase_price)) / (h.quantity * h.purchase_price) * 100 if h.purchase_price > 0 else 0,
            'change': price_data.get('change', 0) if price_data else 0, 'change_percent': price_data.get('change_percent', 0) if price_data else 0
        })
    return render_template('holdings.html', holdings_data=holdings_data)
# --- 거래기록 라우트 (로직 수정) ---
@main_bp.route('/trades')
@login_required
def trades():
    trades = Trade.query.filter_by(user_id=current_user.id).order_by(Trade.trade_date.desc(), Trade.id.desc()).all()
    holdings = Holding.query.filter_by(user_id=current_user.id).all()
    
    # 각 보유 종목에 대한 매수/매도 수량을 계산
    summary_details = {}
    for holding in holdings:
        symbol = holding.symbol
        buys = db.session.query(func.sum(Trade.quantity)).filter_by(user_id=current_user.id, symbol=symbol, trade_type='buy').scalar() or 0
        sells = db.session.query(func.sum(Trade.quantity)).filter_by(user_id=current_user.id, symbol=symbol, trade_type='sell').scalar() or 0
        summary_details[symbol] = {
            'net_quantity': holding.quantity,
            'avg_price': holding.purchase_price,
            'total_bought': buys,
            'total_sold': sells
        }

    return render_template('trades.html', trades=trades, trade_summary=summary_details)

@main_bp.route('/trades/add', methods=['POST'])
@login_required
def add_trade():
    try:
        symbol = request.form.get('symbol', '').upper().strip()
        trade_type = request.form.get('trade_type')
        quantity = float(request.form.get('quantity'))
        price = float(request.form.get('price'))
        trade_date = datetime.strptime(request.form.get('trade_date'), '%Y-%m-%d').date()

        if not all([symbol, trade_type, quantity > 0, price > 0]):
            raise ValueError("모든 필드를 올바르게 입력해주세요.")

        if trade_type == 'sell':
            current_holding = Holding.query.filter_by(user_id=current_user.id, symbol=symbol).first()
            if not current_holding or current_holding.quantity < quantity:
                flash(f'보유 수량이 부족하여 매도할 수 없습니다. (보유: {current_holding.quantity if current_holding else 0})', 'error')
                return redirect(url_for('main.trades'))

        trade = Trade(symbol=symbol, trade_type=trade_type, quantity=quantity, price=price, trade_date=trade_date, user_id=current_user.id)
        db.session.add(trade)
        db.session.commit()
        recalculate_holdings(current_user.id)
        
        flash(f'{symbol} {trade_type.upper()} 거래가 성공적으로 추가되었습니다.', 'success')
    except (ValueError, TypeError) as e:
        flash(str(e) or '수량, 가격, 날짜를 올바른 형식으로 입력해주세요.', 'error')
        db.session.rollback()
    except Exception as e:
        logger.error(f"거래 추가 오류: {e}"); flash('거래 추가 중 오류가 발생했습니다.', 'error'); db.session.rollback()
    return redirect(url_for('main.trades'))

@main_bp.route('/trades/delete/<int:trade_id>')
@login_required
def delete_trade(trade_id):
    trade = Trade.query.filter_by(id=trade_id, user_id=current_user.id).first_or_404()
    symbol = trade.symbol
    db.session.delete(trade); db.session.commit()
    recalculate_holdings(current_user.id)
    flash(f'{symbol} 거래가 삭제되었습니다.', 'success')
    return redirect(url_for('main.trades'))

@main_bp.route('/trades/recalculate')
@login_required
def recalculate_holdings_route():
    recalculate_holdings(current_user.id)
    flash('보유 종목이 재계산되었습니다.', 'success')
    return redirect(url_for('main.holdings'))
# --- 배당금 라우트 (로직 수정) ---
@main_bp.route('/dividends')
@login_required
def dividends():
    # 배당금 페이지 진입 시, 캐시 만료된 종목에 대해 자동 동기화 시도
    try:
        holdings = Holding.query.filter_by(user_id=current_user.id).all()
        if holdings:
            symbols_to_update = []
            for h in holdings:
                cache = DividendUpdateCache.query.filter_by(user_id=current_user.id, symbol=h.symbol).first()
                if not cache or (datetime.utcnow() - cache.last_updated) > timedelta(days=1):
                    symbols_to_update.append(h.symbol)
            
            if symbols_to_update:
                total_added_count = 0
                for symbol in symbols_to_update:
                    total_added_count += _sync_dividends_for_symbol(symbol, current_user.id)
                
                if total_added_count > 0:
                    flash(f'{total_added_count}개의 새로운 배당금 내역을 동기화했습니다.', 'success')

    except Exception as e:
        logger.error(f"배당금 자동 동기화 중 오류 발생: {e}")

    # 페이지 렌더링을 위한 데이터 조회
    dividends_list = Dividend.query.filter_by(user_id=current_user.id).order_by(Dividend.dividend_date.desc()).all()
    dividend_metrics = calculate_dividend_metrics(current_user.id)
    allocation_data = get_dividend_allocation_data(current_user.id)

    # 예상 월별 배당금 계산
    total_annual_dividend = sum(m['expected_annual_dividend'] for m in dividend_metrics.values())
    expected_monthly_data = [total_annual_dividend / 12] * 12 # 간단히 1/12로 계산

    return render_template('dividends.html', 
                             dividends=dividends_list, 
                             dividend_metrics=dividend_metrics,
                             allocation_data=allocation_data,
                             expected_monthly_data=expected_monthly_data)

# 배당금 동기화를 위한 헬퍼 함수
def _sync_dividends_for_symbol(symbol, user_id):
    new_dividend_count = 0
    try:
        holding = Holding.query.filter_by(user_id=user_id, symbol=symbol).first()
        if not holding: return 0

        ticker = yf.Ticker(symbol)
        hist_dividends = ticker.dividends
        if not hist_dividends.empty:
            existing_dates = {d.dividend_date for d in Dividend.query.with_entities(Dividend.dividend_date).filter_by(user_id=user_id, symbol=symbol)}
            
            for pay_date, amount_per_share in hist_dividends.items():
                pay_date_obj = pay_date.date()
                if holding.purchase_date and pay_date_obj > holding.purchase_date.date() and pay_date_obj not in existing_dates:
                    new_dividend = Dividend(symbol=symbol, amount=amount_per_share * holding.quantity, amount_per_share=amount_per_share, dividend_date=pay_date_obj, user_id=user_id)
                    db.session.add(new_dividend)
                    new_dividend_count += 1
        
        # 캐시 업데이트
        cache = DividendUpdateCache.query.filter_by(user_id=user_id, symbol=symbol).first()
        if not cache:
            cache = DividendUpdateCache(user_id=user_id, symbol=symbol)
            db.session.add(cache)
        cache.last_updated = datetime.utcnow()
        
        if new_dividend_count > 0:
            db.session.commit()
    except Exception as e:
        logger.error(f"'{symbol}' 배당금 동기화 실패: {e}")
        db.session.rollback()
    else:
        db.session.commit()
    return new_dividend_count

@main_bp.route('/dividends/add', methods=['POST'])
@login_required
def add_dividend():
    try:
        symbol, amount = request.form.get('symbol', '').upper().strip(), float(request.form.get('amount', 0))
        if not symbol or amount <= 0: raise ValueError('종목과 총 배당금액을 올바르게 입력해주세요.')
        new_dividend = Dividend(
            symbol=symbol, amount=amount, dividend_date=datetime.strptime(request.form.get('dividend_date'), '%Y-%m-%d').date(),
            amount_per_share=float(request.form.get('amount_per_share')) if request.form.get('amount_per_share') else None,
            ex_dividend_date=datetime.strptime(request.form.get('ex_dividend_date'), '%Y-%m-%d').date() if request.form.get('ex_dividend_date') else None,
            payout_frequency=int(request.form.get('payout_frequency', 4)), user_id=current_user.id
        )
        db.session.add(new_dividend); db.session.commit()
        flash(f'{symbol} 배당금이 성공적으로 추가되었습니다.', 'success')
    except (ValueError, TypeError) as e:
        flash(str(e), 'error'); db.session.rollback()
    return redirect(url_for('main.dividends'))

@main_bp.route('/dividends/delete/<int:dividend_id>')
@login_required
def delete_dividend(dividend_id):
    dividend = Dividend.query.filter_by(id=dividend_id, user_id=current_user.id).first_or_404()
    db.session.delete(dividend); db.session.commit()
    flash(f'{dividend.symbol} 배당금이 삭제되었습니다.', 'success')
    return redirect(url_for('main.dividends'))

@main_bp.route('/allocation')
@login_required
def allocation():
    holdings = Holding.query.filter_by(user_id=current_user.id).all()
    allocation_data = []
    for h in holdings:
        price_data = stock_api.get_stock_price(h.symbol)
        if price_data and price_data.get('price'):
            allocation_data.append({'symbol': h.symbol, 'value': h.quantity * price_data['price']})
    return render_template('allocation.html', allocation_data=allocation_data)

# API 라우트
@main_bp.route('/api/stock-price/<symbol>')
@login_required
def get_stock_price(symbol):
    price_data = stock_api.get_stock_price(symbol.upper())
    return jsonify(price_data) if price_data else jsonify({'error': 'Stock price not found'}), 404

@main_bp.route('/api/refresh-prices')
@login_required
def refresh_prices():
    holdings = Holding.query.filter_by(user_id=current_user.id).all()
    symbols = {h.symbol for h in holdings}
    updated_prices = {s: stock_api.get_stock_price(s) for s in symbols}
    return jsonify({s: p for s, p in updated_prices.items() if p})
