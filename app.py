import os
import logging
from datetime import datetime
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix

# Set up logging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

# create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# configure the database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///investment_tracker.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Add custom Jinja2 filters
@app.template_filter('strftime')
def strftime_filter(datetime_obj, format_str='%Y-%m-%d'):
    """Format a datetime object using strftime"""
    if isinstance(datetime_obj, str):
        if datetime_obj == 'now':
            return datetime.now().strftime(format_str)
        return datetime_obj
    return datetime_obj.strftime(format_str)

@app.template_filter('get_stock_logo_url')
def get_stock_logo_url_filter(symbol):
    """Get stock logo URL filter for templates"""
    from models import get_stock_logo_url
    return get_stock_logo_url(symbol)

@app.template_filter('get_company_name')
def get_company_name_filter(symbol):
    """Get company name filter for templates"""
    from models import get_company_name
    return get_company_name(symbol)

@app.template_filter('get_dividend_months')
def get_dividend_months_filter(symbol):
    """Get dividend months filter for templates"""
    from models import get_dividend_months
    return get_dividend_months(symbol)

# initialize the app with the extension
db.init_app(app)

with app.app_context():
    # Import models to ensure tables are created
    import models
    db.create_all()

# Import and register routes
from routes import main_bp
app.register_blueprint(main_bp)
