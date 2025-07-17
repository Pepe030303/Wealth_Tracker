# 🏛️ 프로젝트 구조 (Project Structure)

이 문서는 Wealth Tracker 프로젝트의 주요 디렉토리와 파일 구조 및 각각의 역할을 설명합니다.

```text
/
├── app.py                  # [핵심] Flask 애플리케이션 팩토리 및 초기 설정
├── routes/                 # [신규] 기능별 라우트 Blueprint 모음
│   ├── __init__.py         # Blueprint 등록 및 초기화
│   ├── auth.py             # 인증(로그인/회원가입) 관련 라우트
│   ├── portfolio.py        # 포트폴리오(대시보드/보유종목 등) 관련 라우트
│   ├── stock.py            # 개별 종목 조회 및 API 관련 라우트
│   └── trades.py           # 거래 기록 관련 라우트
├── models.py               # SQLAlchemy 데이터베이스 모델 정의
├── services/               # [강점] 비즈니스 로직 분리
│   ├── portfolio_service.py # 사용자 포트폴리오 데이터 계산/분석 로직
│   └── stock_data_service.py# 일반 주식 데이터 계산/분석 로직
├── tests/                  # [신규] 자동화 테스트 코드
│   ├── __init__.py
│   ├── conftest.py         # Pytest 설정 및 Fixture 정의
│   └── test_portfolio_service.py # 서비스 계층 단위 테스트
├── utils.py                # 범용 유틸리티 함수 (캐싱 헬퍼 등)
├── stock_api.py            # [강점] 외부 금융 API 호출 및 캐싱 로직
├── tasks.py                # [강점] RQ 백그라운드 작업 정의
├── static/                 # CSS, JavaScript, 이미지 등 정적 파일
├── templates/              # Jinja2 HTML 템플릿
├── requirements.txt        # Python 의존성 패키지 목록
├── render.yaml             # Render.com 배포 설정 파일
├── CHANGELOG.md            # 버전별 변경 이력
└── README.md               # 프로젝트 개요 및 설정 가이드
