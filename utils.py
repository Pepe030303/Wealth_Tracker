# 📄 utils.py
from datetime import datetime, timedelta
import logging
import json
from redis import Redis
import os

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
            # 🛠️ 버그 수정: 파일이 비어있는 경우를 대비하여 파일 크기 확인
            if os.path.getsize(override_file) > 0:
                with open(override_file, 'r') as f:
                    MANUAL_OVERRIDES = json.load(f)
                logger.info(f"수동 재정의 데이터({override_file}) 로드 완료: {list(MANUAL_OVERRIDES.keys())}")
            else:
                logger.info(f"수동 재정의 파일({override_file})이 비어있어 로드를 건너뜁니다.")
        except json.JSONDecodeError as e:
            logger.error(f"수동 재정의 파일({override_file}) JSON 파싱 오류: {e}")
        except Exception as e:
            logger.error(f"수동 재정의 파일 로드 중 예상치 못한 오류 발생: {e}")

def get_from_redis_cache(key):
    if not redis_conn: return None
    cached = redis_conn.get(key)
    return json.loads(cached) if cached else None

def set_to_redis_cache(key, value, ttl_hours=6):
    if not redis_conn: return
    redis_conn.setex(key, timedelta(hours=ttl_hours), json.dumps(value))

# 🛠️ Refactor: 비즈니스 로직을 services/portfolio_service.py로 이전함
