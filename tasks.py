# tasks.py

import yfinance as yf
from app import db, app
from models import Holding, Dividend, DividendUpdateCache
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def update_all_dividends_for_user(user_id):
    with app.app_context():
        try:
            # 6시간 이내에 이미 업데이트를 시도했는지 확인
            last_update = DividendUpdateCache.query.filter_by(user_id=user_id).first()
            if last_update and (datetime.utcnow() - last_update.last_updated) < timedelta(hours=6):
                logger.info(f"User {user_id}: 6시간 이내에 이미 업데이트됨. 건너뜁니다.")
                return

            logger.info(f"User {user_id}: 전체 보유 종목 배당금 업데이트 시작.")
            holdings = Holding.query.filter_by(user_id=user_id).all()
            if not holdings: return

            total_new_dividends = 0
            for holding in holdings:
                try:
                    ticker = yf.Ticker(holding.symbol)
                    hist_dividends = ticker.dividends
                    if hist_dividends.empty: continue

                    new_dividend_count = 0
                    for pay_date, amount_per_share in hist_dividends.items():
                        pay_date_obj = pay_date.date()
                        if holding.purchase_date and pay_date_obj > holding.purchase_date.date():
                            exists = Dividend.query.filter_by(symbol=holding.symbol, dividend_date=pay_date_obj, user_id=user_id).first()
                            if not exists:
                                new_dividend = Dividend(
                                    symbol=holding.symbol, amount=float(amount_per_share) * holding.quantity,
                                    amount_per_share=float(amount_per_share), dividend_date=pay_date_obj, user_id=user_id
                                )
                                db.session.add(new_dividend)
                                new_dividend_count += 1
                    if new_dividend_count > 0:
                        total_new_dividends += new_dividend_count
                        db.session.commit()
                except Exception as e:
                    logger.error(f"User {user_id}, Symbol {holding.symbol} 처리 중 오류: {e}")
                    db.session.rollback()
            
            # 업데이트 시점 기록
            if not last_update:
                last_update = DividendUpdateCache(user_id=user_id)
                db.session.add(last_update)
            else:
                last_update.last_updated = datetime.utcnow()
            db.session.commit()
            logger.info(f"User {user_id}: 배당금 업데이트 작업 완료. 추가된 배당금: {total_new_dividends}개.")
        except Exception as e:
            logger.error(f"User {user_id}의 전체 배당금 업데이트 작업 실패: {e}")
            db.session.rollback()
