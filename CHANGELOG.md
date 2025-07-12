2025-07-12 – [요청 A] – templates/stock_detail.html – 페이지에 노출되던 파이썬 주석을 템플릿 엔진이 렌더링하지 않는 Jinja2 주석 {# ... #}으로 변경하여 UI 오류 수정.
2025-07-12 – [요청 B] – utils.py – get_dividend_months 함수가 연간 실제 배당 횟수를 반환하도록 수정하여 TLT와 같은 월 2회 배당 케이스를 정확히 계산하도록 개선.
2025-07-12 – [요청 B] – routes.py – get_monthly_dividend_distribution 함수가 수정된 배당 횟수 로직을 사용하도록 변경.
2025-07-12 – [요청 B] – templates/dividends.html – Chart.js 데이터 라벨 플러그인을 추가하여 월별 배당금 차트 막대 위에 금액을 표시하고, 파이 차트 툴팁에 상세 정보(금액, 비중)가 나타나도록 수정.
2025-07-12 – [요청 C] – templates/base.html – 네비게이션 바의 검색창 구조를 변경하고 반응형 클래스를 적용하여 모바일/데스크톱 화면에서 UI가 깨지지 않도록 개선. 관련 CSS를 템플릿 내에 직접 추가.
2025-07-12 – [요청 D] – routes.py – 대시보드 라우트에서 섹터별 상세 종목 정보를 포함하도록 데이터 구조를 변경.
2025-07-12 – [요청 D] – templates/dashboard.html – 섹터 트리맵 차트의 폰트 크기를 키우고, 툴팁 콜백 함수를 수정하여 마우스 오버 시 해당 섹터의 상세 종목 리스트와 비중이 표시되도록 기능 개선.
2025-07-12 – [에러 수정] – app.py – korean_dividend_months 필터 로직을 단순화하여 TemplateAssertionError 원인 제거.
2025-07-12 – [에러 수정] – routes.py, templates/dividends.html – 템플릿에서 get_dividend_months 필터 직접 호출을 제거하고, 라우트(백엔드)에서 데이터를 모두 가공하여 전달하는 방식으로 변경하여 템플릿 오류 근본적으로 해결.
