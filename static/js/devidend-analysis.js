/* 📄 static/js/dividend-analysis.js */
// 🛠️ 신규 파일: dividends.html의 스크립트 로직을 분리

document.addEventListener('DOMContentLoaded', function() {
    const container = document.getElementById('dividendAnalysisContainer');
    if (!container) return;

    // 데이터셋 가져오기
    const allocationData = JSON.parse(container.dataset.allocationData);
    const monthlyData = JSON.parse(container.dataset.monthlyData);
    const taxRate = parseFloat(container.dataset.taxRate);

    let isTaxApplied = false;

    // 필요한 플러그인 로드 후 차트 및 이벤트 리스너 초기화
    window.ChartUtils.requestPlugins(['datalabels'], () => {
        Chart.register(ChartDataLabels);

        // 월별 배당 차트 생성
        if (monthlyData && monthlyData.datasets && monthlyData.datasets[0].data.some(d => d > 0)) {
            const monthlyChart = createMonthlyDividendChart('monthlyDividendChart', monthlyData, {
                onClick: (event, elements, chart) => {
                    if (elements.length > 0) {
                        const monthIndex = elements[0].index;
                        displayMonthlyDetail(monthIndex);
                        // 선택된 막대 강조
                        chart.setActiveElements([{ datasetIndex: 0, index: monthIndex }]);
                        chart.update();
                    }
                }
            });
            
            // 차트 외부 클릭 시 활성 요소 초기화
            document.addEventListener('click', (event) => {
                if (event.target.id !== 'monthlyDividendChart') {
                    monthlyChart.setActiveElements([]);
                    monthlyChart.update();
                }
            });
        }

        // 배당 비중 도넛 차트 생성 (모달)
        const allocationModal = document.getElementById('allocationModal');
        allocationModal.addEventListener('shown.bs.modal', () => {
            createDividendAllocationChart('dividendAllocationChart', allocationData);
        }, { once: true });

        // 이벤트 리스너 초기화
        initializeEventListeners();
    });

    /**
     * 페이지의 모든 이벤트 리스너를 설정합니다.
     */
    function initializeEventListeners() {
        // 세금 토글 스위치
        const taxToggle = document.getElementById('taxToggleSwitch');
        taxToggle.addEventListener('change', (e) => {
            isTaxApplied = e.target.checked;
            updateTaxDisplay();
        });

        // 월별 상세 정보 닫기 버튼
        const closeMonthlyDetailBtn = document.getElementById('closeMonthlyDetail');
        closeMonthlyDetailBtn.addEventListener('click', () => {
            document.getElementById('monthlyDetail').classList.add('d-none');
        });

        // 종목 카드 클릭 이벤트 (배당 성장률 차트 토글)
        document.querySelectorAll('.stock-card-interactive').forEach(card => {
            card.addEventListener('click', function() {
                const symbol = this.dataset.symbol;
                const historyData = JSON.parse(this.dataset.history);
                toggleDividendHistoryChart(symbol, historyData);
            });
        });
    }

    /**
     * 세금 적용 여부에 따라 화면의 모든 금액 표시를 업데이트합니다.
     */
    function updateTaxDisplay() {
        const taxMultiplier = isTaxApplied ? (1 - taxRate) : 1;
        document.querySelectorAll('.tax-value').forEach(el => {
            const pretaxValue = parseFloat(el.dataset.pretaxValue);
            const valueToShow = pretaxValue * taxMultiplier;
            el.textContent = `$${valueToShow.toFixed(2)}`;
        });
        document.getElementById('taxToggleLabel').textContent = isTaxApplied ? '세후' : '세전';
    }

    /**
     * 특정 월의 상세 배당 내역을 표시합니다.
     * @param {number} monthIndex - 월 인덱스 (0-11)
     */
    function displayMonthlyDetail(monthIndex) {
        const detailContainer = document.getElementById('monthlyDetail');
        const detailTitle = document.getElementById('monthlyDetailTitle');
        const detailContent = document.getElementById('monthlyDetailContent');

        const monthName = monthlyData.labels[monthIndex];
        const items = monthlyData.detailed_data[monthIndex];
        const totalAmount = items.reduce((sum, item) => sum + item.amount, 0);

        detailTitle.textContent = `${monthName} 배당 상세 내역 (총: $${totalAmount.toFixed(2)})`;
        detailContent.innerHTML = '';

        if (items.length > 0) {
            items.sort((a, b) => b.amount - a.amount);
            items.forEach(item => {
                const itemHtml = `
                    <div class="list-group-item d-flex justify-content-between align-items-center">
                        <div>
                            <strong class="me-2">${item.symbol}</strong>
                            <small class="text-muted">(${item.quantity}주, 주당 $${item.dps_per_payout.toFixed(4)})</small>
                            <br>
                            <small class="text-muted">예측 배당락일: ${item.ex_dividend_date}</small>
                        </div>
                        <span class="badge bg-success rounded-pill fs-6">$${item.amount.toFixed(2)}</span>
                    </div>`;
                detailContent.insertAdjacentHTML('beforeend', itemHtml);
            });
        } else {
            detailContent.innerHTML = '<p class="text-muted text-center m-0">해당 월의 배당 정보가 없습니다.</p>';
        }

        detailContainer.classList.remove('d-none');
    }

    /**
     * 종목별 배당금 비중을 보여주는 도넛 차트를 생성합니다.
     * @param {string} canvasId - 캔버스 요소의 ID
     * @param {Array} data - 차트 데이터
     */
    function createDividendAllocationChart(canvasId, data) {
        const ctx = document.getElementById(canvasId)?.getContext('2d');
        if (!ctx) return;

        // 차트가 이미 생성되었다면 파괴
        if (Chart.getChart(canvasId)) {
            Chart.getChart(canvasId).destroy();
        }

        const labels = data.map(d => d.symbol);
        const values = data.map(d => d.value);

        new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: values,
                    backgroundColor: ['#0d6efd', '#198754', '#ffc107', '#dc3545', '#0dcaf0', '#6f42c1', '#fd7e14', '#20c997', '#6610f2', '#6c757d'],
                    borderColor: '#343a40',
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'right' },
                    tooltip: {
                        callbacks: {
                            label: (context) => {
                                const total = context.chart.getData().datasets[0].data.reduce((a, b) => a + b, 0);
                                const percentage = (context.parsed / total * 100).toFixed(2);
                                return ` ${context.label}: $${context.parsed.toFixed(2)} (${percentage}%)`;
                            }
                        }
                    },
                    datalabels: { display: false }
                }
            }
        });
    }
    
    /**
     * 종목별 과거 배당금 이력 차트를 토글합니다.
     * @param {string} symbol - 종목 심볼
     * @param {Array} historyData - 배당 이력 데이터
     */
    function toggleDividendHistoryChart(symbol, historyData) {
        const detailContainer = document.getElementById(`detail-${symbol}`);
        const isCollapsed = detailContainer.classList.contains('collapse');

        if (isCollapsed) {
            // 차트 생성
            if (historyData && historyData.length > 0) {
                const years = {};
                historyData.forEach(item => {
                    const year = item.date.substring(0, 4);
                    years[year] = (years[year] || 0) + item.amount;
                });

                const labels = Object.keys(years).sort();
                const data = labels.map(year => years[year]);

                const canvas = document.createElement('canvas');
                detailContainer.innerHTML = '';
                detailContainer.appendChild(canvas);
                new Chart(canvas.getContext('2d'), {
                    type: 'bar',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: '연간 주당 배당금 (보정됨)',
                            data: data,
                            backgroundColor: 'rgba(25, 135, 84, 0.5)',
                            borderColor: 'rgba(25, 135, 84, 1)',
                            borderWidth: 1
                        }]
                    },
                    options: {
                        plugins: { legend: { display: false } },
                        scales: { y: { beginAtZero: true, ticks: { callback: value => '$' + value.toFixed(2) } } }
                    }
                });
            } else {
                detailContainer.innerHTML = '<p class="text-center text-muted p-3">배당 이력 데이터가 없습니다.</p>';
            }
        }
        
        // 부트스트랩의 Collapse 인스턴스를 사용하여 토글
        const collapse = bootstrap.Collapse.getOrCreateInstance(detailContainer);
        collapse.toggle();
    }
});```
