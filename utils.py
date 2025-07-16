# 📄 utils.py
from datetime import datetime, timedelta
import logging
import json
from redis import Redis
import os

# 🛠️ Refactoring: yfinance, pandas 등 특정 비즈니스 로직에만 필요했던 임포트 제거
try:
    from app import conn as redis_conn
except ImportError:
    redis_conn = None
    logging.warning("Redis 연결을 가져오지 못했습니다. 캐싱이 비활성화됩니다.")

logger = logging.getLogger(__name__)

MANUAL_OVERRIDES = {}

def load_manual_overrides():
    global MANUAL_OVERRIDES
    override_file = 'manual_overrides.json'
    if os.path.exists(override_file):
        try:
            with open(override_file, 'r') as f:
                MANUAL_OVERRIDES = json.load(f)
            logger.info(f"수동 재정의 데이터({override_file}) 로드 완료: {list(MANUAL_OVERRIDES.keys())}")
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"수동 재정의 파일 로드 중 오류 발생: {e}")

def get_from_redis_cache(key):
    if not redis_conn: return None
    cached = redis_conn.get(key)
    return json.loads(cached) if cached else None

def set_to_redis_cache(key, value, ttl_hours=6):
    if not redis_conn: return
    redis_conn.setex(key, timedelta(hours=ttl_hours), json.dumps(value))

# 🛠️ Refactoring: 아래의 비즈니스 로직 함수들은 모두 services/stock_data_service.py 로 이동되었습니다.
# - calculate_dividend_metrics
# - get_adjusted_dividend_history
# - calculate_5yr_avg_dividend_growth
# - get_dividend_payout_schedule

def get_dividend_allocation_data(dividend_metrics):
    """
    배당 지표 데이터를 받아 차트 표시에 적합한 형태로 변환하는 유틸리티 함수.
    (템플릿에서 직접 호출되므로 utils에 유지)
    """
    return [{'symbol': item[0], 'value': item[1]['expected_annual_dividend']} for item in dividend_metrics if item[1].get('expected_annual_dividend', 0) > 0]
