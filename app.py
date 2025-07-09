# app.py

import os
import logging
from datetime import datetime
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_login import LoginManager

# 로깅 설정
logging.basicConfig(level=logging.INFO)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()

# 앱 생성
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# 데이터베이스 설정
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL") # .env 파일에서 읽어옴
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 280, # Railway MySQL 기본 타임아웃보다 짧게 설정
    "pool_pre_ping": True,
}

# Flask-Login 설정
login_manager.init_app(app)
login_manager.login_view = 'main.login'
login_manager.login_message = "로그인이 필요한 페이지입니다."
login_manager.login_message_category = "info"

# Jinja2 커스텀 필터
@app.template_filter('strftime')
def strftime_filter(datetime_obj, format_str='%Y-%m-%d'):
    if isinstance(datetime_obj, str):
        if datetime_obj == 'now': return datetime.now().strftime(format_str)
        return datetime_obj
    return datetime_obj.strftime(format_str)

@app.template_filter('get_stock_logo_url')
def get_stock_logo_url_filter(symbol):
    from models import get_stock_logo_url
    return get_stock_logo_url(symbol)

@app.template_filter('get_company_name')
def get_company_name_filter(symbol):
    from models import get_company_name
    return get_company_name(symbol)

@app.template_filter('get_dividend_months')
def get_dividend_months_filter(symbol):
    from models import get_dividend_months
    return get_dividend_months(symbol)

# DB 확장 초기화
db.init_app(app)

# User 로더 함수
from models import User
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# 앱 컨텍스트 내에서 DB 테이블 생성
with app.app_context():
    import models
    db.create_all()

# 라우트 블루프린트 등록
from routes import main_bp
app.register_blueprint(main_bp)
