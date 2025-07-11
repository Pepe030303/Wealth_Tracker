# tasks.py

import yfinance as yf
from app import db, app
from models import Holding, Dividend
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def update_all_dividends_for_user(user_id):
    """
    백그라운드에서 실행될 실제 배당금 업데이트 작업.
    app_context 안에서 실행해야 DB에 접근 가능합니다.
    """
    with app.app_context():
        try:
            # 최근 6시간 이내에 이미 업데이트를 시도했는지 확인
            # (사용자가 페이지를 너무 자주 새로고침하는 것을 방지)
            # 이를 위해서는 DividendUpdateCache 모델이 필요합니다.
            # 지금은 단순화를 위해 이 로직을 일단 주석 처리합니다.
            
            # last_update = DividendUpdateCache.query.filter_by(user_id=user_id).first()
            # if last_update and (datetime.utcnow() - last_update.last_updated) < timedelta(hours=6):
            #     logger.info(f"User {user_id}: 6시간 이내에 이미 업데이트됨. 건너뜁니다.")
            #     return

            logger.info(f"User {user_id}: 전체 보유 종목 배당금 업데이트 시작.")
            holdings = Holding.query.filter_by(user_id=user_id).all()
            if not holdings:
                logger.info(f"User {user_id}: 업데이트할 보유 종목 없음.")
                return

            total_new_dividends = 0
            for holding in holdings:
                try:
                    ticker = yf.Ticker(holding.symbol)
                    # yfinance에서 배당금 정보 가져오기
                    hist_dividends = ticker.dividends
                    if hist_dividends.empty: continue

                    new_dividend_count = 0
                    for pay_date, amount_per_share in hist_dividends.items():
                        pay_date_obj = pay_date.date()
                        # 종목 구매일 이후의 배당금만 추가
                        if holding.purchase_date and pay_date_obj > holding.purchase_date.date():
                            exists = Dividend.query.filter_by(symbol=holding.symbol, dividend_date=pay_date_obj, user_id=user_id).first()
                            if not exists:
                                new_dividend = Dividend(
                                    symbol=holding.symbol,
                                    amount=amount_per_share * holding.quantity,
                                    amount_per_share=amount_per_share,
                                    dividend_date=pay_date_obj,
                                    user_id=user_id
                                )
                                db.session.add(new_dividend)
                                new_dividend_count += 1
                    
                    if new_dividend_count > 0:
                        total_new_dividends += new_dividend_count
                        # 각 종목별로 커밋하여 부분 성공 보장
                        db.session.commit()
                        logger.info(f"User {user_id}, Symbol {holding.symbol}: {new_dividend_count}개 배당금 추가.")
                except Exception as e:
                    logger.error(f"User {user_id}, Symbol {holding.symbol} 처리 중 오류: {e}")
                    db.session.rollback()
            
            # 업데이트 시점 기록 (캐싱 로직)
            # if not last_update:
            #     last_update = DividendUpdateCache(user_id=user_id)
            #     db.session.add(last_update)
            # else:
            #     last_update.last_updated = datetime.utcnow()
            # db.session.commit()

            if total_new_dividends > 0:
                logger.info(f"User {user_id}: 총 {total_new_dividends}개의 새로운 배당금 추가 완료.")
            else:
                logger.info(f"User {user_id}: 업데이트할 새로운 배당금이 없습니다.")
        except Exception as e:
            logger.error(f"User {user_id}의 전체 배당금 업데이트 작업 실패: {e}")
            db.session.rollback()
