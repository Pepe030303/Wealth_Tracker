# app.py

import os
import logging
from datetime import datetime
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_login import LoginManager

logging.basicConfig(level=logging.INFO)

class Base(DeclarativeBase): pass
db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-for-local-testing")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_recycle": 280, "pool_pre_ping": True}

login_manager.init_app(app)
login_manager.login_view = 'main.login'
login_manager.login_message = "로그인이 필요한 페이지입니다."
login_manager.login_message_category = "info"

@app.template_filter('strftime')
def strftime_filter(dt, fmt='%Y-%m-%d'):
    if isinstance(dt, str): return datetime.now().strftime(fmt) if dt == 'now' else dt
    return dt.strftime(fmt)

@app.template_filter('get_stock_logo_url')
def get_stock_logo_url_filter(symbol): from models import get_stock_logo_url; return get_stock_logo_url(symbol)
@app.template_filter('get_company_name')
def get_company_name_filter(symbol): from models import get_company_name; return get_company_name(symbol)
@app.template_filter('get_dividend_months')
def get_dividend_months_filter(symbol): from models import get_dividend_months; return get_dividend_months(symbol)

db.init_app(app)

from models import User
@login_manager.user_loader
def load_user(user_id): return User.query.get(int(user_id))

with app.app_context():
    import models
    db.create_all()

from routes import main_bp
app.register_blueprint(main_bp)
