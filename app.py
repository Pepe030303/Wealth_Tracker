# 📄 app.py
import os
import logging
from datetime import datetime
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_login import LoginManager
import redis
from rq import Queue

logging.basicConfig(level=logging.INFO)

class Base(DeclarativeBase): pass
db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()

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
    login_manager.login_view = 'auth.login' # 🛠️ Refactor: Blueprint 엔드포인트로 변경
    login_manager.login_message = "로그인이 필요한 페이지입니다."
    login_manager.login_message_category = "info"

    # Redis 및 RQ 초기화
    try:
        redis_url = os.environ.get('REDIS_URL')
        if not redis_url:
            raise ValueError("REDIS_URL 환경 변수가 설정되지 않았습니다.")
        conn = redis.from_url(redis_url)
        app.task_queue = Queue('wealth-tracker-tasks', connection=conn)
    except Exception as e:
        app.logger.error(f"Redis 연결 실패: {e}")
        app.task_queue = None

    # 템플릿 필터 등록
    register_template_filters(app)

    # Blueprint 등록
    from routes import register_blueprints
    register_blueprints(app)

    with app.app_context():
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

app = create_app()

# task_queue를 전역에서 접근할 수 있도록 app 컨텍스트에서 설정
task_queue = app.task_queue

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
