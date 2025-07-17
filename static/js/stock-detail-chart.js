// 📄 static/js/stock-detail-chart.js
// 🛠️ Refactor: templates/stock_detail.html에서 분리된 스크립트
document.addEventListener('DOMContentLoaded', function () {
    const container = document.getElementById('stockDetailPageContainer');
    if (!container) return;

    const ctx = document.getElementById('stockPriceChart')?.getContext('2d');
    if (!ctx) return;
    
    // Jinja 템플릿에서 받은 데이터를 Javascript 변수로 변환
    const priceHistory = JSON.parse(container.dataset.priceHistory);
    const symbol = container.dataset.symbol;

    const labels = priceHistory.dates;
    const dataPoints = priceHistory.prices;
    
    // 가격 변동에 따른 선 색상 결정
    const firstPrice = dataPoints[0];
    const lastPrice = dataPoints[dataPoints.length - 1];
    const chartColor = lastPrice >= firstPrice ? 'rgba(25, 135, 84, 0.7)' : 'rgba(220, 53, 69, 0.7)';
    const chartBorderColor = lastPrice >= firstPrice ? '#198754' : '#dc3545';

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: `${symbol} Price ($)`,
                data: dataPoints,
                borderColor: chartBorderColor,
                backgroundColor: chartColor,
                fill: true,
                tension: 0.1, // 선을 부드럽게
                pointRadius: 0 // 데이터 포인트를 숨김
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    ticks: {
                        // X축 레이블이 너무 많으면 자동으로 건너뛰도록 설정
                        autoSkip: true,
                        maxTicksLimit: 10
                    }
                },
                y: {
                    ticks: {
                        // Y축 레이블에 달러($) 기호 추가
                        callback: function(value, index, values) {
                            return '$' + value;
                        }
                    }
                }
            },
            plugins: {
                tooltip: {
                    mode: 'index',
                    intersect: false
                }
            }
        }
    });
});
