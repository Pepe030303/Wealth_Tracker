# 📄 services/portfolio_service.py

from stock_api import stock_api
from utils import calculate_dividend_metrics, get_dividend_months
from models import Holding

def get_monthly_dividend_distribution(dividend_metrics):
    """
    [차트 개선] 월별 배당금을 종목별 스택(stack) 및 상세 데이터 형태로 계산.
    - Chart.js의 막대 차트에서 사용할 데이터셋 구조와
    - 월 클릭 시 상세 내역을 보여주기 위한 상세 데이터를 함께 반환.
    """
    month_map = {'Jan':0, 'Feb':1, 'Mar':2, 'Apr':3, 'May':4, 'Jun':5, 'Jul':6, 'Aug':7, 'Sep':8, 'Oct':9, 'Nov':10, 'Dec':11}
    
    # 🛠️ 개선: 월별 상세 데이터를 저장하기 위한 구조
    # 예: { 0: [{'symbol': 'AAPL', 'amount': 10.0, 'logo_url': '...'}, ...], 1: [...] }
    detailed_monthly_data = {i: [] for i in range(12)}
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
                    # 상세 데이터 추가
                    detailed_monthly_data[month_index].append({
                        'symbol': symbol,
                        'amount': amount_per_payout,
                        'profile': metrics.get('profile', {})
                    })

    # Chart.js가 요구하는 datasets 형식으로 변환 (스택 차트용 - 대시보드에서 사용)
    datasets = []
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
        'datasets': datasets,
        'detailed_data': detailed_monthly_data # 템플릿에 전달할 상세 데이터
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
    profile_data_map = {s: stock_api.get_stock_profile(s) for s in symbols}
    
    dividend_metrics = calculate_dividend_metrics(holdings, price_data_map)
    for symbol, metrics in dividend_metrics.items():
        dividend_info = get_dividend_months(symbol)
        metrics['payout_months'] = dividend_info.get("months", [])
        # 🛠️ 배당금 상세 정보에 프로필 데이터(로고, 이름) 추가
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
