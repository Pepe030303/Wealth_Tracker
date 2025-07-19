// 📄 static/js/stock-detail-chart.js
// ✨ New File: 종목 상세 페이지의 시세 차트 렌더링 스크립트

document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('stockDetailPageContainer');
    if (!container) return;

    try {
        const priceHistory = JSON.parse(container.dataset.priceHistory || '{}');
        const symbol = container.dataset.symbol;

        if (priceHistory.dates && priceHistory.dates.length > 0) {
            const chartCtx = document.getElementById('stockPriceChart').getContext('2d');
            createPriceHistoryChart(chartCtx, symbol, priceHistory);
        }
    } catch (e) {
        console.error("Error parsing or rendering stock price history data:", e);
    }
});

function createPriceHistoryChart(ctx, symbol, historyData) {
    const prices = historyData.prices;
    const startPrice = prices[0];
    const endPrice = prices[prices.length - 1];
    const borderColor = endPrice >= startPrice ? 'rgba(40, 167, 69, 0.8)' : 'rgba(220, 53, 69, 0.8)';
    const backgroundColor = endPrice >= startPrice ? 'rgba(40, 167, 69, 0.1)' : 'rgba(220, 53, 69, 0.1)';

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: historyData.dates,
            datasets: [{
                label: `${symbol} Price`,
                data: prices,
                borderColor: borderColor,
                backgroundColor: backgroundColor,
                borderWidth: 2,
                pointRadius: 0,
                fill: true,
                tension: 0.1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            if (context.parsed.y !== null) {
                                label += new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(context.parsed.y);
                            }
                            return label;
                        }
                    }
                }
            },
            scales: {
                x: {
                    display: true,
                    ticks: {
                        color: '#868e96',
                        maxRotation: 0,
                        autoSkip: true,
                        maxTicksLimit: 7 // X축 레이블 개수 제한
                    },
                    grid: {
                        display: false
                    }
                },
                y: {
                    display: true,
                    ticks: {
                        color: '#868e96',
                        callback: function(value) {
                            return '$' + value;
                        }
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.05)'
                    }
                }
            }
        }
    });
}
