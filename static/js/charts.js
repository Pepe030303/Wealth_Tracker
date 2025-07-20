/* 📄 static/js/charts.js */
// 🛠️ 버그 수정: 비어있던 파일에 공통 차트 생성 함수 로직 추가

/**
 * 월별 배당금 막대 차트를 생성하고 지정된 캔버스에 렌더링합니다.
 * @param {string} canvasId - 차트를 렌더링할 캔버스 요소의 ID
 * @param {object} monthlyData - 차트 데이터 (labels, datasets, detailed_data 포함)
 * @param {object} [options={}] - 추가 차트 옵션 (예: onClick 핸들러)
 * @returns {Chart} 생성된 Chart.js 인스턴스
 */
function createMonthlyDividendChart(canvasId, monthlyData, options = {}) {
    const ctx = document.getElementById(canvasId)?.getContext('2d');
    if (!ctx) return null;

    // 차트가 이미 존재하면 파괴하여 중복 생성을 방지
    if (Chart.getChart(canvasId)) {
        Chart.getChart(canvasId).destroy();
    }
    
    const chartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: monthlyData.labels,
            datasets: [{
                label: '월별 배당금',
                data: monthlyData.datasets[0].data,
                backgroundColor: 'rgba(25, 135, 84, 0.6)',
                borderColor: 'rgba(25, 135, 84, 1)',
                borderWidth: 1,
                borderRadius: 5,
                barThickness: 'flex',
                maxBarThickness: 50
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return ` 총액: $${context.parsed.y.toFixed(2)}`;
                        }
                    }
                },
                datalabels: {
                    anchor: 'end',
                    align: 'end',
                    formatter: (value) => value > 0 ? '$' + value.toFixed(0) : '',
                    color: '#adb5bd',
                    font: { weight: 'bold' }
                }
            },
            scales: {
                x: { grid: { display: false } },
                y: { display: false, beginAtZero: true }
            },
            // 외부에서 전달된 옵션 병합 (예: onClick)
            ...options
        }
    });

    return chartInstance;
}
