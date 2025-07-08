from datetime import datetime
from sqlalchemy import func
from app import db

class Trade(db.Model):
    """거래 기록"""
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False)  # 종목 심볼
    trade_type = db.Column(db.String(10), nullable=False)  # 'buy' 또는 'sell'
    quantity = db.Column(db.Integer, nullable=False)  # 거래 수량
    price = db.Column(db.Float, nullable=False)  # 거래 가격
    trade_date = db.Column(db.Date, nullable=False)  # 거래 일자
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Trade {self.symbol}: {self.trade_type} {self.quantity} @ ${self.price}>'

class Holding(db.Model):
    """보유 종목 정보"""
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False)  # 종목 심볼 (예: AAPL, TSLA)
    quantity = db.Column(db.Float, nullable=False)  # 보유 수량
    purchase_price = db.Column(db.Float, nullable=False)  # 구매 단가
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Holding {self.symbol}: {self.quantity} shares at ${self.purchase_price}>'

class Dividend(db.Model):
    """배당금 기록"""
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False)  # 종목 심볼
    amount = db.Column(db.Float, nullable=False)  # 총 배당금액 (기존 호환성)
    amount_per_share = db.Column(db.Float, nullable=True)  # 주당 배당금
    dividend_date = db.Column(db.Date, nullable=False)  # 배당금 수령일
    ex_dividend_date = db.Column(db.Date, nullable=True)  # 배당락일
    payout_frequency = db.Column(db.Integer, default=4)  # 연간 배당 횟수 (분기별=4)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Dividend {self.symbol}: ${self.amount} on {self.dividend_date}>'
    
    def get_amount_per_share(self):
        """주당 배당금 반환 (amount_per_share가 있으면 사용, 없으면 amount 사용)"""
        return self.amount_per_share if self.amount_per_share is not None else self.amount

class StockPrice(db.Model):
    """주가 캐시"""
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False, unique=True)
    current_price = db.Column(db.Float, nullable=False)
    change = db.Column(db.Float, default=0.0)
    change_percent = db.Column(db.Float, default=0.0)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<StockPrice {self.symbol}: ${self.current_price}>'

def calculate_holdings_from_trades():
    """거래 기록으로부터 현재 보유 종목 계산"""
    # 기존 보유 종목 데이터 삭제
    Holding.query.delete()
    
    # 심볼별 거래 집계
    trades_by_symbol = db.session.query(Trade.symbol).distinct().all()
    
    for (symbol,) in trades_by_symbol:
        # 해당 심볼의 모든 거래 조회
        trades = Trade.query.filter_by(symbol=symbol).order_by(Trade.trade_date).all()
        
        total_quantity = 0
        total_cost = 0
        
        for trade in trades:
            if trade.trade_type == 'buy':
                total_quantity += trade.quantity
                total_cost += trade.quantity * trade.price
            elif trade.trade_type == 'sell':
                total_quantity -= trade.quantity
                # 매도 시 비용 차감 (FIFO 방식으로 처리)
                total_cost -= trade.quantity * trade.price
        
        # 현재 보유 수량이 0보다 클 때만 보유 종목으로 추가
        if total_quantity > 0:
            avg_price = total_cost / total_quantity
            
            # 가장 최근 거래 날짜를 구매 날짜로 설정
            latest_trade = trades[-1]
            
            holding = Holding(
                symbol=symbol,
                quantity=total_quantity,
                purchase_price=avg_price,
                purchase_date=latest_trade.trade_date
            )
            db.session.add(holding)
    
    db.session.commit()

def recalculate_holdings():
    """보유 종목 재계산 (더 정확한 FIFO 방식)"""
    # 기존 보유 종목 데이터 삭제
    Holding.query.delete()
    
    # 심볼별 처리
    symbols = db.session.query(Trade.symbol).distinct().all()
    
    for (symbol,) in symbols:
        # 해당 심볼의 모든 거래를 날짜순으로 조회
        trades = Trade.query.filter_by(symbol=symbol).order_by(Trade.trade_date, Trade.id).all()
        
        # FIFO 큐로 매수 기록 관리
        buy_queue = []
        total_quantity = 0
        total_cost = 0
        
        for trade in trades:
            if trade.trade_type == 'buy':
                buy_queue.append({
                    'quantity': trade.quantity,
                    'price': trade.price,
                    'date': trade.trade_date
                })
                total_quantity += trade.quantity
                total_cost += trade.quantity * trade.price
                
            elif trade.trade_type == 'sell':
                sell_quantity = trade.quantity
                
                # FIFO 방식으로 매도 처리
                while sell_quantity > 0 and buy_queue:
                    buy_record = buy_queue[0]
                    
                    if buy_record['quantity'] <= sell_quantity:
                        # 해당 매수 기록 전체 매도
                        sold_qty = buy_record['quantity']
                        total_quantity -= sold_qty
                        total_cost -= sold_qty * buy_record['price']
                        sell_quantity -= sold_qty
                        buy_queue.pop(0)
                    else:
                        # 해당 매수 기록 일부 매도
                        buy_record['quantity'] -= sell_quantity
                        total_quantity -= sell_quantity
                        total_cost -= sell_quantity * buy_record['price']
                        sell_quantity = 0
        
        # 현재 보유 수량이 0보다 클 때만 보유 종목으로 추가
        if total_quantity > 0 and total_cost > 0:
            avg_price = total_cost / total_quantity
            
            # 가장 최근 매수 날짜를 구매 날짜로 설정
            latest_buy_date = max([buy['date'] for buy in buy_queue]) if buy_queue else trades[-1].trade_date
            
            holding = Holding(
                symbol=symbol,
                quantity=total_quantity,
                purchase_price=avg_price,
                purchase_date=latest_buy_date
            )
            db.session.add(holding)
    
    db.session.commit()

def calculate_dividend_metrics():
    """배당 관련 지표 계산"""
    holdings = Holding.query.all()
    dividend_metrics = {}
    
    for holding in holdings:
        # 해당 종목의 최근 배당 기록 조회
        recent_dividend = Dividend.query.filter_by(symbol=holding.symbol).order_by(
            Dividend.dividend_date.desc()
        ).first()
        
        if recent_dividend:
            amount_per_share = recent_dividend.get_amount_per_share()
            
            # 예상 연간 배당금 계산
            expected_annual_dividend = amount_per_share * holding.quantity * recent_dividend.payout_frequency
            
            # 현재 시가총액 계산을 위해 stock_api 사용 필요
            from stock_api import stock_api
            price_data = stock_api.get_stock_price(holding.symbol)
            
            if price_data:
                current_market_value = price_data['price'] * holding.quantity
                dividend_yield = (expected_annual_dividend / current_market_value) * 100 if current_market_value > 0 else 0
            else:
                current_market_value = 0
                dividend_yield = 0
            
            dividend_metrics[holding.symbol] = {
                'holding_quantity': holding.quantity,
                'amount_per_share': amount_per_share,
                'payout_frequency': recent_dividend.payout_frequency,
                'expected_annual_dividend': expected_annual_dividend,
                'current_market_value': current_market_value,
                'dividend_yield': dividend_yield
            }
    
    return dividend_metrics

def get_dividend_allocation_data():
    """배당 배분 차트용 데이터"""
    dividend_metrics = calculate_dividend_metrics()
    allocation_data = []
    
    for symbol, metrics in dividend_metrics.items():
        if metrics['expected_annual_dividend'] > 0:
            allocation_data.append({
                'symbol': symbol,
                'expected_annual_dividend': metrics['expected_annual_dividend']
            })
    
    return allocation_data

# Stock to Company Domain Mapping for Logo API
STOCK_COMPANY_MAPPING = {
    'AAPL': {'domain': 'apple.com', 'name': 'Apple Inc.'},
    'MSFT': {'domain': 'microsoft.com', 'name': 'Microsoft Corporation'},
    'GOOGL': {'domain': 'google.com', 'name': 'Alphabet Inc.'},
    'GOOG': {'domain': 'google.com', 'name': 'Alphabet Inc.'},
    'AMZN': {'domain': 'amazon.com', 'name': 'Amazon.com Inc.'},
    'TSLA': {'domain': 'tesla.com', 'name': 'Tesla Inc.'},
    'META': {'domain': 'meta.com', 'name': 'Meta Platforms Inc.'},
    'NVDA': {'domain': 'nvidia.com', 'name': 'NVIDIA Corporation'},
    'NFLX': {'domain': 'netflix.com', 'name': 'Netflix Inc.'},
    'V': {'domain': 'visa.com', 'name': 'Visa Inc.'},
    'JPM': {'domain': 'jpmorganchase.com', 'name': 'JPMorgan Chase & Co.'},
    'JNJ': {'domain': 'jnj.com', 'name': 'Johnson & Johnson'},
    'WMT': {'domain': 'walmart.com', 'name': 'Walmart Inc.'},
    'PG': {'domain': 'pg.com', 'name': 'Procter & Gamble'},
    'UNH': {'domain': 'unitedhealthgroup.com', 'name': 'UnitedHealth Group'},
    'HD': {'domain': 'homedepot.com', 'name': 'The Home Depot'},
    'BAC': {'domain': 'bankofamerica.com', 'name': 'Bank of America'},
    'MA': {'domain': 'mastercard.com', 'name': 'Mastercard Inc.'},
    'DIS': {'domain': 'disney.com', 'name': 'The Walt Disney Company'},
    'ADBE': {'domain': 'adobe.com', 'name': 'Adobe Inc.'},
    'CRM': {'domain': 'salesforce.com', 'name': 'Salesforce Inc.'},
    'XOM': {'domain': 'exxonmobil.com', 'name': 'Exxon Mobil Corporation'},
    'CVX': {'domain': 'chevron.com', 'name': 'Chevron Corporation'},
    'KO': {'domain': 'coca-cola.com', 'name': 'The Coca-Cola Company'},
    'PEP': {'domain': 'pepsico.com', 'name': 'PepsiCo Inc.'},
    'T': {'domain': 'att.com', 'name': 'AT&T Inc.'},
    'VZ': {'domain': 'verizon.com', 'name': 'Verizon Communications'},
    'INTC': {'domain': 'intel.com', 'name': 'Intel Corporation'},
    'IBM': {'domain': 'ibm.com', 'name': 'International Business Machines'},
    'ORCL': {'domain': 'oracle.com', 'name': 'Oracle Corporation'},
    'CZR': {'domain': 'caesars.com', 'name': 'Caesars Entertainment'},
}

# Dividend Payment Months for Major Stocks
DIVIDEND_MONTHS = {
    'AAPL': ['Feb', 'May', 'Aug', 'Nov'],  # Apple - Quarterly
    'MSFT': ['Mar', 'Jun', 'Sep', 'Dec'],  # Microsoft - Quarterly
    'GOOGL': [],  # Alphabet - No dividends
    'GOOG': [],   # Alphabet - No dividends
    'AMZN': [],   # Amazon - No dividends
    'TSLA': [],   # Tesla - No dividends
    'META': [],   # Meta - No dividends
    'NVDA': ['Mar', 'Jun', 'Sep', 'Dec'],  # NVIDIA - Quarterly
    'NFLX': [],   # Netflix - No dividends
    'V': ['Mar', 'Jun', 'Sep', 'Dec'],     # Visa - Quarterly
    'JPM': ['Jan', 'Apr', 'Jul', 'Oct'],   # JPMorgan - Quarterly
    'JNJ': ['Mar', 'Jun', 'Sep', 'Dec'],   # Johnson & Johnson - Quarterly
    'WMT': ['Jan', 'Apr', 'Jul', 'Oct'],   # Walmart - Quarterly
    'PG': ['Feb', 'May', 'Aug', 'Nov'],    # Procter & Gamble - Quarterly
    'UNH': ['Mar', 'Jun', 'Sep', 'Dec'],   # UnitedHealth - Quarterly
    'HD': ['Mar', 'Jun', 'Sep', 'Dec'],    # Home Depot - Quarterly
    'BAC': ['Mar', 'Jun', 'Sep', 'Dec'],   # Bank of America - Quarterly
    'MA': ['Feb', 'May', 'Aug', 'Nov'],    # Mastercard - Quarterly
    'DIS': ['Jan', 'Jul'],                 # Disney - Semi-annual
    'ADBE': ['Mar', 'Jun', 'Sep', 'Dec'],  # Adobe - Quarterly
    'CRM': [],    # Salesforce - No dividends
    'XOM': ['Mar', 'Jun', 'Sep', 'Dec'],   # ExxonMobil - Quarterly
    'CVX': ['Mar', 'Jun', 'Sep', 'Dec'],   # Chevron - Quarterly
    'KO': ['Apr', 'Jul', 'Oct', 'Dec'],    # Coca-Cola - Quarterly
    'PEP': ['Jan', 'Apr', 'Jun', 'Oct'],   # PepsiCo - Quarterly
    'T': ['Feb', 'May', 'Aug', 'Nov'],     # AT&T - Quarterly
    'VZ': ['Feb', 'May', 'Aug', 'Nov'],    # Verizon - Quarterly
    'INTC': ['Mar', 'Jun', 'Sep', 'Dec'],  # Intel - Quarterly
    'IBM': ['Mar', 'Jun', 'Sep', 'Dec'],   # IBM - Quarterly
    'ORCL': ['Jan', 'Apr', 'Jul', 'Oct'],  # Oracle - Quarterly
}

def get_stock_logo_url(symbol):
    """Get stock logo URL from Clearbit API or return None for fallback"""
    if symbol in STOCK_COMPANY_MAPPING:
        domain = STOCK_COMPANY_MAPPING[symbol]['domain']
        return f"https://logo.clearbit.com/{domain}"
    return None

def get_company_name(symbol):
    """Get company name for a stock symbol"""
    if symbol in STOCK_COMPANY_MAPPING:
        return STOCK_COMPANY_MAPPING[symbol]['name']
    return symbol

def get_dividend_months(symbol):
    """Get dividend payment months for a stock symbol"""
    return DIVIDEND_MONTHS.get(symbol, [])
