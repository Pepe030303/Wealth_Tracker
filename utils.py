# 📄 utils.py
from datetime import datetime, timedelta
import json
from redis import Redis
# 🛠️ 제거: os, logging 임포트 제거 (더 이상 사용되지 않음)

try:
    from app import conn as redis_conn
except ImportError:
    redis_conn = None
    # 🛠️ 수정: logging 라이브러리 대신 print 사용 또는 로깅 비활성화
    print("경고: Redis 연결을 가져오지 못했습니다. 캐싱이 비활성화됩니다.")

# 🛠️ 제거: 수동 재정의 관련 변수 및 함수 제거
# logger = logging.getLogger(__name__)
# MANUAL_OVERRIDES = {}
# def load_manual_overrides(): ...

def get_from_redis_cache(key):
    if not redis_conn: return None
    cached = redis_conn.get(key)
    return json.loads(cached) if cached else None

def set_to_redis_cache(key, value, ttl_hours=6):
    if not redis_conn: return
    redis_conn.setex(key, timedelta(hours=ttl_hours), json.dumps(value))

def get_dividend_allocation_data(dividend_metrics):
    return [{'symbol': item[0], 'value': item[1]['expected_annual_dividend']} for item in dividend_metrics if item[1].get('expected_annual_dividend', 0) > 0]
