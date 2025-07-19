# 📄 extensions.py
# ✨ New File: 순환 참조 방지를 위한 Flask 확장(extensions) 중앙 관리 파일

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from flask_login import LoginManager
import redis
from rq import Queue
import os
import logging

# 데이터베이스 기본 클래스
class Base(DeclarativeBase):
    pass

# SQLAlchemy 인스턴스
db = SQLAlchemy(model_class=Base)

# Flask-Login 인스턴스
login_manager = LoginManager()

# Redis 연결 및 RQ(Task Queue) 인스턴스
redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
try:
    redis_conn = redis.from_url(redis_url)
    task_queue = Queue('wealth-tracker-tasks', connection=redis_conn)
except Exception as e:
    logging.error(f"Redis 연결 실패: {e}")
    redis_conn = None
    task_queue = None

# 로그인 뷰 및 메시지 설정
login_manager.login_view = 'auth.login'
login_manager.login_message = "로그인이 필요한 페이지입니다."
login_manager.login_message_category = "info"
