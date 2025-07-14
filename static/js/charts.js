// 📄 static/js/charts.js

/**
 * 월별 배당금 차트를 렌더링하는 공통 함수
 * @param {string} canvasId - 차트를 그릴 캔버스 요소의 ID
 * @param {object} chartData - 차트 데이터 (labels, datasets 포함)
 * @param {boolean} isClickable - 차트 클릭 이벤트를 활성화할지 여부
 */
function renderMonthlyDividendChart(canvasId, chartData, isClickable = false) {
    const ctx = document.getElementById(canvasId)?.getContext('2d');
    if (!ctx || !chartData || !chartData.datasets || chartData.datasets.length === 0) {
        return;
    }

    let activeIndex = -1;
    const defaultColor = 'rgba(25, 135, 84, 0.6)';
    const activeColor = 'rgba(25, 135, 84, 1)';
    const inactiveColor = 'rgba(200, 200, 200, 0.5)';

    const chartOptions = {
        responsive: true,
        maintainAspectRatio: false,
        layout: { padding: { top: 30 } },
        plugins: {
            legend: { display: false },
            tooltip: { callbacks: { label: (context) => `총액: $${context.parsed.y.toFixed(2)}` } },
            datalabels: {
                anchor: 'end',
                align: 'top',
                formatter: (value) => value > 0 ? '$' + value.toFixed(2) : null,
                color: '#adb5bd',
                font: { weight: 'bold' }
            }
        },
        scales: {
            x: { grid: { display: false } },
            y: { display: false, beginAtZero: true }
        }
    };
    
    // 🛠️ UX 개선: 클릭 이벤트 로직 추가
    if (isClickable) {
        chartOptions.onClick = (event, elements, chart) => {
            if (elements.length > 0) {
                const clickedIndex = elements[0].index;
                
                // 이미 활성화된 막대를 다시 클릭하면 초기화
                if (activeIndex === clickedIndex) {
                    activeIndex = -1;
                    document.getElementById('closeMonthlyDetail')?.click(); // 상세 뷰 닫기
                } else {
                    activeIndex = clickedIndex;
                    if (window.renderMonthlyDetails) {
                        window.renderMonthlyDetails(activeIndex);
                    }
                }
                
                // 모든 막대의 색상을 동적으로 업데이트
                const backgroundColors = chart.data.datasets[0].data.map((_, i) => 
                    activeIndex === -1 ? defaultColor : (i === activeIndex ? activeColor : inactiveColor)
                );
                chart.data.datasets[0].backgroundColor = backgroundColors;
                chart.update();
            }
        };
    }

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: chartData.labels,
            datasets: [{
                label: '월별 배당금',
                data: chartData.datasets[0].data,
                backgroundColor: defaultColor,
                borderColor: 'rgba(25, 135, 84, 1)',
                borderRadius: 4,
                borderSkipped: false
            }]
        },
        options: chartOptions
    });
}

function renderSectorAllocationChart(canvasId, chartData) {
    const ctx = document.getElementById(canvasId)?.getContext('2d');
    if (!ctx || !chartData || chartData.length === 0) {
        return;
    }

    const totalPortfolioValue = chartData.reduce((sum, sector) => sum + sector.value, 0);

    new Chart(ctx, {
        type: 'treemap',
        data: {
            datasets: [{
                tree: chartData,
                key: 'value',
                groups: ['sector'],
                labels: {
                    display: true,
                    color: 'white',
                    font: { size: 16, weight: 'bold' },
                    textStrokeColor: 'rgba(0,0,0,0.6)',
                    textStrokeWidth: 2,
                    formatter(context) {
                        if (context.raw) {
                            const item = context.raw;
                            const percentage = (item.v / totalPortfolioValue * 100).toFixed(1);
                            return [item.g, `$${item.v.toFixed(0)}`, `(${percentage}%)`];
                        }
                        return null;
                    }
                },
                backgroundColor: (ctx) => {
                    const colors = ['#0d6efd', '#198754', '#ffc107', '#dc3545', '#6c757d', '#0dcaf0', '#6f42c1', '#fd7e14'];
                    if (ctx.type === 'dataset') return 'transparent';
                    return colors[ctx.dataIndex % colors.length];
                }
            }]
        },
        options: {
            plugins: {
                legend: { display: false },
                tooltip: {
                    titleFont: { size: 14, weight: 'bold' },
                    bodyFont: { size: 12 },
                    callbacks: {
                        title: function(tooltipItems) {
                            return `${tooltipItems[0].raw.g} | $${tooltipItems[0].raw.v.toFixed(2)}`;
                        },
                        label: function(context) {
                            const item = context.raw;
                            const holdings = item._data.holdings || [];
                            let holdingsText = ['\nHoldings:'];
                            holdings.forEach(h => {
                                const percentage = (h.value / item.v * 100).toFixed(1);
                                holdingsText.push(`  ${h.symbol}: $${h.value.toFixed(2)} (${percentage}%)`);
                            });
                            return holdingsText;
                        }
                    }
                }
            }
        }
    });
}
