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
from whitenoise import WhiteNoise # 🛠️ 추가: WhiteNoise 임포트

logging.basicConfig(level=logging.INFO)

class Base(DeclarativeBase): pass
db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()

# Flask 앱 생성 시 static, templates 폴더 경로 명시 (이전 수정사항 유지)
app = Flask(__name__,
            static_folder='static',
            template_folder='templates')

app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-for-local-testing")

# 🛠️ [핵심 수정] WhiteNoise 미들웨어를 적용하여 정적 파일 서빙 문제를 해결합니다.
# Gunicorn과 같은 프로덕션 WSGI 서버 환경에서 Flask 앱이 직접 static 파일들을
# 안정적으로 제공할 수 있도록 app.wsgi_app을 WhiteNoise로 감쌉니다.
# ProxyFix는 WhiteNoise 다음에 적용하는 것이 일반적입니다.
app.wsgi_app = WhiteNoise(app.wsgi_app, root='static/')
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)


app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///investment.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_recycle": 280, "pool_pre_ping": True}

app.config["TAX_RATE"] = 0.154

task_queue = None
try:
    redis_url = os.environ.get('REDIS_URL')
    if not redis_url:
        raise ValueError("REDIS_URL 환경 변수가 설정되지 않았습니다.")
    conn = redis.from_url(redis_url)
    task_queue = Queue('wealth-tracker-tasks', connection=conn)
except Exception as e:
    app.logger.error(f"Redis 연결 실패: {e}")

login_manager.init_app(app)
login_manager.login_view = 'main.login'
login_manager.login_message = "로그인이 필요한 페이지입니다."
login_manager.login_message_category = "info"

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

db.init_app(app)

from models import User
@login_manager.user_loader
def load_user(user_id): return User.query.get(int(user_id))

with app.app_context():
    import models
    db.create_all()
    from stock_api import load_us_stocks_data
    load_us_stocks_data()
    # 🛠️ 제거: 수동 재정의 파일 로딩 함수 호출 제거
    # from utils import load_manual_overrides
    # load_manual_overrides()

from routes import main_bp
app.register_blueprint(main_bp)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
