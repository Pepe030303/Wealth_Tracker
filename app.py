import os
import logging
from datetime import datetime
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_login import LoginManager # <-- 추가

# Set up logging
logging.basicConfig(level=logging.INFO)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
login_manager = LoginManager() # <-- 추가

# create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# configure the database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///investment_tracker.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_recycle": 300, "pool_pre_ping": True}

# Flask-Login 설정
login_manager.init_app(app)
login_manager.login_view = 'main.login' # <-- 로그인 페이지 엔드포인트
login_manager.login_message = "로그인이 필요한 페이지입니다."
login_manager.login_message_category = "info"

# Jinja2 필터들... (기존과 동일)
@app.template_filter('strftime')
def strftime_filter(datetime_obj, format_str='%Y-%m-%d'): ...
@app.template_filter('get_stock_logo_url')
def get_stock_logo_url_filter(symbol): ...
@app.template_filter('get_company_name')
def get_company_name_filter(symbol): ...
@app.template_filter('get_dividend_months')
def get_dividend_months_filter(symbol): ...

db.init_app(app)

# User 로더 함수 추가
from models import User
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    import models
    db.create_all()

# Import and register routes
from routes import main_bp
app.register_blueprint(main_bp)
