📈 투자 포트폴리오 관리 시스템 (Wealth Tracker)

Flask와 Redis 캐싱을 기반으로 구축된 개인 투자 포트폴리오 관리 웹 애플리케이션입니다. 수동으로 거래 내역을 기록하면, 복잡한 계산과 데이터 조회를 자동화하여 포트폴리오 현황을 한눈에 파악할 수 있도록 돕습니다.

📌 프로젝트 개요

이 애플리케이션은 스프레드시트나 여러 증권사 앱에 흩어져 있는 투자 정보를 하나로 통합하여, 다음과 같은 문제를 해결하는 것을 목표로 합니다:

정확한 수익률 계산: FIFO(선입선출) 회계 방식을 적용하여 매도된 주식을 제외한 현재 보유 주식의 정확한 평균 단가와 수익률을 계산합니다.

배당금 흐름 예측: 보유 종목을 기반으로 미래에 발생할 월별 예상 배당금과 연간 배당 흐름을 시각화하여 보여줍니다.

자산 배분 현황 분석: 내 자산이 어떤 종목과 섹터에 얼마나 배분되어 있는지 직관적인 차트로 분석할 수 있습니다.

통합 정보 탐색: 보유하지 않은 주식이라도 미국 시장 전체 종목을 검색하고, 상세 정보와 시세 차트를 바로 확인할 수 있습니다.

🔧 기술 스택
백엔드 (Backend)

언어/프레임워크: Python, Flask

데이터베이스: PostgreSQL (ORM: Flask-SQLAlchemy)

캐싱: Redis (API 응답 속도 향상 및 성능 병목 해결)

비동기 작업: RQ (Redis Queue) - 배당금 내역 등 시간이 걸리는 작업을 백그라운드에서 처리

데이터 소스: Yahoo Finance (yfinance 패키지), SEC (미국 증권거래위원회)

프론트엔드 (Frontend)

템플릿 엔진: Jinja2

UI 프레임워크: Bootstrap 5

차트 라이브러리: Chart.js (트리맵, 파이, 막대 차트 등), chartjs-plugin-datalabels

기타: Font Awesome (아이콘), Vanilla JavaScript

주요 Python 패키지

Flask, Flask-SQLAlchemy, Flask-Login

psycopg2-binary (PostgreSQL 드라이버)

yfinance, pandas (금융 데이터 수집 및 가공)

redis, rq (캐싱 및 백그라운드 작업)

gunicorn (프로덕션 WSGI 서버)

🚀 설치 및 실행 방법
1. 프로젝트 클론
Generated bash
git clone <your-repository-url>
cd wealth-tracker

2. 가상환경 생성 및 활성화
Generated bash
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate    # Windows
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Bash
IGNORE_WHEN_COPYING_END
3. 의존성 패키지 설치

requirements.txt 파일에 명시된 모든 패키지를 설치합니다.

Generated bash
pip install -r requirements.txt
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Bash
IGNORE_WHEN_COPYING_END
4. 환경변수 설정

프로젝트 루트 디렉토리에 .env 파일을 생성하고 아래 내용을 채워주세요.

Generated env
# 데이터베이스 URL (로컬 SQLite 예시)
# 프로덕션에서는 PostgreSQL URL을 사용합니다. (예: postgresql://user:password@host:port/dbname)
DATABASE_URL=sqlite:///investment.db

# Redis URL (캐싱 및 백그라운드 작업용)
# 로컬에 Redis가 설치되어 있어야 합니다.
REDIS_URL=redis://localhost:6379/0

# Flask 세션 암호화를 위한 시크릿 키
SESSION_SECRET=your-very-secret-key
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Env
IGNORE_WHEN_COPYING_END
5. 데이터베이스 초기화 및 앱 실행

로컬 개발 서버 실행:

Generated bash
flask run
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Bash
IGNORE_WHEN_COPYING_END

백그라운드 워커 실행 (별도의 터미널에서):
배당금 내역 자동 업데이트 등을 위해 필요합니다.

Generated bash
rq worker wealth-tracker-tasks
```이제 웹 브라우저에서 `http://127.0.0.1:5000`으로 접속하여 애플리케이션을 사용할 수 있습니다.
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Bash
IGNORE_WHEN_COPYING_END
🌐 주요 기능 상세
📊 대시보드

로그인 후 가장 먼저 마주하는 메인 화면입니다.

자산 요약: 총 평가금액, 총 투자원금, 총 손익 및 수익률을 한눈에 보여주는 위젯 카드.

섹터 비중: 보유 자산이 어떤 산업 섹터에 분포되어 있는지 시각적인 트리맵 차트로 보여줍니다. 각 섹터에 마우스를 올리면 포함된 종목 리스트와 비중을 확인할 수 있습니다.

월별 예상 배당금: 미래에 수령할 월별 배당금 총액을 막대그래프로 예측하여 보여줍니다.

💸 배당금 분석

예상 배당금 (/dividends):

보유 종목별 연간 예상 배당금과 배당수익률을 테이블로 제공합니다.

전체 예상 배당금 중 각 종목이 차지하는 비중을 파이 차트로 보여줍니다.

배당금 입금 내역 (/dividends/history):

과거에 실제로 지급된 배당금 기록을 날짜순으로 보여줍니다.

이 데이터는 백그라운드에서 주기적으로 업데이트됩니다.

🔍 종목 검색 및 상세 정보

전역 검색: 모든 페이지 상단의 검색창을 통해 미국 주식/ETF를 실시간으로 검색할 수 있습니다.

종목 상세 페이지 (/stock/<symbol>):

검색 결과 클릭 시 이동하는 페이지로, 해당 종목의 6개월 시세 차트와 주요 정보를 제공합니다.

📝 거래 내역 관리

FIFO 기반 계산: 모든 보유 종목의 수량과 평균 단가는 /trades 페이지에 기록된 매수/매도 내역을 기반으로 자동 계산됩니다. 사용자가 직접 평균 단가를 입력할 필요가 없습니다.

매도 유효성 검사: 특정 종목을 매도할 때, 현재 보유 수량을 초과하여 매도할 수 없도록 시스템이 자동으로 검증합니다.

🧪 테스트 및 배포
로컬 테스트

회원가입 후 로그인합니다.

/trades 페이지에서 몇 가지 종목(예: AAPL, SCHD, TLT)의 매수 기록을 다른 날짜로 추가합니다.

/holdings 페이지에서 평균 단가와 수량이 정확히 계산되었는지 확인합니다.

/dashboard와 /dividends 페이지에 접속하여 차트와 데이터가 정상적으로 표시되는지 확인합니다. 이 때 API 호출로 인해 초기 로딩이 약간 길 수 있습니다.

페이지를 새로고침했을 때, Redis 캐시 덕분에 로딩 속도가 현저히 빨라지는지 확인합니다.

상단 검색창에서 'MSFT' 등을 검색하여 상세 페이지로 정상 이동하는지 테스트합니다.

Render 배포 가이드

이 프로젝트는 render.yaml 설정 파일을 포함하고 있어 Render.com에 쉽게 배포할 수 있습니다.

서비스 구성:

Web Service: Flask 웹 애플리케이션 (Gunicorn 실행)

Worker: 백그라운드 작업 처리 (RQ 워커 실행)

Redis: 캐싱 및 메시지 큐

PostgreSQL: 데이터베이스

주의사항:

Render 환경변수에 DATABASE_URL, REDIS_URL, SESSION_SECRET이 정상적으로 설정되었는지 확인해야 합니다.

Free Plan에서는 일정 시간 미사용 시 서비스가 잠자기(sleep) 상태에 들어갈 수 있습니다.

🗂️ 폴더 구조
Generated code
/
├── app.py                  # Flask 애플리케이션 팩토리 및 초기 설정
├── routes.py               # 모든 웹 페이지 라우팅 및 뷰 로직
├── models.py               # SQLAlchemy 데이터베이스 모델 정의 (User, Trade 등)
├── services/               # 비즈니스 로직 분리 (코드 중복 방지)
│   └── portfolio_service.py # 포트폴리오 데이터 계산 로직 중앙화
├── utils.py                # 유틸리티 함수 (배당 정보 계산 등)
├── stock_api.py            # 외부 금융 API 호출 및 캐싱 로직
├── tasks.py                # RQ 백그라운드 작업 정의 (배당금 동기화 등)
├── static/                 # CSS, JavaScript, 이미지 등 정적 파일
├── templates/              # Jinja2 HTML 템플릿
├── requirements.txt        # Python 의존성 패키지 목록
└── render.yaml             # Render.com 배포 설정 파일
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
IGNORE_WHEN_COPYING_END
✍️ 기여 방법

이 프로젝트에 기여하고 싶으신 분은 언제든지 환영합니다.

이 저장소를 Fork합니다.

새로운 기능이나 버그 수정을 위한 브랜치를 생성합니다. (git checkout -b feature/amazing-feature)

코드를 수정하고 커밋합니다. (git commit -m 'Add some amazing feature')

원본 저장소로 Pull Request를 생성합니다.

코드 스타일은 PEP 8을 준수하며, 가급적 명확하고 간결한 코드를 지향합니다.

📎 라이선스

이 프로젝트는 MIT 라이선스를 따릅니다. 자세한 내용은 LICENSE 파일을 참고하세요.
