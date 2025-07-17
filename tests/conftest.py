# 📄 tests/conftest.py
# 🛠️ New File: Pytest 설정을 위한 파일 (Fixtures)

import pytest
from app import create_app, db
from models import User, Trade

@pytest.fixture(scope='module')
def test_app():
    """테스트용 Flask 애플리케이션 인스턴스를 생성합니다."""
    app = create_app()
    app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",  # 인메모리 DB 사용
        "WTF_CSRF_ENABLED": False,  # 테스트 시 CSRF 비활성화
        "LOGIN_DISABLED": True, # 테스트 시 로그인 비활성화
    })

    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()

@pytest.fixture()
def test_client(test_app):
    """테스트 클라이언트를 생성합니다."""
    return test_app.test_client()

@pytest.fixture()
def init_database(test_app):
    """테스트를 위한 초기 데이터를 DB에 삽입합니다."""
    with test_app.app_context():
        # 테스트 사용자 생성
        user = User(username='testuser', email='test@example.com')
        user.set_password('password')
        db.session.add(user)
        db.session.commit()
        
        yield db # 테스트 함수 실행
        
        # 테스트 후 데이터 정리
        db.session.remove()
        db.drop_all()
        db.create_all()
