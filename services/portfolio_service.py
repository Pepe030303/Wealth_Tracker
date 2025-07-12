# 📄 services/portfolio_service.py

from stock_api import stock_api
from utils import calculate_dividend_metrics, get_monthly_dividend_distribution
from models import Holding

def get_portfolio_analysis_data(user_id):
    """
    사용자의 전체 포트폴리오 데이터를 분석하고 종합하는 중앙 서비스 함수.
    - 보유 종목, 현재가, 섹터, 배당 등 모든 정보를 계산하여 하나의 딕셔너리로 반환.
    - 코드 중복을 방지하고 비즈니스 로직을 한 곳에서 관리.
    """
    holdings = Holding.query.filter_by(user_id=user_id).all()
    if not holdings:
        return None

    symbols = {h.symbol for h in holdings}
    price_data_map = {s: stock_api.get_stock_price(s) for s in symbols}
    profile_data_map = {s: stock_api.get_stock_profile(s) for s in symbols}
    
    # 배당 지표 계산
    dividend_metrics = calculate_dividend_metrics(holdings, price_data_map)

    total_investment = sum(h.quantity * h.purchase_price for h in holdings)
    total_current_value = sum(h.quantity * (price_data_map.get(h.symbol, {}).get('price') or h.purchase_price) for h in holdings)
    
    # 섹터별 데이터 계산
    sector_details = {}
    for h in holdings:
        profile = profile_data_map.get(h.symbol, {}); 
        sector = profile.get('sector', 'N/A')
        current_value = h.quantity * (price_data_map.get(h.symbol, {}).get('price') or h.purchase_price)
        
        if sector not in sector_details:
            sector_details[sector] = {'total_value': 0, 'holdings': []}
            
        sector_details[sector]['total_value'] += current_value
        sector_details[sector]['holdings'].append({'symbol': h.symbol, 'value': current_value})

    sector_allocation = [
        {
            'sector': sector, 
            'value': details['total_value'],
            'holdings': sorted(details['holdings'], key=lambda x: x['value'], reverse=True)
        } 
        for sector, details in sector_details.items()
    ]
    
    total_profit_loss = total_current_value - total_investment
    
    summary_data = {
        'total_investment': total_investment, 
        'total_current_value': total_current_value,
        'total_profit_loss': total_profit_loss,
        'total_return_percent': (total_profit_loss / total_investment * 100) if total_investment > 0 else 0
    }
    
    # 월별 예상 배당금 계산
    monthly_dividend_data = get_monthly_dividend_distribution(dividend_metrics)
    
    return {
        "holdings": holdings,
        "summary": summary_data,
        "sector_allocation": sector_allocation,
        "dividend_metrics": dividend_metrics,
        "monthly_dividend_data": monthly_dividend_data,
    }
