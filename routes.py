# routes.py

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from datetime import datetime, date
from sqlalchemy import func, extract
from app import db
from models import User, Holding, Dividend, Trade, recalculate_holdings, calculate_dividend_metrics, get_dividend_allocation_data
from stock_api import stock_api
from flask_login import login_user, logout_user, current_user, login_required
import logging
import yfinance as yf

logger = logging.getLogger(__name__)
main_bp = Blueprint('main', __name__)

# --- 인증 라우트 ---
@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user is None or not user.check_password(password):
            flash('아이디 또는 비밀번호가 올바르지 않습니다.', 'error')
            return redirect(url_for('main.login'))
        login_user(user, remember=True)
        return redirect(url_for('main.dashboard'))
    return render_template('login.html')

@main_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.login'))

@main_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        if not username or not email or not password:
            flash('모든 필드를 입력해주세요.', 'error')
            return redirect(url_for('main.signup'))

        if User.query.filter_by(username=username).first():
            flash('이미 사용 중인 아이디입니다.', 'error')
            return redirect(url_for('main.signup'))
        if User.query.filter_by(email=email).first():
            flash('이미 사용 중인 이메일입니다.', 'error')
            return redirect(url_for('main.signup'))

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('회원가입이 완료되었습니다! 로그인해주세요.', 'success')
        return redirect(url_for('main.login'))
    return render_template('signup.html')


# --- 메인 애플리케이션 라우트 (@login_required 추가) ---
@main_bp.route('/')
@login_required
def dashboard():
    holdings = Holding.query.filter_by(user_id=current_user.id).all()
    
    total_investment = sum(h.quantity * h.purchase_price for h in holdings)
    total_current_value = 0
    holdings_data = []
    
    for holding in holdings:
        price_data = stock_api.get_stock_price(holding.symbol)
        current_price = price_data.get('price') if price_data else holding.purchase_price
        current_value = holding.quantity * current_price
        profit_loss = current_value - (holding.quantity * holding.purchase_price)
        profit_loss_percent = (profit_loss / (holding.quantity * holding.purchase_price)) * 100 if holding.quantity * holding.purchase_price > 0 else 0
        
        holdings_data.append({
            'holding': holding,
            'current_price': current_price,
            'current_value': current_value,
            'profit_loss': profit_loss,
            'profit_loss_percent': profit_loss_percent,
            'change': price_data.get('change', 0) if price_data else 0,
            'change_percent': price_data.get('change_percent', 0) if price_data else 0
        })
        total_current_value += current_value
        
    total_profit_loss = total_current_value - total_investment
    total_return_percent = (total_profit_loss / total_investment * 100) if total_investment > 0 else 0
    
    current_year = datetime.now().year
    monthly_dividends = db.session.query(
        extract('month', Dividend.dividend_date).label('month'),
        func.sum(Dividend.amount).label('total')
    ).filter(
        Dividend.user_id == current_user.id,
        extract('year', Dividend.dividend_date) == current_year
    ).group_by(extract('month', Dividend.dividend_date)).all()
    
    dividend_data = [0] * 12
    for month, total in monthly_dividends:
        dividend_data[int(month) - 1] = float(total)

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
    for holding in holdings:
        price_data = stock_api.get_stock_price(holding.symbol)
        current_price = price_data.get('price') if price_data else holding.purchase_price
        current_value = holding.quantity * current_price
        profit_loss = current_value - (holding.quantity * holding.purchase_price)
        profit_loss_percent = (profit_loss / (holding.quantity * holding.purchase_price)) * 100 if holding.quantity * holding.purchase_price > 0 else 0
        
        holdings_data.append({
            'holding': holding,
            'current_price': current_price,
            'current_value': current_value,
            'profit_loss': profit_loss,
            'profit_loss_percent': profit_loss_percent,
            'change': price_data.get('change', 0) if price_data else 0,
            'change_percent': price_data.get('change_percent', 0) if price_data else 0
        })
    return render_template('holdings.html', holdings_data=holdings_data)


@main_bp.route('/trades')
@login_required
def trades():
    trades = Trade.query.filter_by(user_id=current_user.id).order_by(Trade.trade_date.desc(), Trade.id.desc()).all()
    
    trade_summary = {}
    all_user_trades = Trade.query.filter_by(user_id=current_user.id).all()
    symbols = {t.symbol for t in all_user_trades}

    for symbol in symbols:
        recalculate_holdings(current_user.id) # 보유량 다시 계산
        holding = Holding.query.filter_by(user_id=current_user.id, symbol=symbol).first()
        if holding:
             trade_summary[symbol] = {
                 'net_quantity': holding.quantity,
                 'avg_price': holding.purchase_price
             }

    return render_template('trades.html', trades=trades, trade_summary=trade_summary)

@main_bp.route('/trades/add', methods=['POST'])
@login_required
def add_trade():
    try:
        symbol = request.form.get('symbol', '').upper().strip()
        trade_type = request.form.get('trade_type')
        quantity = float(request.form.get('quantity'))
        price = float(request.form.get('price'))
        trade_date = datetime.strptime(request.form.get('trade_date'), '%Y-%m-%d').date()

        if not all([symbol, trade_type, quantity > 0, price > 0, trade_date]):
            flash('모든 필드를 올바르게 입력해주세요.', 'error')
            return redirect(url_for('main.trades'))

        if trade_type == 'sell':
            current_holding = Holding.query.filter_by(user_id=current_user.id, symbol=symbol).first()
            if not current_holding or current_holding.quantity < quantity:
                flash(f'보유 수량이 부족하여 매도할 수 없습니다. (보유: {current_holding.quantity if current_holding else 0})', 'error')
                return redirect(url_for('main.trades'))

        trade = Trade(
            symbol=symbol, trade_type=trade_type, quantity=quantity,
            price=price, trade_date=trade_date, user_id=current_user.id
        )
        db.session.add(trade)
        db.session.commit()
        recalculate_holdings(current_user.id)
        flash(f'{symbol} {trade_type.upper()} 거래가 성공적으로 추가되었습니다.', 'success')
    except (ValueError, TypeError):
        flash('수량, 가격, 날짜를 올바른 형식으로 입력해주세요.', 'error')
        db.session.rollback()
    except Exception as e:
        logger.error(f"거래 추가 오류: {e}")
        flash('거래 추가 중 오류가 발생했습니다.', 'error')
        db.session.rollback()
    return redirect(url_for('main.trades'))


@main_bp.route('/trades/delete/<int:trade_id>')
@login_required
def delete_trade(trade_id):
    trade = Trade.query.filter_by(id=trade_id, user_id=current_user.id).first_or_404()
    symbol = trade.symbol
    db.session.delete(trade)
    db.session.commit()
    recalculate_holdings(current_user.id)
    flash(f'{symbol} 거래가 삭제되었습니다.', 'success')
    return redirect(url_for('main.trades'))

@main_bp.route('/trades/recalculate')
@login_required
def recalculate_holdings_route():
    recalculate_holdings(current_user.id)
    flash('보유 종목이 재계산되었습니다.', 'success')
    return redirect(url_for('main.holdings'))


@main_bp.route('/dividends')
@login_required
def dividends():
    dividends_list = Dividend.query.filter_by(user_id=current_user.id).order_by(Dividend.dividend_date.desc()).all()
    dividend_metrics = calculate_dividend_metrics(current_user.id)
    allocation_data = get_dividend_allocation_data(current_user.id)
    
    current_year = datetime.now().year
    monthly_dividends_query = db.session.query(
        extract('month', Dividend.dividend_date).label('month'),
        func.sum(Dividend.amount).label('total')
    ).filter(
        Dividend.user_id == current_user.id,
        extract('year', Dividend.dividend_date) == current_year
    ).group_by(extract('month', Dividend.dividend_date)).all()
    
    dividend_data = [0] * 12
    for month, total in monthly_dividends_query:
        dividend_data[int(month) - 1] = float(total)

    return render_template('dividends.html', 
                             dividends=dividends_list, 
                             dividend_data=dividend_data,
                             dividend_metrics=dividend_metrics,
                             allocation_data=allocation_data)

@main_bp.route('/dividends/add', methods=['POST'])
@login_required
def add_dividend():
    try:
        symbol = request.form.get('symbol', '').upper().strip()
        amount = float(request.form.get('amount', 0))
        dividend_date = datetime.strptime(request.form.get('dividend_date'), '%Y-%m-%d').date()
        
        if not symbol or amount <= 0:
            flash('종목과 총 배당금액을 올바르게 입력해주세요.', 'error')
            return redirect(url_for('main.dividends'))

        new_dividend = Dividend(
            symbol=symbol, amount=amount, dividend_date=dividend_date,
            amount_per_share=float(request.form.get('amount_per_share')) if request.form.get('amount_per_share') else None,
            ex_dividend_date=datetime.strptime(request.form.get('ex_dividend_date'), '%Y-%m-%d').date() if request.form.get('ex_dividend_date') else None,
            payout_frequency=int(request.form.get('payout_frequency', 4)),
            user_id=current_user.id
        )
        db.session.add(new_dividend)
        db.session.commit()
        flash(f'{symbol} 배당금이 성공적으로 추가되었습니다.', 'success')
    except (ValueError, TypeError):
        flash('금액과 날짜를 올바른 형식으로 입력해주세요.', 'error')
        db.session.rollback()
    return redirect(url_for('main.dividends'))

@main_bp.route('/dividends/delete/<int:dividend_id>')
@login_required
def delete_dividend(dividend_id):
    dividend = Dividend.query.filter_by(id=dividend_id, user_id=current_user.id).first_or_404()
    db.session.delete(dividend)
    db.session.commit()
    flash(f'{dividend.symbol} 배당금이 삭제되었습니다.', 'success')
    return redirect(url_for('main.dividends'))

@main_bp.route('/dividends/auto-update')
@login_required
def auto_update_dividends():
    holdings = Holding.query.filter_by(user_id=current_user.id).all()
    if not holdings:
        flash('보유 종목이 없습니다. 자동 업데이트를 위해 먼저 거래 기록을 추가해주세요.', 'info')
        return redirect(url_for('main.dividends'))

    new_dividend_count = 0
    for holding in holdings:
        try:
            ticker = yf.Ticker(holding.symbol)
            hist_dividends = ticker.dividends
            if hist_dividends.empty: continue

            for pay_date, amount_per_share in hist_dividends.items():
                pay_date_obj = pay_date.date()
                exists = Dividend.query.filter_by(symbol=holding.symbol, dividend_date=pay_date_obj, user_id=current_user.id).first()
                if not exists and pay_date_obj > holding.purchase_date.date():
                    new_dividend = Dividend(
                        symbol=holding.symbol, amount=amount_per_share * holding.quantity,
                        amount_per_share=amount_per_share, dividend_date=pay_date_obj,
                        user_id=current_user.id
                    )
                    db.session.add(new_dividend)
                    new_dividend_count += 1
        except Exception as e:
            logger.error(f"'{holding.symbol}' 배당금 업데이트 오류: {e}")
    
    if new_dividend_count > 0:
        db.session.commit()
        flash(f'{new_dividend_count}개의 새로운 배당금 내역을 추가했습니다.', 'success')
    else:
        flash('업데이트할 새로운 배당금 내역이 없습니다.', 'info')
        
    return redirect(url_for('main.dividends'))

@main_bp.route('/allocation')
@login_required
def allocation():
    holdings = Holding.query.filter_by(user_id=current_user.id).all()
    allocation_data = []
    for holding in holdings:
        price_data = stock_api.get_stock_price(holding.symbol)
        if price_data and price_data.get('price'):
            current_value = holding.quantity * price_data['price']
            allocation_data.append({'symbol': holding.symbol, 'value': current_value})
            
    return render_template('allocation.html', allocation_data=allocation_data)
