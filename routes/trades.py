# 📄 routes/trades.py
# 🛠️ New File: 거래 기록 관련 라우트를 분리한 Blueprint

from flask import Blueprint, render_template, request, redirect, url_for, flash
from datetime import datetime
from app import db
from models import Trade, Holding
from services.portfolio_service import recalculate_holdings
from flask_login import current_user, login_required
import logging

logger = logging.getLogger(__name__)
trades_bp = Blueprint('trades', __name__)

@trades_bp.route('/')
@login_required
def trades():
    trades = Trade.query.filter_by(user_id=current_user.id).order_by(Trade.trade_date.desc(), Trade.id.desc()).all()
    return render_template('trades.html', trades=trades)

@trades_bp.route('/add', methods=['POST'])
@login_required
def add_trade():
    symbol = request.form.get('symbol', '').upper().strip()
    try:
        trade_type = request.form.get('trade_type')
        quantity = float(request.form.get('quantity'))
        price = float(request.form.get('price'))
        trade_date = datetime.strptime(request.form.get('trade_date'), '%Y-%m-%d').date()
        
        if not all([symbol, trade_type, quantity > 0, price > 0]):
            raise ValueError("모든 필드를 올바르게 입력해주세요.")
            
        if trade_type == 'sell':
            holding = Holding.query.filter_by(user_id=current_user.id, symbol=symbol).first()
            if not holding or holding.quantity < quantity:
                flash(f'보유 수량이 부족하여 매도할 수 없습니다. (보유: {holding.quantity if holding else 0})', 'error')
                return redirect(url_for('trades.trades'))
                
        trade = Trade(symbol=symbol, trade_type=trade_type, quantity=quantity, price=price, trade_date=trade_date, user_id=current_user.id)
        db.session.add(trade)
        db.session.commit()
        recalculate_holdings(current_user.id)
        flash(f'{symbol} {trade_type.upper()} 거래가 성공적으로 추가되었습니다.', 'success')
        
    except (ValueError, TypeError) as e:
        flash(str(e) or '수량, 가격, 날짜를 올바른 형식으로 입력해주세요.', 'error')
        db.session.rollback()
    except Exception as e:
        logger.error(f"거래 추가 오류: {e}")
        flash('거래 추가 중 오류가 발생했습니다.', 'error')
        db.session.rollback()
        
    return redirect(url_for('trades.trades'))

@trades_bp.route('/delete/<int:trade_id>')
@login_required
def delete_trade(trade_id):
    trade = Trade.query.filter_by(id=trade_id, user_id=current_user.id).first_or_404()
    db.session.delete(trade)
    db.session.commit()
    recalculate_holdings(current_user.id)
    flash(f'{trade.symbol} 거래가 삭제되었습니다.', 'success')
    return redirect(url_for('trades.trades'))
