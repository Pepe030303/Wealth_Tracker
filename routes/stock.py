# 📄 routes/stock.py
# 🛠️ New File: 개별 종목 및 API 관련 라우트를 분리한 Blueprint

from flask import Blueprint, jsonify, request, render_template, flash, redirect, url_for
from stock_api import stock_api, US_STOCKS_LIST
from flask_login import login_required

stock_bp = Blueprint('stock', __name__)

@stock_bp.route('/api/search-stocks')
@login_required
def search_stocks():
    query = request.args.get('q', '').upper()
    if not query:
        return jsonify([])
    results = [stock for stock in US_STOCKS_LIST if query in stock['ticker'].upper() or query in stock['name'].upper()]
    return jsonify(results[:10])

@stock_bp.route('/stock/<string:symbol>')
@login_required
def stock_detail(symbol):
    symbol = symbol.upper()
    profile = stock_api.get_stock_profile(symbol)
    price_data = stock_api.get_stock_price(symbol)
    price_history = stock_api.get_price_history(symbol, period='6mo')
    
    if not price_data or not price_history:
        flash(f'{symbol} 종목 정보를 가져오는 데 실패했습니다.', 'error')
        return redirect(request.referrer or url_for('portfolio.dashboard'))
        
    return render_template('stock_detail.html', 
                           symbol=symbol,
                           profile=profile,
                           price_data=price_data,
                           price_history=price_history)
