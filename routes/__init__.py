# 📄 routes/__init__.py
# 🛠️ 이 파일의 내용은 정확해야 합니다. 다시 한번 확인을 위해 제공합니다.

def register_blueprints(app):
    """애플리케이션에 모든 Blueprint를 등록합니다."""
    from .auth import auth_bp
    from .portfolio import portfolio_bp
    from .trades import trades_bp
    from .stock import stock_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(portfolio_bp)
    app.register_blueprint(trades_bp, url_prefix='/trades')
    app.register_blueprint(stock_bp)
