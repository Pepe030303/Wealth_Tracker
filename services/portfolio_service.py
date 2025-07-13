# 📄 services/portfolio_service.py

from stock_api import stock_api
from utils import calculate_dividend_metrics, get_dividend_payout_schedule
from models import Holding
from datetime import datetime

def get_monthly_dividend_distribution(dividend_metrics):
    """
    [기준 변경] 월별 배당금을 계산할 때, Finnhub에서 제공하는 '지급일(PayDate)'을 기준으로 집계합니다.
    """
    detailed_monthly_data = {i: [] for i in range(12)}
    
    for symbol, metrics in dividend_metrics.items():
        dividend_schedule = get_dividend_payout_schedule(symbol)
        payout_schedule = dividend_schedule.get('payouts', [])
        
        if not payout_schedule:
            continue
            
        for payout in payout_schedule:
            # 🛠️ 변경: 집계 기준을 배당락일(ex_date)에서 지급일(pay_date)로 변경
            if not payout.get('pay_date'):
                continue # 지급일 정보가 없으면 건너뜀
                
            payout_date = datetime.strptime(payout['pay_date'], '%Y-%m-%d')
            month_index = payout_date.month - 1
            
            # 🛠️ 변경: 상세 데이터에 지급일(pay_date)과 배당락일(ex_date)을 모두 포함
            detailed_monthly_data[month_index].append({
                'symbol': symbol,
                'amount': payout['amount'] * metrics.get('quantity', 0),
                'profile': metrics.get('profile', {}),
                'quantity': metrics.get('quantity', 0),
                'dps_per_payout': payout['amount'],
                'ex_dividend_date': payout.get('ex_date'),
                'pay_date': payout.get('pay_date')
            })

    monthly_totals = [0] * 12
    for month, items in detailed_monthly_data.items():
        monthly_totals[month] = sum(item['amount'] for item in items)

    return {
        'labels': [f"{i+1}월" for i in range(12)],
        'datasets': [{'data': monthly_totals}],
        'detailed_data': detailed_monthly_data
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
        # 🛠️ 변경: 월 목록도 지급일 기준으로 생성된 것을 사용
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
    
    monthly_dividend_data = get_monthly_dividend_distribution(dividend_metrics)
    
    return {
        "holdings": holdings,
        "summary": summary_data,
        "sector_allocation": sector_allocation,
        "dividend_metrics": dividend_metrics,
        "monthly_dividend_data": monthly_dividend_data,
    }
