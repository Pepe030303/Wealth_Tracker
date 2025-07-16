# 📄 tasks.py

import yfinance as yf
import pandas as pd
from app import db, app
from models import Holding, Dividend, DividendUpdateCache, Trade
import logging
from datetime import datetime, timedelta
import requests

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
    [배당락일 로직 개선]
    사용자의 전체 보유 종목에 대해, '배당락일' 기준 보유 수량을 계산하여
    실제 받을 배당금을 'Dividend' 테이블에 기록하는 백그라운드 작업.
    """
    with app.app_context():
        try:
            last_update_record = DividendUpdateCache.query.filter_by(user_id=user_id).first()
            if last_update_record and (datetime.utcnow() - last_update_record.last_updated) < timedelta(hours=6):
                logger.info(f"User {user_id}: 6시간 이내에 이미 배당금 업데이트를 시도했습니다. 건너뜁니다.")
                return

            logger.info(f"User {user_id}: 배당금 내역 업데이트 시작 (배당락일 기준).")
            symbols_traded = db.session.query(Trade.symbol).filter_by(user_id=user_id).distinct().all()
            if not symbols_traded:
                logger.info(f"User {user_id}: 거래 기록이 없어 배당금 업데이트를 종료합니다.")
                return

            total_new_dividends = 0
            for (symbol,) in symbols_traded:
                try:
                    ticker = yf.Ticker(symbol)
                    # 🛠️ Changed: actions 대신 dividends 속성을 직접 사용하여 더 안정적인 데이터 조회
                    dividends_df = ticker.dividends
                    if dividends_df is None or dividends_df.empty:
                        continue
                    
                    # yfinance가 반환하는 dividends 시리즈를 데이터프레임처럼 처리
                    dividends_data = dividends_df.reset_index()
                    dividends_data.columns = ['Ex-Dividend-Date', 'Dividends']
                    
                    for _, row in dividends_data.iterrows():
                        amount_per_share = row['Dividends']
                        if amount_per_share <= 0: continue
                        
                        ex_dividend_date = row['Ex-Dividend-Date']
                        # Pandas Timestamp를 Python datetime.date 객체로 변환
                        ex_date_native = ex_dividend_date.to_pydatetime().date()
                        
                        quantity_on_ex_date = get_quantity_on_date(user_id, symbol, ex_date_native)
                        if quantity_on_ex_date <= 0: continue

                        exists = Dividend.query.filter_by(
                            user_id=user_id, 
                            symbol=symbol, 
                            ex_dividend_date=ex_date_native
                        ).first()

                        if not exists:
                            total_amount = float(amount_per_share) * quantity_on_ex_date
                            # dividend_date는 실제 지급일이지만, yfinance에서 정확한 pay date를 제공하지 않으므로
                            # ex_dividend_date를 임시로 사용. Polygon.io 등 유료 API 사용 시 개선 가능.
                            new_dividend = Dividend(
                                symbol=symbol,
                                amount=total_amount,
                                amount_per_share=float(amount_per_share),
                                dividend_date=ex_date_native, 
                                ex_dividend_date=ex_date_native,
                                user_id=user_id
                            )
                            db.session.add(new_dividend)
                            total_new_dividends += 1
                
                # 🛠️ Changed: 오류 로깅 시 어떤 종목에서 문제 발생했는지 명확히 기록
                except requests.exceptions.HTTPError as http_err:
                    logger.warning(f"배당 정보 조회 실패 (HTTP 오류) (User: {user_id}, Symbol: {symbol}): {http_err}")
                except (AttributeError, KeyError, IndexError, TypeError) as e:
                    logger.warning(f"배당 정보 파싱 오류 (User: {user_id}, Symbol: {symbol}): {e}")
                except Exception as e:
                    logger.error(f"배당 처리 중 예상치 못한 오류 (User: {user_id}, Symbol: {symbol}): {e}")
                    # 개별 종목 오류 시 롤백하지 않고 다음 종목으로 넘어가기 위해 continue 처리
                    continue
            
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
