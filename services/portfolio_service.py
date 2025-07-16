# 📄 services/portfolio_service.py
from stock_api import stock_api
from utils import (
    calculate_dividend_metrics, 
    get_dividend_payout_schedule,
    get_adjusted_dividend_history,
    calculate_5yr_avg_dividend_growth
)
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
    holdings = Holding.query.filter_by(user_id=user_id).order_by(Holding.symbol).all()
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
    return holdings_data

def get_monthly_dividend_distribution(dividend_metrics):
    detailed_monthly_data = {i: [] for i in range(12)}
    for symbol, metrics in dividend_metrics:
        dividend_schedule = get_dividend_payout_schedule(symbol)
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
    
    dividend_metrics = calculate_dividend_metrics(holdings, price_data_map)
    for symbol, metrics in dividend_metrics.items():
        h = next((h for h in holdings if h.symbol == symbol), None)
        quantity = h.quantity if h else 0
        
        dividend_schedule = get_dividend_payout_schedule(symbol)
        metrics['payout_months'] = dividend_schedule.get('months', [])
        metrics['profile'] = profile_data_map.get(symbol, {})
        metrics['quantity'] = quantity
        
        adjusted_div_data = get_adjusted_dividend_history(symbol)
        metrics['note'] = adjusted_div_data.get('note')
        metrics['adjusted_history'] = adjusted_div_data.get('history', [])
        metrics['dgr_5y'] = calculate_5yr_avg_dividend_growth(metrics['adjusted_history'])

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
