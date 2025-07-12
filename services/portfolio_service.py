# 📄 services/portfolio_service.py

from stock_api import stock_api
from utils import calculate_dividend_metrics, get_dividend_months
from models import Holding

def get_monthly_dividend_distribution(dividend_metrics):
    """
    [차트 개선] 월별 예상 배당금을 종목별 스택(stack) 형태로 계산.
    - Chart.js의 스택 막대 차트에서 사용할 수 있는 데이터셋 구조로 반환.
    - 각 월별로 어떤 종목이 얼마나 기여하는지 상세 데이터를 포함.
    """
    month_map = {'Jan':0, 'Feb':1, 'Mar':2, 'Apr':3, 'May':4, 'Jun':5, 'Jul':6, 'Aug':7, 'Sep':8, 'Oct':9, 'Nov':10, 'Dec':11}
    # { 'AAPL': [10, 0, ...], 'MSFT': [5, 0, ...] } 형태의 임시 데이터 구조
    monthly_data_by_symbol = {}

    for symbol, metrics in dividend_metrics.items():
        if symbol not in monthly_data_by_symbol:
            monthly_data_by_symbol[symbol] = [0] * 12

        dividend_info = get_dividend_months(symbol)
        payout_months = dividend_info.get("months", [])
        payout_count = dividend_info.get("count", 0)

        if payout_months and payout_count > 0 and metrics.get('expected_annual_dividend'):
            amount_per_payout = metrics['expected_annual_dividend'] / payout_count
            
            for month_str in payout_months:
                if month_str in month_map:
                    month_index = month_map[month_str]
                    monthly_data_by_symbol[symbol][month_index] += amount_per_payout

    # Chart.js가 요구하는 datasets 형식으로 변환
    datasets = []
    # 색상 팔레트
    colors = ['#0d6efd', '#198754', '#ffc107', '#dc3545', '#6c757d', '#0dcaf0', '#6f42c1', '#fd7e14', '#20c997', '#6610f2']
    color_index = 0
    for symbol, data in monthly_data_by_symbol.items():
        datasets.append({
            'label': symbol,
            'data': [round(d, 2) for d in data],
            'backgroundColor': colors[color_index % len(colors)],
        })
        color_index += 1

    return {
        'labels': [f"{i+1}월" for i in range(12)],
        'datasets': datasets
    }


def get_portfolio_analysis_data(user_id):
    """
    사용자의 전체 포트폴리오 데이터를 분석하고 종합하는 중앙 서비스 함수.
    """
    holdings = Holding.query.filter_by(user_id=user_id).all()
    if not holdings:
        return None

    symbols = {h.symbol for h in holdings}
    price_data_map = {s: stock_api.get_stock_price(s) for s in symbols}
    
    dividend_metrics = calculate_dividend_metrics(holdings, price_data_map)
    for symbol, metrics in dividend_metrics.items():
        dividend_info = get_dividend_months(symbol)
        metrics['payout_months'] = dividend_info.get("months", [])

    total_investment = sum(h.quantity * h.purchase_price for h in holdings)
    total_current_value = sum(h.quantity * (price_data_map.get(h.symbol, {}).get('price') or h.purchase_price) for h in holdings)
    
    sector_details = {}
    profile_data_map = {s: stock_api.get_stock_profile(s) for s in symbols}
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
    
    # 개선된 월별 배당금 데이터 계산
    monthly_dividend_data = get_monthly_dividend_distribution(dividend_metrics)
    
    return {
        "holdings": holdings,
        "summary": summary_data,
        "sector_allocation": sector_allocation,
        "dividend_metrics": dividend_metrics,
        "monthly_dividend_data": monthly_dividend_data,
    }
