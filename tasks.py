# 📄 tasks.py

import yfinance as yf
import pandas as pd
from app import db, app
from models import Holding, Dividend, DividendUpdateCache, Trade
# 🛠️ 변경: Finnhub API를 사용하기 위해 유틸리티 함수 임포트
from utils import get_dividend_payout_schedule
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def get_quantity_on_date(user_id, symbol, target_date):
    """
    특정 날짜(target_date) 기준으로 사용자가 해당 종목(symbol)을 몇 주 보유했는지 계산.
    - target_date 이전의 모든 거래 내역을 조회하여 계산.
    """
    trades = Trade.query.filter(
        Trade.user_id == user_id,
        Trade.symbol == symbol,
        Trade.trade_date < target_date
    ).order_by(Trade.trade_date).all()
    
    quantity = 0
    for trade in trades:
        if trade.trade_type == 'buy':
            quantity += trade.quantity
        elif trade.trade_type == 'sell':
            quantity -= trade.quantity
            
    return quantity if quantity > 0 else 0


def update_all_dividends_for_user(user_id):
    """
    [API 교체] yfinance 대신 Finnhub API를 사용하여 배당 내역을 업데이트합니다.
    '배당락일' 기준 보유 수량을 계산하여 실제 받을 배당금을 'Dividend' 테이블에 기록합니다.
    """
    with app.app_context():
        try:
            last_update_record = DividendUpdateCache.query.filter_by(user_id=user_id).first()
            if last_update_record and (datetime.utcnow() - last_update_record.last_updated) < timedelta(hours=6):
                logger.info(f"User {user_id}: 6시간 이내에 이미 배당금 업데이트를 시도했습니다. 건너뜁니다.")
                return

            logger.info(f"User {user_id}: 배당금 내역 업데이트 시작 (Finnhub API 사용).")
            symbols_traded = db.session.query(Trade.symbol).filter_by(user_id=user_id).distinct().all()
            if not symbols_traded:
                logger.info(f"User {user_id}: 거래 기록이 없어 배당금 업데이트를 종료합니다.")
                return

            total_new_dividends = 0
            for (symbol,) in symbols_traded:
                try:
                    # 🛠️ 변경: yfinance 대신 Finnhub 데이터 조회 함수 호출
                    dividend_data = get_dividend_payout_schedule(symbol)
                    payouts = dividend_data.get('payouts', [])
                    
                    if not payouts:
                        continue

                    for payout in payouts:
                        ex_date_str = payout.get('ex_date')
                        pay_date_str = payout.get('pay_date')
                        amount_per_share = payout.get('amount')
                        
                        if not all([ex_date_str, pay_date_str, amount_per_share]):
                            continue
                        
                        ex_date_native = datetime.strptime(ex_date_str, '%Y-%m-%d').date()
                        pay_date_native = datetime.strptime(pay_date_str, '%Y-%m-%d').date()

                        # 1. 이 배당락일 기준으로, 사용자가 이 배당을 받을 자격이 있는지 확인
                        quantity_on_ex_date = get_quantity_on_date(user_id, symbol, ex_date_native)
                        
                        if quantity_on_ex_date <= 0:
                            continue

                        # 2. 이미 DB에 동일한 배당락일의 기록이 있는지 확인 (중복 방지)
                        exists = Dividend.query.filter_by(
                            user_id=user_id, 
                            symbol=symbol, 
                            ex_dividend_date=ex_date_native
                        ).first()

                        if not exists:
                            # 3. 신규 배당 기록 추가 (정확한 지급일과 배당락일 모두 저장)
                            total_amount = float(amount_per_share) * quantity_on_ex_date
                            new_dividend = Dividend(
                                symbol=symbol,
                                amount=total_amount,
                                amount_per_share=float(amount_per_share),
                                dividend_date=pay_date_native, # 실제 지급일
                                ex_dividend_date=ex_date_native, # 실제 배당락일
                                user_id=user_id
                            )
                            db.session.add(new_dividend)
                            total_new_dividends += 1
                
                except Exception as e:
                    logger.error(f"User {user_id}, Symbol {symbol} 처리 중 오류: {e}")
                    db.session.rollback()
            
            if total_new_dividends > 0:
                db.session.commit()
                logger.info(f"User {user_id}: 신규 배당금 {total_new_dividends}건을 추가했습니다.")

            if not last_update_record:
                last_update_record = DividendUpdateCache(user_id=user_id)
                db.session.add(last_update_record)
            else:
                last_update_record.last_updated = datetime.utcnow()
            db.session.commit()
            
            logger.info(f"User {user_id}: 배당금 업데이트 작업 완료.")

        except Exception as e:
            logger.error(f"User {user_id}의 전체 배당금 업데이트 작업 실패: {e}")
            db.session.rollback()
