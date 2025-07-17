// 📄 static/js/dashboard-charts.js
// 🛠️ Refactor: templates/dashboard.html에서 분리된 스크립트
document.addEventListener('DOMContentLoaded', function () {
    const container = document.getElementById('dashboardPageContainer');
    if (!container) return;

    // 1. 월별 배당금 차트 생성
    const monthlyData = JSON.parse(container.dataset.monthlyData);
    if (monthlyData && Object.keys(monthlyData).length > 0) {
        // createMonthlyDividendChart는 static/js/charts.js에 정의되어 있음
        // 해당 파일이 먼저 로드되어야 함.
        if(typeof createMonthlyDividendChart === 'function') {
            createMonthlyDividendChart('monthlyDividendChart', monthlyData, false); // 세금 토글 기능 비활성화
        } else {
            console.error("createMonthlyDividendChart is not defined. Make sure charts.js is loaded first.");
        }
    }

    // 2. 섹터 비중 트리맵 차트 생성
    const sectorData = JSON.parse(container.dataset.sectorData);
    const sectorCtx = document.getElementById('sectorAllocationChart')?.getContext('2d');
    
    if (sectorCtx && sectorData && sectorData.length > 0) {
        window.ChartUtils.requestPlugins(['treemap', 'datalabels'], () => {
            Chart.register(ChartJsChartTreemap.TreemapController, ChartJsChartTreemap.TreemapElement, ChartDataLabels);

            const totalPortfolioValue = sectorData.reduce((sum, sector) => sum + sector.value, 0);
            new Chart(sectorCtx, {
                type: 'treemap',
                data: { 
                    datasets: [{
                        tree: sectorData, key: 'value', groups: ['sector'], 
                        labels: {
                            display: true, color: 'white', font: { size: 16, weight: 'bold' },
                            textStrokeColor: 'rgba(0,0,0,0.6)', textStrokeWidth: 2,
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
                            titleFont: { size: 14, weight: 'bold' }, bodyFont: { size: 12 },
                            callbacks: {
                                title: function(tooltipItems) { return `${tooltipItems[0].raw.g} | $${tooltipItems[0].raw.v.toFixed(2)}`; },
                                label: function(context) {
                                    const item = context.raw; const holdings = item._data.holdings || [];
                                    let holdingsText = ['\nHoldings:'];
                                    holdings.forEach(h => {
                                        const percentage = (h.value / item.v * 100).toFixed(1);
                                        holdingsText.push(`  ${h.symbol}: $${h.value.toFixed(2)} (${percentage}%)`);
                                    });
                                    return holdingsText;
                                }
                            }
                        },
                        datalabels: { display: true }
                    } 
                }
            });
        });
    }
});
