# 📄 routes.py

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from datetime import datetime
from sqlalchemy import func
from app import db, task_queue
from tasks import update_all_dividends_for_user
# 🛠️ Refactoring: `recalculate_holdings`를 `models`에서 임포트하던 것을 제거
from models import User, Holding, Dividend, Trade
from utils import get_dividend_allocation_data
from stock_api import stock_api, US_STOCKS_LIST
# 🛠️ Refactoring: 서비스 계층에서 필요한 모든 함수를 임포트
from services.portfolio_service import (
    get_portfolio_analysis_data,
    get_processed_holdings_data,
    recalculate_holdings
)
from flask_login import login_user, logout_user, current_user, login_required
import logging

logger = logging.getLogger(__name__)
main_bp = Blueprint('main', __name__)

# ... (login, logout, signup 등 인증 관련 라우트는 변경 없음) ...
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
        if not all([username, email, password]): flash('모든 필드를 입력해주세요.', 'error')
        elif User.query.filter_by(username=username).first(): flash('이미 사용 중인 아이디입니다.', 'error')
        elif User.query.filter_by(email=email).first(): flash('이미 사용 중인 이메일입니다.', 'error')
        else:
            user = User(username=username, email=email); user.set_password(password)
            db.session.add(user); db.session.commit()
            flash('회원가입이 완료되었습니다! 로그인해주세요.', 'success')
            return redirect(url_for('main.login'))
    return render_template('signup.html')


@main_bp.route('/')
@login_required
def dashboard():
    portfolio_data = get_portfolio_analysis_data(current_user.id)
    if not portfolio_data:
        return render_template('dashboard.html', summary={}, sector_allocation=[], monthly_dividend_data={})
    return render_template('dashboard.html', 
                           summary=portfolio_data['summary'], 
                           sector_allocation=portfolio_data['sector_allocation'], 
                           monthly_dividend_data=portfolio_data['monthly_dividend_data'])

@main_bp.route('/dividends')
@login_required
def dividends():
    portfolio_data = get_portfolio_analysis_data(current_user.id)
    if not portfolio_data:
        return render_template('dividends.html', dividend_metrics={}, allocation_data=[], monthly_dividend_data={})
    
    dividend_metrics = portfolio_data['dividend_metrics']
    allocation_data = get_dividend_allocation_data(dividend_metrics)
    monthly_dividend_data = portfolio_data['monthly_dividend_data']
    total_annual_dividend = sum(m.get('expected_annual_dividend', 0) for m in dividend_metrics.values())

    return render_template('dividends.html',
                           dividend_metrics=dividend_metrics,
                           allocation_data=allocation_data,
                           monthly_dividend_data=monthly_dividend_data,
                           total_annual_dividend=total_annual_dividend)

@main_bp.route('/holdings')
@login_required
def holdings():
    # 🛠️ Refactoring: 복잡한 데이터 처리 로직을 서비스 함수 호출로 대체
    # 라우트는 이제 데이터 가공의 책임 없이, 서비스 계층에 작업을 위임하고 결과만 받습니다.
    holdings_data = get_processed_holdings_data(current_user.id)
    return render_template('holdings.html', holdings_data=holdings_data)

# ... (trades, etc. routes are unchanged) ...
@main_bp.route('/trades')
@login_required
def trades():
    trades = Trade.query.filter_by(user_id=current_user.id).order_by(Trade.trade_date.desc(), Trade.id.desc()).all()
    return render_template('trades.html', trades=trades)

@main_bp.route('/trades/add', methods=['POST'])
@login_required
def add_trade():
    symbol = request.form.get('symbol', '').upper().strip()
    try:
        trade_type, quantity, price = request.form.get('trade_type'), float(request.form.get('quantity')), float(request.form.get('price'))
        trade_date = datetime.strptime(request.form.get('trade_date'), '%Y-%m-%d').date()
        if not all([symbol, trade_type, quantity > 0, price > 0]): raise ValueError("모든 필드를 올바르게 입력해주세요.")
        if trade_type == 'sell':
            holding = Holding.query.filter_by(user_id=current_user.id, symbol=symbol).first()
            if not holding or holding.quantity < quantity:
                flash(f'보유 수량이 부족하여 매도할 수 없습니다. (보유: {holding.quantity if holding else 0})', 'error')
                return redirect(url_for('main.trades'))
        trade = Trade(symbol=symbol, trade_type=trade_type, quantity=quantity, price=price, trade_date=trade_date, user_id=current_user.id)
        db.session.add(trade); db.session.commit()
        # 🛠️ Refactoring: 서비스 계층에서 임포트된 함수를 호출
        recalculate_holdings(current_user.id)
        flash(f'{symbol} {trade_type.upper()} 거래가 성공적으로 추가되었습니다.', 'success')
    except (ValueError, TypeError) as e:
        flash(str(e) or '수량, 가격, 날짜를 올바른 형식으로 입력해주세요.', 'error'); db.session.rollback()
    except Exception as e:
        logger.error(f"거래 추가 오류: {e}"); flash('거래 추가 중 오류가 발생했습니다.', 'error'); db.session.rollback()
    return redirect(url_for('main.trades'))

@main_bp.route('/trades/delete/<int:trade_id>')
@login_required
def delete_trade(trade_id):
    trade = Trade.query.filter_by(id=trade_id, user_id=current_user.id).first_or_404()
    db.session.delete(trade); db.session.commit()
    # 🛠️ Refactoring: 서비스 계층에서 임포트된 함수를 호출
    recalculate_holdings(current_user.id)
    flash(f'{trade.symbol} 거래가 삭제되었습니다.', 'success')
    return redirect(url_for('main.trades'))

@main_bp.route('/dividends/history')
@login_required
def dividends_history():
    if task_queue:
        task_queue.enqueue(update_all_dividends_for_user, current_user.id, job_timeout='10m')
    page = request.args.get('page', 1, type=int)
    dividends_pagination = Dividend.query.filter_by(user_id=current_user.id).order_by(Dividend.dividend_date.desc()).paginate(page=page, per_page=20, error_out=False)
    total_received = db.session.query(func.sum(Dividend.amount)).filter_by(user_id=current_user.id).scalar() or 0
    return render_template('dividends_history.html', 
                           dividends_pagination=dividends_pagination,
                           total_received=total_received)

@main_bp.route('/allocation')
@login_required
def allocation():
    holdings = Holding.query.filter_by(user_id=current_user.id).all()
    if not holdings: return render_template('allocation.html', allocation_data=[])
    symbols = {h.symbol for h in holdings}
    price_data_map = stock_api.get_stock_prices_bulk(symbols)
    allocation_data = []
    for h in holdings:
        price_data = price_data_map.get(h.symbol)
        if price_data and price_data.get('price') is not None:
            allocation_data.append({'symbol': h.symbol, 'value': h.quantity * price_data['price']})
    return render_template('allocation.html', allocation_data=allocation_data)

@main_bp.route('/api/search-stocks')
@login_required
def search_stocks():
    query = request.args.get('q', '').upper()
    if not query: return jsonify([])
    results = [stock for stock in US_STOCKS_LIST if query in stock['ticker'].upper() or query in stock['name'].upper()]
    return jsonify(results[:10])

@main_bp.route('/stock/<string:symbol>')
@login_required
def stock_detail(symbol):
    symbol = symbol.upper()
    profile = stock_api.get_stock_profile(symbol)
    price_data = stock_api.get_stock_price(symbol)
    price_history = stock_api.get_price_history(symbol, period='6mo')
    if not price_data or not price_history:
        flash(f'{symbol} 종목 정보를 가져오는 데 실패했습니다.', 'error')
        return redirect(request.referrer or url_for('main.dashboard'))
    return render_template('stock_detail.html', 
                           symbol=symbol,
                           profile=profile,
                           price_data=price_data,
                           price_history=price_history)
