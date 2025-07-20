# 📄 static/js/dashboard-charts.js
// ✨ New File: 대시보드 페이지의 차트 렌더링 로직
document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('dashboardPageContainer');
    if (!container) return;

    // 1. 월별 배당금 차트
    const monthlyCtx = document.getElementById('monthlyDividendChart')?.getContext('2d');
    if (monthlyCtx) {
        const monthlyData = JSON.parse(container.dataset.monthlyData || '{}');
        if (monthlyData && monthlyData.labels) {
            createMonthlyDividendChart(monthlyCtx, monthlyData);
        }
    }

    // 2. 섹터 비중 차트 (Treemap)
    const sectorCtx = document.getElementById('sectorAllocationChart')?.getContext('2d');
    if (sectorCtx) {
        const sectorData = JSON.parse(container.dataset.sectorData || '[]');
        if (sectorData.length > 0) {
            // base.html의 ChartUtils를 사용하여 treemap 플러그인을 로드합니다.
            window.ChartUtils.requestPlugins(['treemap'], () => {
                createSectorAllocationChart(sectorCtx, sectorData);
            });
        }
    }
});

function createMonthlyDividendChart(ctx, data) {
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.labels,
            datasets: [{
                label: '월별 배당금',
                data: data.datasets[0].data,
                backgroundColor: 'rgba(102, 126, 234, 0.7)',
                borderColor: 'rgba(102, 126, 234, 1)',
                borderWidth: 1,
                borderRadius: 5,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `배당금: $${context.parsed.y.toFixed(2)}`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function(value) {
                            return '$' + value;
                        }
                    }
                },
                x: { grid: { display: false } }
            }
        }
    });
}

function createSectorAllocationChart(ctx, data) {
    const totalValue = data.reduce((sum, item) => sum + item.value, 0);
    const chartData = data.map(item => ({
        ...item,
        value: item.value,
        // 툴팁에 표시될 종목 정보 포맷팅
        holdingsTooltip: item.holdings.map(h => `${h.symbol}: ${((h.value / item.value) * 100).toFixed(1)}%`).join('\n')
    }));

    new Chart(ctx, {
        type: 'treemap',
        data: {
            datasets: [{
                label: '섹터 비중',
                tree: chartData,
                key: 'value',
                groups: ['sector'],
                backgroundColor: (c) => Chart.Colors.get(c.index),
                labels: {
                    display: true,
                    formatter: (c) => [c.raw._data.sector, `$${c.raw.v.toFixed(0)}`, `${((c.raw.v / totalValue) * 100).toFixed(1)}%`]
                }
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        title: (c) => c[0].raw._data.sector,
                        label: (c) => {
                           const item = c.raw._data;
                           const percentage = ((item.value / totalValue) * 100).toFixed(2);
                           return ` 평가금액: $${item.value.toFixed(2)} (${percentage}%)`;
                        },
                        afterBody: (c) => c[0].raw._data.holdingsTooltip,
                    }
                }
            }
        }
    });
}
