# 📄 services/portfolio_service.py

from stock_api import stock_api
from utils import calculate_dividend_metrics, get_dividend_payout_schedule
# 🛠️ 버그 수정: NameError 해결을 위해 db 객체를 app 모듈에서 import 합니다.
from app import db
from models import Holding, Dividend
from datetime import datetime
from sqlalchemy import func, extract

def get_differentiated_monthly_dividends(user_id, all_holdings, dividend_metrics_by_symbol):
    """
    [기능 개선] 과거(지급 완료) 배당과 미래(예정) 배당을 분리하여 월별 데이터를 집계합니다.
    - 과거: DB의 Dividend 테이블에서 실제 지급된 내역을 사용.
    - 미래: API를 통해 공시된 예정 배당을 사용.
    """
    current_year = datetime.now().year
    current_month = datetime.now().month
    
    paid_totals = [0] * 12
    scheduled_totals = [0] * 12
    detailed_data = {i: [] for i in range(12)}

    # 1. 과거 월 데이터 집계 (DB 기반)
    past_dividends = db.session.query(
        extract('month', Dividend.dividend_date).label('month'),
        func.sum(Dividend.amount).label('total_amount')
    ).filter(
        Dividend.user_id == user_id,
        extract('year', Dividend.dividend_date) == current_year,
        extract('month', Dividend.dividend_date) < current_month
    ).group_by('month').all()

    for div in past_dividends:
        month_index = div.month - 1
        paid_totals[month_index] = float(div.total_amount)
    
    # 과거 월 상세 데이터 추가
    past_dividends_details = Dividend.query.filter(
        Dividend.user_id == user_id,
        extract('year', Dividend.dividend_date) == current_year,
        extract('month', Dividend.dividend_date) < current_month
    ).all()

    for div in past_dividends_details:
        month_index = div.dividend_date.month - 1
        detailed_data[month_index].append({
            'symbol': div.symbol,
            'amount': div.amount,
            'dps_per_payout': div.amount_per_share,
            'ex_dividend_date': div.ex_dividend_date.strftime('%Y-%m-%d') if div.ex_dividend_date else None,
            'pay_date': div.dividend_date.strftime('%Y-%m-%d'),
            'status': '지급 완료'
        })

    # 2. 현재 월 및 미래 월 데이터 집계 (API 기반)
    holdings_map = {h.symbol: h.quantity for h in all_holdings}

    for symbol, quantity in holdings_map.items():
        dividend_schedule = get_dividend_payout_schedule(symbol)
        payout_schedule = dividend_schedule.get('payouts', [])
        
        for payout in payout_schedule:
            pay_date_str = payout.get('pay_date')
            if not pay_date_str: continue

            pay_date = datetime.strptime(pay_date_str, '%Y-%m-%d')
            if pay_date.year == current_year and pay_date.month >= current_month:
                month_index = pay_date.month - 1
                amount = payout['amount'] * quantity
                scheduled_totals[month_index] += amount
                
                detailed_data[month_index].append({
                    'symbol': symbol,
                    'amount': amount,
                    'dps_per_payout': payout['amount'],
                    'ex_dividend_date': payout.get('ex_date'),
                    'pay_date': pay_date_str,
                    'status': '예정'
                })

    # 프로필 정보 추가
    profiles = stock_api.get_stock_profiles_bulk(list(holdings_map.keys()))
    for month_items in detailed_data.values():
        for item in month_items:
            item['profile'] = profiles.get(item['symbol'], {})
            item['quantity'] = holdings_map.get(item['symbol'], 0)


    return {
        'labels': [f"{i+1}월" for i in range(12)],
        'datasets': [
            {'label': '지급 완료', 'data': paid_totals, 'backgroundColor': '#198754'},
            {'label': '예정', 'data': scheduled_totals, 'backgroundColor': '#a3cfbb'}
        ],
        'detailed_data': detailed_data
    }


def get_portfolio_analysis_data(user_id):
    """
    사용자의 전체 포트폴리오 데이터를 분석하고 종합하는 중앙 서비스 함수.
    """
    holdings = Holding.query.filter_by(user_id=user_id).all()
    if not holdings:
        return None

    symbols = list({h.symbol for h in holdings})
    price_data_map = stock_api.get_stock_prices_bulk(symbols)
    profile_data_map = stock_api.get_stock_profiles_bulk(symbols)
    
    dividend_metrics = calculate_dividend_metrics(holdings, price_data_map)
    for symbol, metrics in dividend_metrics.items():
        dividend_schedule = get_dividend_payout_schedule(symbol)
        metrics['payout_months'] = dividend_schedule.get('months', [])
        metrics['profile'] = profile_data_map.get(symbol, {})
        metrics['quantity'] = next((h.quantity for h in holdings if h.symbol == symbol), 0)


    total_investment = sum(h.quantity * h.purchase_price for h in holdings)
    total_current_value = sum(h.quantity * (price_data_map.get(h.symbol, {}).get('price') or h.purchase_price) for h in holdings)
    
    sector_details = {}
    for h in holdings:
        profile = profile_data_map.get(h.symbol, {}); 
        sector = profile.get('sector', 'N/A')
        current_value = h.quantity * (price_data_map.get(h.symbol, {}).get('price') or h.purchase_price)
        if sector not in sector_details:
            sector_details[sector] = {'total_value': 0, 'holdings': []}
        sector_details[sector]['total_value'] += current_value
        sector_details[sector]['holdings'].append({'symbol': h.symbol, 'value': current_value})

    sector_allocation = [{'sector': sector, 'value': details['total_value'], 'holdings': sorted(details['holdings'], key=lambda x: x['value'], reverse=True)} for sector, details in sector_details.items()]
    
    total_profit_loss = total_current_value - total_investment
    summary_data = {'total_investment': total_investment, 'total_current_value': total_current_value, 'total_profit_loss': total_profit_loss, 'total_return_percent': (total_profit_loss / total_investment * 100) if total_investment > 0 else 0}
    
    monthly_dividend_data = get_differentiated_monthly_dividends(user_id, holdings, dividend_metrics)
    
    return {
        "holdings": holdings,
        "summary": summary_data,
        "sector_allocation": sector_allocation,
        "dividend_metrics": dividend_metrics,
        "monthly_dividend_data": monthly_dividend_data,
    }
