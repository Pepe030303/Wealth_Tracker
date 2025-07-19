# 📄 routes/portfolio.py
from flask import Blueprint, render_template, request, current_app
from sqlalchemy import func
# 🛠️ Refactor: app 대신 extensions에서 db, task_queue 객체를 가져옵니다.
from extensions import db, task_queue
from tasks import update_all_dividends_for_user
from models import Dividend
from services.portfolio_service import (
    get_portfolio_analysis_data,
    get_processed_holdings_data,
    get_portfolio_allocation_data,
    get_dividend_allocation_data_from_metrics
)
from flask_login import current_user, login_required

portfolio_bp = Blueprint('portfolio', __name__)

@portfolio_bp.route('/')
@login_required
def dashboard():
    portfolio_data = get_portfolio_analysis_data(current_user.id)
    if not portfolio_data:
        return render_template('dashboard.html', summary={}, sector_allocation=[], monthly_dividend_data={})
    return render_template('dashboard.html', 
                           summary=portfolio_data['summary'], 
                           sector_allocation=portfolio_data['sector_allocation'], 
                           monthly_dividend_data=portfolio_data['monthly_dividend_data'])

@portfolio_bp.route('/dividends')
@login_required
def dividends():
    portfolio_data = get_portfolio_analysis_data(current_user.id)
    if not portfolio_data:
        return render_template('dividends.html', dividend_metrics=[], dividend_allocation_data=[])
    
    dividend_allocation_data = get_dividend_allocation_data_from_metrics(portfolio_data['dividend_metrics'])
    
    return render_template('dividends.html',
                           dividend_metrics=portfolio_data['dividend_metrics'],
                           monthly_dividend_data=portfolio_data['monthly_dividend_data'],
                           dividend_allocation_data=dividend_allocation_data,
                           tax_rate=current_app.config.get('TAX_RATE', 0.154))

@portfolio_bp.route('/allocation')
@login_required
def allocation():
    allocation_data = get_portfolio_allocation_data(current_user.id)
    return render_template('allocation.html', allocation_data=allocation_data)

@portfolio_bp.route('/holdings')
@login_required
def holdings():
    holdings_data = get_processed_holdings_data(current_user.id)
    return render_template('holdings.html', holdings_data=holdings_data)

@portfolio_bp.route('/dividends/history')
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
