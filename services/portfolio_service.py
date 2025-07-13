# 📄 services/portfolio_service.py

from stock_api import stock_api
# 🛠️ 버그 수정: NameError 해결을 위해 defaultdict를 collections 모듈에서 import 합니다.
from collections import defaultdict
from utils import calculate_dividend_metrics, get_projected_dividend_schedule
from app import db
from models import Holding, Dividend
from datetime import datetime
from sqlalchemy import func, extract

def get_unified_monthly_dividends(user_id, all_holdings):
    """
    [로직 변경] DB의 실제 지급 완료 데이터와 API의 예측/확정 데이터를 통합하여
    현재 연도의 통일된 월별 배당금 데이터를 생성합니다.
    """
    current_year = datetime.now().year
    
    monthly_totals = [0] * 12
    detailed_data = {i: [] for i in range(12)}

    # 1. (1순위) DB에서 실제 지급 완료된 배당금 집계
    paid_dividends = Dividend.query.filter(
        Dividend.user_id == user_id,
        extract('year', Dividend.dividend_date) == current_year
    ).all()

    paid_months_map = defaultdict(list)
    for div in paid_dividends:
        month_index = div.dividend_date.month - 1
        monthly_totals[month_index] += div.amount
        
        detail = {
            'symbol': div.symbol, 'amount': div.amount,
            'dps_per_payout': div.amount_per_share,
            'ex_dividend_date': div.ex_dividend_date.strftime('%Y-%m-%d') if div.ex_dividend_date else None,
            'pay_date': div.dividend_date.strftime('%Y-%m-%d'),
            'status': '지급 완료', 'is_estimated': False
        }
        detailed_data[month_index].append(detail)
        paid_months_map[div.symbol].append(month_index)


    # 2. (2순위 & 3순위) API 기반 예측/확정 배당금 집계
    holdings_map = {h.symbol: h.quantity for h in all_holdings}
    profiles = stock_api.get_stock_profiles_bulk(list(holdings_map.keys()))

    for symbol, quantity in holdings_map.items():
        schedule_data = get_projected_dividend_schedule(symbol)
        payout_schedule = schedule_data.get('payouts', [])
        
        for payout in payout_schedule:
            pay_date = datetime.strptime(payout['pay_date'], '%Y-%m-%d')
            month_index = pay_date.month - 1

            # 이미 DB에 해당 종목의 해당 월 지급 기록이 있으면 건너뛰기
            if month_index in paid_months_map.get(symbol, []):
                continue
            
            amount = payout['amount'] * quantity
            monthly_totals[month_index] += amount
            
            status = '예정' if pay_date > datetime.now() else '지급 완료'

            detailed_data[month_index].append({
                'symbol': symbol, 'amount': amount,
                'dps_per_payout': payout['amount'],
                'ex_dividend_date': payout.get('ex_date'),
                'pay_date': payout['pay_date'],
                'status': status,
                'is_estimated': payout.get('is_estimated', False),
                'profile': profiles.get(symbol, {}),
                'quantity': quantity
            })
    
    # 지급 완료 데이터에도 프로필과 수량 정보 추가
    for month_items in detailed_data.values():
        for item in month_items:
            if 'profile' not in item:
                item['profile'] = profiles.get(item['symbol'], {})
                item['quantity'] = holdings_map.get(item['symbol'], 0)


    return {
        'labels': [f"{i+1}월" for i in range(12)],
        'datasets': [{'data': monthly_totals}], # 단순 막대 차트용
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
        schedule_data = get_projected_dividend_schedule(symbol)
        metrics['payout_months'] = schedule_data.get('months', [])
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
    
    monthly_dividend_data = get_unified_monthly_dividends(user_id, holdings)
    
    return {
        "holdings": holdings,
        "summary": summary_data,
        "sector_allocation": sector_allocation,
        "dividend_metrics": dividend_metrics,
        "monthly_dividend_data": monthly_dividend_data,
    }
