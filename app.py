# 📄 app.py
import os
import sys
import logging
from datetime import datetime
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

# 🛠️ Refactor: extensions.py에서 Flask 확장 객체를 가져옵니다.
from extensions import db, login_manager, task_queue, redis_conn

# 파이썬의 모듈 검색 경로에 현재 프로젝트의 루트 디렉토리를 추가합니다.
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

logging.basicConfig(level=logging.INFO)

def create_app():
    """Flask 애플리케이션 팩토리 함수"""
    app = Flask(__name__)
    app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-for-local-testing")
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///investment.db")
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_recycle": 280, "pool_pre_ping": True}
    app.config["TAX_RATE"] = 0.154

    # 🛠️ Refactor: extensions.py의 객체들을 앱에 초기화하고 등록합니다.
    db.init_app(app)
    login_manager.init_app(app)
    
    # app 객체에 task_queue와 redis_conn을 할당하여 다른 곳에서 current_app을 통해 접근 가능하도록 합니다.
    app.task_queue = task_queue
    app.redis_conn = redis_conn

    # 템플릿 필터 등록
    register_template_filters(app)

    with app.app_context():
        # Blueprint 등록
        from routes import register_blueprints
        register_blueprints(app)

        # 데이터베이스 생성 및 초기 데이터 로드
        import models # 모델이 db 객체를 사용하므로 init_app 이후에 import
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

# 🛠️ Refactor: models를 import하기 전에 login_manager가 초기화되어 있어야 합니다.
from models import User
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Gunicorn과 같은 프로덕션 서버가 'app' 객체를 찾을 수 있도록 전역 스코프에 생성
app = create_app()

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)), debug=True)
