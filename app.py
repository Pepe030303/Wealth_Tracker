# 📄 app.py
import os
import sys # 🛠️ Fix: sys 모듈 임포트
import logging
from datetime import datetime
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_login import LoginManager
import redis
from rq import Queue

# 🛠️ Fix: 파이썬의 모듈 검색 경로에 현재 프로젝트의 루트 디렉토리를 추가합니다.
# 이 코드는 순환 참조 및 ImportError를 방지하는 가장 확실한 방법입니다.
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

logging.basicConfig(level=logging.INFO)

class Base(DeclarativeBase): pass
db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()
task_queue = None

def create_app():
    """Flask 애플리케이션 팩토리 함수"""
    app = Flask(__name__)
    app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-for-local-testing")
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///investment.db")
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_recycle": 280, "pool_pre_ping": True}
    app.config["TAX_RATE"] = 0.154

    # 데이터베이스 및 로그인 매니저 초기화
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = "로그인이 필요한 페이지입니다."
    login_manager.login_message_category = "info"

    # Redis 및 RQ 초기화
    global task_queue
    try:
        redis_url = os.environ.get('REDIS_URL')
        if not redis_url:
            raise ValueError("REDIS_URL 환경 변수가 설정되지 않았습니다.")
        conn = redis.from_url(redis_url)
        task_queue = Queue('wealth-tracker-tasks', connection=conn)
    except Exception as e:
        app.logger.error(f"Redis 연결 실패: {e}")
        task_queue = None
    
    # app 객체에 task_queue 할당
    app.task_queue = task_queue

    # 템플릿 필터 등록
    register_template_filters(app)

    with app.app_context():
        # 모든 객체가 초기화된 후, 마지막에 Blueprint를 임포트하고 등록합니다.
        from routes import register_blueprints
        register_blueprints(app)

        # 애플리케이션 컨텍스트 내에서 초기 데이터 로드
        import models
        db.create_all()
        from stock_api import load_us_stocks_data
        load_us_stocks_data()
        from utils import load_manual_overrides
        load_manual_overrides()

    return app

def register_template_filters(app):
    @app.template_filter('strftime')
    def strftime_filter(dt, fmt='%Y-%m-%d'):
        if isinstance(dt, str): return datetime.now().strftime(fmt) if dt == 'now' else dt
        if dt is None: return ""
        return dt.strftime(fmt)

    @app.template_filter('korean_dividend_months')
    def korean_dividend_months_filter(month_names):
        if not isinstance(month_names, list):
            return []
        month_map = {'Jan':'1월','Feb':'2월','Mar':'3월','Apr':'4월','May':'5월','Jun':'6월','Jul':'7월','Aug':'8월','Sep':'9월','Oct':'10월','Nov':'11월','Dec':'12월'}
        return [month_map.get(m, m) for m in month_names]

from models import User
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Gunicorn과 같은 프로덕션 서버가 'app' 객체를 찾을 수 있도록 전역 스코프에 생성
app = create_app()

if __name__ == '__main__':
    # 로컬에서 직접 실행할 때 (예: python app.py)
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)), debug=True)
