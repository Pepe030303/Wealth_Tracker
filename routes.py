from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from datetime import datetime, date
from sqlalchemy import func, extract
from app import db
from models import Holding, Dividend, StockPrice, Trade, recalculate_holdings, calculate_dividend_metrics, get_dividend_allocation_data, get_stock_logo_url, get_company_name, get_dividend_months
from stock_api import stock_api
import logging

logger = logging.getLogger(__name__)

main_bp = Blueprint('main', __name__)

def enhance_stock_data(symbol):
    """Add logo URL, company name, and dividend months to stock data"""
    return {
        'symbol': symbol,
        'logo_url': get_stock_logo_url(symbol),
        'company_name': get_company_name(symbol),
        'dividend_months': get_dividend_months(symbol)
    }

@main_bp.route('/')
def dashboard():
    """대시보드 페이지"""
    try:
        # 보유 종목 조회
        holdings = Holding.query.all()
        
        # 포트폴리오 요약 계산
        total_investment = sum(h.quantity * h.purchase_price for h in holdings)
        total_current_value = 0
        total_profit_loss = 0
        
        holdings_data = []
        for holding in holdings:
            # 현재 주가 조회
            price_data = stock_api.get_stock_price(holding.symbol)
            if price_data:
                current_price = price_data['price']
                current_value = holding.quantity * current_price
                profit_loss = current_value - (holding.quantity * holding.purchase_price)
                profit_loss_percent = (profit_loss / (holding.quantity * holding.purchase_price)) * 100
                
                holdings_data.append({
                    'holding': holding,
                    'current_price': current_price,
                    'current_value': current_value,
                    'profit_loss': profit_loss,
                    'profit_loss_percent': profit_loss_percent,
                    'change': price_data.get('change', 0),
                    'change_percent': price_data.get('change_percent', 0)
                })
                
                total_current_value += current_value
                total_profit_loss += profit_loss
        
        # 전체 수익률 계산
        total_return_percent = (total_profit_loss / total_investment * 100) if total_investment > 0 else 0
        
        # 월별 배당금 합계
        current_year = datetime.now().year
        monthly_dividends = db.session.query(
            extract('month', Dividend.dividend_date).label('month'),
            func.sum(Dividend.amount).label('total')
        ).filter(
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
        
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        flash('대시보드 데이터를 불러오는 중 오류가 발생했습니다.', 'error')
        return render_template('dashboard.html', holdings_data=[], total_investment=0,
                             total_current_value=0, total_profit_loss=0, total_return_percent=0,
                             dividend_data=[0]*12)

@main_bp.route('/holdings')
def holdings():
    """보유 종목 페이지"""
    try:
        holdings = Holding.query.all()
        holdings_data = []
        
        for holding in holdings:
            price_data = stock_api.get_stock_price(holding.symbol)
            if price_data:
                current_price = price_data['price']
                current_value = holding.quantity * current_price
                profit_loss = current_value - (holding.quantity * holding.purchase_price)
                profit_loss_percent = (profit_loss / (holding.quantity * holding.purchase_price)) * 100
                
                holdings_data.append({
                    'holding': holding,
                    'current_price': current_price,
                    'current_value': current_value,
                    'profit_loss': profit_loss,
                    'profit_loss_percent': profit_loss_percent,
                    'change': price_data.get('change', 0),
                    'change_percent': price_data.get('change_percent', 0)
                })
        
        return render_template('holdings.html', holdings_data=holdings_data)
        
    except Exception as e:
        logger.error(f"Holdings error: {e}")
        flash('보유 종목 데이터를 불러오는 중 오류가 발생했습니다.', 'error')
        return render_template('holdings.html', holdings_data=[])

@main_bp.route('/holdings/add', methods=['POST'])
def add_holding():
    """보유 종목 추가 - 이제 거래 기록을 통해 관리"""
    flash('보유 종목은 이제 거래 기록을 통해 자동으로 계산됩니다. 거래 페이지에서 매수/매도 기록을 추가해주세요.', 'info')
    return redirect(url_for('main.trades'))

@main_bp.route('/holdings/delete/<int:holding_id>')
def delete_holding(holding_id):
    """보유 종목 삭제 - 이제 거래 기록을 통해 관리"""
    flash('보유 종목은 이제 거래 기록을 통해 자동으로 계산됩니다. 거래 페이지에서 관련 거래를 삭제해주세요.', 'info')
    return redirect(url_for('main.trades'))

@main_bp.route('/dividends')
def dividends():
    """배당금 페이지"""
    try:
        # 전체 배당금 기록
        dividends = Dividend.query.order_by(Dividend.dividend_date.desc()).all()
        
        # 월별 배당금 집계
        current_year = datetime.now().year
        monthly_dividends = db.session.query(
            extract('month', Dividend.dividend_date).label('month'),
            func.sum(Dividend.amount).label('total')
        ).filter(
            extract('year', Dividend.dividend_date) == current_year
        ).group_by(extract('month', Dividend.dividend_date)).all()
        
        dividend_data = [0] * 12
        for month, total in monthly_dividends:
            dividend_data[int(month) - 1] = float(total)
        
        # 배당 지표 계산
        dividend_metrics = calculate_dividend_metrics()
        
        # 배당 배분 데이터 (차트용)
        allocation_data = get_dividend_allocation_data()
        
        return render_template('dividends.html', 
                             dividends=dividends, 
                             dividend_data=dividend_data,
                             dividend_metrics=dividend_metrics,
                             allocation_data=allocation_data)
        
    except Exception as e:
        logger.error(f"Dividends error: {e}")
        flash('배당금 데이터를 불러오는 중 오류가 발생했습니다.', 'error')
        return render_template('dividends.html', dividends=[], dividend_data=[0]*12, dividend_metrics={}, allocation_data=[])

@main_bp.route('/dividends/add', methods=['POST'])
def add_dividend():
    """배당금 추가"""
    try:
        symbol = request.form.get('symbol', '').upper().strip()
        amount = float(request.form.get('amount', 0))
        amount_per_share = request.form.get('amount_per_share')
        dividend_date = datetime.strptime(request.form.get('dividend_date'), '%Y-%m-%d').date()
        ex_dividend_date = request.form.get('ex_dividend_date')
        payout_frequency = int(request.form.get('payout_frequency', 4))
        
        if not symbol or amount <= 0:
            flash('모든 필드를 올바르게 입력해주세요.', 'error')
            return redirect(url_for('main.dividends'))
        
        # 배당락일 처리
        ex_div_date = None
        if ex_dividend_date:
            ex_div_date = datetime.strptime(ex_dividend_date, '%Y-%m-%d').date()
        
        # 주당 배당금 처리
        per_share_amount = None
        if amount_per_share:
            per_share_amount = float(amount_per_share)
        
        dividend = Dividend(
            symbol=symbol,
            amount=amount,
            amount_per_share=per_share_amount,
            dividend_date=dividend_date,
            ex_dividend_date=ex_div_date,
            payout_frequency=payout_frequency
        )
        
        db.session.add(dividend)
        db.session.commit()
        
        flash(f'{symbol} 배당금이 성공적으로 추가되었습니다.', 'success')
        
    except ValueError:
        flash('금액과 날짜를 올바르게 입력해주세요.', 'error')
    except Exception as e:
        logger.error(f"Add dividend error: {e}")
        flash('배당금 추가 중 오류가 발생했습니다.', 'error')
        db.session.rollback()
    
    return redirect(url_for('main.dividends'))

@main_bp.route('/dividends/delete/<int:dividend_id>')
def delete_dividend(dividend_id):
    """배당금 삭제"""
    try:
        dividend = Dividend.query.get_or_404(dividend_id)
        symbol = dividend.symbol
        
        db.session.delete(dividend)
        db.session.commit()
        
        flash(f'{symbol} 배당금이 삭제되었습니다.', 'success')
        
    except Exception as e:
        logger.error(f"Delete dividend error: {e}")
        flash('배당금 삭제 중 오류가 발생했습니다.', 'error')
        db.session.rollback()
    
    return redirect(url_for('main.dividends'))

@main_bp.route('/allocation')
def allocation():
    """포트폴리오 비중 페이지"""
    try:
        holdings = Holding.query.all()
        allocation_data = []
        
        for holding in holdings:
            price_data = stock_api.get_stock_price(holding.symbol)
            if price_data:
                current_value = holding.quantity * price_data['price']
                allocation_data.append({
                    'symbol': holding.symbol,
                    'value': current_value
                })
        
        return render_template('allocation.html', allocation_data=allocation_data)
        
    except Exception as e:
        logger.error(f"Allocation error: {e}")
        flash('포트폴리오 비중 데이터를 불러오는 중 오류가 발생했습니다.', 'error')
        return render_template('allocation.html', allocation_data=[])

@main_bp.route('/api/stock-price/<symbol>')
def get_stock_price(symbol):
    """AJAX용 주가 조회 API"""
    try:
        price_data = stock_api.get_stock_price(symbol.upper())
        if price_data:
            return jsonify(price_data)
        else:
            return jsonify({'error': 'Stock price not found'}), 404
            
    except Exception as e:
        logger.error(f"Stock price API error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@main_bp.route('/api/refresh-prices')
def refresh_prices():
    """모든 보유 종목 가격 갱신"""
    try:
        holdings = Holding.query.all()
        symbols = [h.symbol for h in holdings]
        
        updated_prices = {}
        for symbol in symbols:
            price_data = stock_api.get_stock_price(symbol)
            if price_data:
                updated_prices[symbol] = price_data
        
        return jsonify(updated_prices)
        
    except Exception as e:
        logger.error(f"Refresh prices error: {e}")
        return jsonify({'error': 'Failed to refresh prices'}), 500

@main_bp.route('/trades')
def trades():
    """거래 기록 페이지"""
    try:
        # 거래 기록 조회 (최신순)
        trades = Trade.query.order_by(Trade.trade_date.desc(), Trade.id.desc()).all()
        
        # 심볼별 거래 요약
        trade_summary = {}
        for trade in trades:
            if trade.symbol not in trade_summary:
                trade_summary[trade.symbol] = {
                    'total_bought': 0,
                    'total_sold': 0,
                    'net_quantity': 0,
                    'total_cost': 0
                }
            
            if trade.trade_type == 'buy':
                trade_summary[trade.symbol]['total_bought'] += trade.quantity
                trade_summary[trade.symbol]['total_cost'] += trade.quantity * trade.price
            else:
                trade_summary[trade.symbol]['total_sold'] += trade.quantity
                trade_summary[trade.symbol]['total_cost'] -= trade.quantity * trade.price
            
            trade_summary[trade.symbol]['net_quantity'] = (
                trade_summary[trade.symbol]['total_bought'] - 
                trade_summary[trade.symbol]['total_sold']
            )
        
        return render_template('trades.html', trades=trades, trade_summary=trade_summary)
        
    except Exception as e:
        logger.error(f"Trades error: {e}")
        flash('거래 기록을 불러오는 중 오류가 발생했습니다.', 'error')
        return render_template('trades.html', trades=[], trade_summary={})

@main_bp.route('/trades/add', methods=['POST'])
def add_trade():
    """거래 추가"""
    try:
        symbol = request.form.get('symbol', '').upper().strip()
        trade_type = request.form.get('trade_type', '').lower().strip()
        quantity = int(request.form.get('quantity', 0))
        price = float(request.form.get('price', 0))
        trade_date = datetime.strptime(request.form.get('trade_date'), '%Y-%m-%d').date()
        
        # 입력 검증
        if not symbol or trade_type not in ['buy', 'sell'] or quantity <= 0 or price <= 0:
            flash('모든 필드를 올바르게 입력해주세요.', 'error')
            return redirect(url_for('main.trades'))
        
        # 매도 시 보유 수량 확인
        if trade_type == 'sell':
            # 현재까지의 순 보유량 계산
            existing_trades = Trade.query.filter_by(symbol=symbol).filter(
                Trade.trade_date <= trade_date
            ).order_by(Trade.trade_date, Trade.id).all()
            
            net_quantity = 0
            for existing_trade in existing_trades:
                if existing_trade.trade_type == 'buy':
                    net_quantity += existing_trade.quantity
                else:
                    net_quantity -= existing_trade.quantity
            
            if quantity > net_quantity:
                flash(f'{symbol} 종목의 보유 수량이 부족합니다. (현재 보유: {net_quantity})', 'error')
                return redirect(url_for('main.trades'))
        
        # 거래 기록 추가
        trade = Trade(
            symbol=symbol,
            trade_type=trade_type,
            quantity=quantity,
            price=price,
            trade_date=trade_date
        )
        
        db.session.add(trade)
        db.session.commit()
        
        # 보유 종목 재계산
        recalculate_holdings()
        
        flash(f'{symbol} {trade_type.upper()} 거래가 성공적으로 추가되었습니다.', 'success')
        
    except ValueError:
        flash('수량, 가격, 날짜를 올바르게 입력해주세요.', 'error')
    except Exception as e:
        logger.error(f"Add trade error: {e}")
        flash('거래 추가 중 오류가 발생했습니다.', 'error')
        db.session.rollback()
    
    return redirect(url_for('main.trades'))

@main_bp.route('/trades/delete/<int:trade_id>')
def delete_trade(trade_id):
    """거래 삭제"""
    try:
        trade = Trade.query.get_or_404(trade_id)
        symbol = trade.symbol
        
        db.session.delete(trade)
        db.session.commit()
        
        # 보유 종목 재계산
        recalculate_holdings()
        
        flash(f'{symbol} 거래가 삭제되었습니다.', 'success')
        
    except Exception as e:
        logger.error(f"Delete trade error: {e}")
        flash('거래 삭제 중 오류가 발생했습니다.', 'error')
        db.session.rollback()
    
    return redirect(url_for('main.trades'))

@main_bp.route('/trades/recalculate')
def recalculate_holdings_route():
    """보유 종목 재계산"""
    try:
        recalculate_holdings()
        flash('보유 종목이 재계산되었습니다.', 'success')
    except Exception as e:
        logger.error(f"Recalculate holdings error: {e}")
        flash('보유 종목 재계산 중 오류가 발생했습니다.', 'error')
    
    return redirect(url_for('main.trades'))
