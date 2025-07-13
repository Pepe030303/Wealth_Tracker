# 📄 services/portfolio_service.py

from stock_api import stock_api
from utils import calculate_dividend_metrics, get_dividend_payout_schedule
from models import Holding
from datetime import datetime

def get_monthly_dividend_distribution(dividend_metrics):
    """
    [기능 개선] 월별 배당금을 계산할 때, 상세 배당락일 정보를 포함하여 반환.
    """
    detailed_monthly_data = {i: [] for i in range(12)}
    
    for symbol, metrics in dividend_metrics.items():

        # 🛠️ Refactoring: 반환된 딕셔너리에서 'payouts' 리스트를 직접 사용
        dividend_schedule = get_dividend_payout_schedule(symbol)
        payout_schedule = dividend_schedule['payouts']
        
        if not payout_schedule:
            continue
            
        for payout in payout_schedule:
            payout_date = datetime.strptime(payout['date'], '%Y-%m-%d')
            month_index = payout_date.month - 1
            
            detailed_monthly_data[month_index].append({
                'symbol': symbol,
                'amount': payout['amount'] * metrics.get('quantity', 0),
                'profile': metrics.get('profile', {}),
                'quantity': metrics.get('quantity', 0),
                'dps_per_payout': payout['amount'],
                'ex_dividend_date': payout['date']
            })

    monthly_totals = [0] * 12
    for month, items in detailed_monthly_data.items():
        monthly_totals[month] = sum(item['amount'] for item in items)

    return {
        'labels': [f"{i+1}월" for i in range(12)],
        'datasets': [{'data': monthly_totals}],
        'detailed_data': detailed_monthly_data
    }
=======
        if symbol not in monthly_data_by_symbol: monthly_data_by_symbol[symbol] = [0] * 12
        dividend_info = get_dividend_months(symbol)
        payout_months = dividend_info.get("months", [])
        payout_count = dividend_info.get("count", 0)
        if payout_months and payout_count > 0 and metrics.get('expected_annual_dividend'):
            amount_per_payout = metrics['expected_annual_dividend'] / payout_count

            
            # 🛠️ 개선: 1회 지급 시 주당 배당금 계산

            dps_per_payout = (metrics.get('dividend_per_share', 0) / payout_count) if payout_count > 0 else 0
            for month_str in payout_months:
                if month_str in month_map:
                    month_index = month_map[month_str]
                    monthly_data_by_symbol[symbol][month_index] += amount_per_payout
                    # 🛠️ 개선: 상세 데이터에 수량 및 주당 배당금 정보 추가
                    detailed_monthly_data[month_index].append({
                        'symbol': symbol, 'amount': amount_per_payout,
                        'profile': metrics.get('profile', {}),
                        'quantity': metrics.get('quantity', 0),
                        'dps_per_payout': dps_per_payout
                    })


    # Chart.js가 요구하는 datasets 형식으로 변환 (스택 차트용 - 대시보드에서 사용)

    datasets = []
    colors = ['#0d6efd', '#198754', '#ffc107', '#dc3545', '#6c757d', '#0dcaf0', '#6f42c1', '#fd7e14', '#20c997', '#6610f2']
    color_index = 0
    for symbol, data in monthly_data_by_symbol.items():
        datasets.append({'label': symbol, 'data': [round(d, 2) for d in data], 'backgroundColor': colors[color_index % len(colors)]})
        color_index += 1
    return {'labels': [f"{i+1}월" for i in range(12)], 'datasets': datasets, 'detailed_data': detailed_monthly_data}



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

        h = next((h for h in holdings if h.symbol == symbol), None)
        current_price = price_data_map.get(symbol, {}).get('price') or (h.purchase_price if h else 0)
        quantity = h.quantity if h else 0
        current_value = current_price * quantity
        
        # 🛠️ Refactoring: 복잡한 계산 로직을 제거하고, 반환된 딕셔너리에서 'months'를 직접 사용
        dividend_schedule = get_dividend_payout_schedule(symbol)
        metrics['payout_months'] = dividend_schedule['months']

        metrics['profile'] = profile_data_map.get(symbol, {})
        metrics['quantity'] = quantity
        metrics['current_value'] = current_value

        dividend_info = get_dividend_months(symbol)
        metrics['payout_months'] = dividend_info.get("months", [])
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
