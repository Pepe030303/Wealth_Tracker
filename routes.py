# 📄 routes.py
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from datetime import datetime
from sqlalchemy import func
from app import db, task_queue, app
from tasks import update_all_dividends_for_user
from models import User, Holding, Dividend, Trade
from stock_api import stock_api, US_STOCKS_LIST
from services.portfolio_service import (
    get_portfolio_analysis_data,
    get_processed_holdings_data,
    recalculate_holdings,
    get_portfolio_allocation_data,
    get_dividend_allocation_data_from_metrics # 🛠️ Refactor: 함수 임포트 경로 변경
)
from flask_login import login_user, logout_user, current_user, login_required
import logging

logger = logging.getLogger(__name__)
main_bp = Blueprint('main', __name__)

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
        return render_template('dividends.html', dividend_metrics=[], dividend_allocation_data=[])

    # 🛠️ Refactor: 템플릿에서 함수를 호출하는 대신, 라우트에서 데이터를 미리 계산하여 전달
    dividend_allocation_data = get_dividend_allocation_data_from_metrics(portfolio_data['dividend_metrics'])
    
    return render_template('dividends.html',
                           dividend_metrics=portfolio_data['dividend_metrics'],
                           monthly_dividend_data=portfolio_data['monthly_dividend_data'],
                           dividend_allocation_data=dividend_allocation_data,
                           tax_rate=app.config.get('TAX_RATE', 0.154))

# 🛠️ 추가: '포트폴리오 비중' 페이지를 위한 라우트 신설
@main_bp.route('/allocation')
@login_required
def allocation():
    allocation_data = get_portfolio_allocation_data(current_user.id)
    return render_template('allocation.html', allocation_data=allocation_data)

@main_bp.route('/holdings')
@login_required
def holdings():
    holdings_data = get_processed_holdings_data(current_user.id)
    return render_template('holdings.html', holdings_data=holdings_data)

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
                           price_history=price_history)```

# 📄 Wealth_Tracker-develop/services/portfolio_service.py
```python
# 📄 services/portfolio_service.py
from stock_api import stock_api
from services import stock_data_service
from models import Holding, Trade
from app import db
from datetime import datetime

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
            holding = Holding(symbol=symbol, quantity=final_quantity, purchase_price=avg_price, purchase_date=datetime.combine(latest_buy_date, datetime.min.time()) if latest_buy_date else None, user_id=user_id)
            db.session.add(holding)
    db.session.commit()

def get_processed_holdings_data(user_id):
    holdings = Holding.query.filter_by(user_id=user_id).all()
    if not holdings: return []
    symbols = {h.symbol for h in holdings}
    price_data_map = stock_api.get_stock_prices_bulk(symbols)
    profile_data_map = stock_api.get_stock_profiles_bulk(symbols)
    holdings_data = []
    for h in holdings:
        price_data = price_data_map.get(h.symbol)
        current_price = price_data['price'] if price_data else h.purchase_price
        total_cost = h.quantity * h.purchase_price
        current_value = h.quantity * current_price
        profit_loss = current_value - total_cost
        profit_loss_percent = (profit_loss / total_cost) * 100 if total_cost > 0 else 0
        holdings_data.append({'holding': h, 'profile': profile_data_map.get(h.symbol), 'current_price': current_price, 'total_cost': total_cost, 'current_value': current_value, 'profit_loss': profit_loss, 'profit_loss_percent': profit_loss_percent,})
    
    holdings_data.sort(key=lambda x: x['current_value'], reverse=True)
    
    return holdings_data

def get_monthly_dividend_distribution(dividend_metrics):
    detailed_monthly_data = {i: [] for i in range(12)}
    for symbol, metrics in dividend_metrics:
        dividend_schedule = stock_data_service.get_dividend_payout_schedule(symbol)
        payout_schedule = dividend_schedule['payouts']
        if not payout_schedule: continue
        for payout in payout_schedule:
            payout_date = datetime.strptime(payout['date'], '%Y-%m-%d')
            month_index = payout_date.month - 1
            detailed_monthly_data[month_index].append({'symbol': symbol, 'amount': payout['amount'] * metrics.get('quantity', 0), 'profile': metrics.get('profile', {}), 'quantity': metrics.get('quantity', 0), 'dps_per_payout': payout['amount'], 'ex_dividend_date': payout['date']})
    monthly_totals = [sum(item['amount'] for item in items) for items in detailed_monthly_data.values()]
    return {'labels': [f"{i+1}월" for i in range(12)], 'datasets': [{'data': monthly_totals}], 'detailed_data': detailed_monthly_data}


def get_portfolio_analysis_data(user_id):
    holdings = Holding.query.filter_by(user_id=user_id).all()
    if not holdings: return None

    symbols = list({h.symbol for h in holdings})
    price_data_map = stock_api.get_stock_prices_bulk(symbols)
    profile_data_map = stock_api.get_stock_profiles_bulk(symbols)
    
    dividend_metrics = stock_data_service.calculate_dividend_metrics(holdings, price_data_map)
    for symbol, metrics in dividend_metrics.items():
        h = next((h for h in holdings if h.symbol == symbol), None)
        quantity = h.quantity if h else 0
        
        dividend_schedule = stock_data_service.get_dividend_payout_schedule(symbol)
        metrics['payout_months'] = dividend_schedule.get('months', [])
        metrics['profile'] = profile_data_map.get(symbol, {})
        metrics['quantity'] = quantity
        
        adjusted_div_data = stock_data_service.get_adjusted_dividend_history(symbol)
        metrics['note'] = adjusted_div_data.get('note')
        metrics['adjusted_history'] = adjusted_div_data.get('history', [])
        metrics['dgr_5y'] = stock_data_service.calculate_5yr_avg_dividend_growth(metrics['adjusted_history'])

    sorted_dividend_metrics = sorted(
        dividend_metrics.items(),
        key=lambda item: item[1].get('expected_annual_dividend', 0),
        reverse=True
    )

    total_investment = sum(h.quantity * h.purchase_price for h in holdings)
    total_current_value = sum(h.quantity * (price_data_map.get(h.symbol, {}).get('price') or h.purchase_price) for h in holdings)
    
    sector_details = {}
    for h in holdings:
        profile = profile_data_map.get(h.symbol, {}); sector = profile.get('sector', 'N/A')
        current_value = h.quantity * (price_data_map.get(h.symbol, {}).get('price') or h.purchase_price)
        if sector not in sector_details: sector_details[sector] = {'total_value': 0, 'holdings': []}
        sector_details[sector]['total_value'] += current_value
        sector_details[sector]['holdings'].append({'symbol': h.symbol, 'value': current_value})

    sector_allocation = [{'sector': sector, 'value': details['total_value'], 'holdings': sorted(details['holdings'], key=lambda x: x['value'], reverse=True)} for sector, details in sector_details.items()]
    total_profit_loss = total_current_value - total_investment
    summary_data = {'total_investment': total_investment, 'total_current_value': total_current_value, 'total_profit_loss': total_profit_loss, 'total_return_percent': (total_profit_loss / total_investment * 100) if total_investment > 0 else 0}
    
    monthly_dividend_data = get_monthly_dividend_distribution(sorted_dividend_metrics)
    
    return {"holdings": holdings, "summary": summary_data, "sector_allocation": sector_allocation, "dividend_metrics": sorted_dividend_metrics, "monthly_dividend_data": monthly_dividend_data}

def get_portfolio_allocation_data(user_id):
    """보유 종목의 자산 배분(비중) 데이터를 계산하여 반환합니다."""
    holdings = Holding.query.filter_by(user_id=user_id).all()
    if not holdings:
        return []

    symbols = {h.symbol for h in holdings}
    price_data_map = stock_api.get_stock_prices_bulk(symbols)
    
    allocation_data = []
    for h in holdings:
        price_data = price_data_map.get(h.symbol)
        current_price = price_data['price'] if price_data else h.purchase_price
        current_value = h.quantity * current_price
        allocation_data.append({
            'symbol': h.symbol,
            'value': current_value,
        })
    
    # 평가금액 기준으로 내림차순 정렬
    allocation_data.sort(key=lambda x: x['value'], reverse=True)
    return allocation_data

# 🛠️ Refactor: utils.py에서 비즈니스 로직을 이전하고 이름 변경
def get_dividend_allocation_data_from_metrics(dividend_metrics):
    """주어진 배당 지표에서 배당 비중 차트용 데이터를 추출합니다."""
    return [{'symbol': item[0], 'value': item[1]['expected_annual_dividend']} for item in dividend_metrics if item[1].get('expected_annual_dividend', 0) > 0]
