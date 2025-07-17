# 📄 tests/test_portfolio_service.py
# 🛠️ New File: 포트폴리오 서비스 로직에 대한 단위 테스트

import pytest
from datetime import date
from models import User, Trade, Holding
from services.portfolio_service import recalculate_holdings

def test_recalculate_holdings_simple_buy(init_database):
    """단순 매수 시 보유 종목이 정확히 계산되는지 테스트합니다."""
    db = init_database
    user = User.query.first()
    
    # Given: 1개의 매수 거래
    trade1 = Trade(symbol='AAPL', trade_type='buy', quantity=10, price=150, trade_date=date(2023, 1, 1), user_id=user.id)
    db.session.add(trade1)
    db.session.commit()
    
    # When: 보유 종목 재계산
    recalculate_holdings(user.id)
    
    # Then: 결과 검증
    holding = Holding.query.filter_by(user_id=user.id, symbol='AAPL').first()
    assert holding is not None
    assert holding.quantity == 10
    assert holding.purchase_price == 150

def test_recalculate_holdings_multiple_buys(init_database):
    """여러 번 매수 시 평균 단가가 정확히 계산되는지 테스트합니다."""
    db = init_database
    user = User.query.first()

    # Given: 2개의 매수 거래
    db.session.add_all([
        Trade(symbol='GOOG', trade_type='buy', quantity=5, price=100, trade_date=date(2023, 1, 1), user_id=user.id),
        Trade(symbol='GOOG', trade_type='buy', quantity=5, price=110, trade_date=date(2023, 2, 1), user_id=user.id)
    ])
    db.session.commit()
    
    # When: 보유 종목 재계산
    recalculate_holdings(user.id)
    
    # Then: 결과 검증
    holding = Holding.query.filter_by(user_id=user.id, symbol='GOOG').first()
    assert holding is not None
    assert holding.quantity == 10
    assert holding.purchase_price == pytest.approx(105) # (5*100 + 5*110) / 10 = 105

def test_recalculate_holdings_fifo_sell(init_database):
    """FIFO(선입선출) 방식에 따라 매도 후 평단가가 정확히 계산되는지 테스트합니다."""
    db = init_database
    user = User.query.first()

    # Given: 3개의 매수 거래 후 1개의 매도 거래
    db.session.add_all([
        Trade(symbol='MSFT', trade_type='buy', quantity=10, price=200, trade_date=date(2023, 1, 1), user_id=user.id), # 먼저 매도될 거래
        Trade(symbol='MSFT', trade_type='buy', quantity=10, price=250, trade_date=date(2023, 2, 1), user_id=user.id), # 남을 거래
        Trade(symbol='MSFT', trade_type='buy', quantity=10, price=300, trade_date=date(2023, 3, 1), user_id=user.id), # 남을 거래
        Trade(symbol='MSFT', trade_type='sell', quantity=15, price=350, trade_date=date(2023, 4, 1), user_id=user.id) # 10주(200원) + 5주(250원) 매도
    ])
    db.session.commit()
    
    # When: 보유 종목 재계산
    recalculate_holdings(user.id)
    
    # Then: 결과 검증 (남은 수량: 15주, 남은 평단가: (5*250 + 10*300) / 15 = 283.33)
    holding = Holding.query.filter_by(user_id=user.id, symbol='MSFT').first()
    assert holding is not None
    assert holding.quantity == 15 
    assert holding.purchase_price == pytest.approx((5 * 250 + 10 * 300) / 15)

def test_recalculate_holdings_sell_all(init_database):
    """전량 매도 시 보유 종목이 없는 것으로 계산되는지 테스트합니다."""
    db = init_database
    user = User.query.first()

    # Given: 매수 후 전량 매도
    db.session.add_all([
        Trade(symbol='TSLA', trade_type='buy', quantity=10, price=200, trade_date=date(2023, 1, 1), user_id=user.id),
        Trade(symbol='TSLA', trade_type='sell', quantity=10, price=250, trade_date=date(2023, 2, 1), user_id=user.id)
    ])
    db.session.commit()
    
    # When: 보유 종목 재계산
    recalculate_holdings(user.id)
    
    # Then: 결과 검증
    holding = Holding.query.filter_by(user_id=user.id, symbol='TSLA').first()
    assert holding is None
