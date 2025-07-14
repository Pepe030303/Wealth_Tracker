// 📄 static/js/charts.js

/**
 * 월별 배당금 차트를 렌더링하는 공통 함수
 * @param {string} canvasId - 차트를 그릴 캔버스 요소의 ID
 * @param {object} chartData - 차트 데이터 (labels, datasets 포함)
 * @param {boolean} isClickable - 차트 클릭 이벤트를 활성화할지 여부
 */
function renderMonthlyDividendChart(canvasId, chartData, isClickable = false) {
    const ctx = document.getElementById(canvasId)?.getContext('2d');
    // 🛠️ 안정성 강화: 컨텍스트나 데이터가 없으면 함수를 조용히 종료
    if (!ctx || !chartData || !chartData.datasets || chartData.datasets.length === 0) {
        return;
    }

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

    if (isClickable) {
        chartOptions.onClick = (event, elements) => {
            if (elements.length > 0) {
                const index = elements[0].index;
                if (window.renderMonthlyDetails) {
                    window.renderMonthlyDetails(index);
                }
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
                backgroundColor: 'rgba(25, 135, 84, 0.6)',
                borderColor: 'rgba(25, 135, 84, 1)',
                borderRadius: 4,
                borderSkipped: false
            }]
        },
        options: chartOptions
    });
}

/**
 * 섹터 비중 트리맵 차트를 렌더링하는 공통 함수
 * @param {string} canvasId - 차트를 그릴 캔버스 요소의 ID
 * @param {Array} chartData - 섹터 데이터 배열
 */
function renderSectorAllocationChart(canvasId, chartData) {
    const ctx = document.getElementById(canvasId)?.getContext('2d');
    // 🛠️ 안정성 강화: 컨텍스트나 데이터가 없으면 함수를 조용히 종료
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
