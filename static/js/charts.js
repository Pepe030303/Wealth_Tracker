// 📄 static/js/charts.js
// 🛠️ 신규 파일: 공통 차트 생성 로직을 모듈화

/**
 * 월별 배당금 바 차트를 생성하는 공통 함수
 * @param {string} canvasId - 차트를 그릴 canvas 요소의 ID
 * @param {object} chartData - 차트 데이터 (labels, datasets 포함)
 * @param {function|null} onClickCallback - 차트 바 클릭 시 실행될 콜백 함수 (인자로 index 전달)
 */
function createMonthlyDividendChart(canvasId, chartData, onClickCallback = null) {
    const ctx = document.getElementById(canvasId)?.getContext('2d');
    if (!ctx || !chartData || !chartData.datasets || chartData.datasets[0].data.length === 0) {
        console.warn(`Chart with id #${canvasId} could not be created. Missing canvas or data.`);
        return null;
    }

    // 전역 플러그인 등록 해제 (페이지별로 독립적인 설정을 위함)
    Chart.register(ChartDataLabels);

    const chartInstance = new Chart(ctx, {
        type: 'bar',
        data: { 
            labels: chartData.labels, 
            datasets: [{
                label: '월별 배당금',
                data: chartData.datasets[0].data,
                backgroundColor: 'rgba(25, 135, 84, 0.6)',
                borderColor: 'rgba(25, 135, 84, 1)',
                borderWidth: 1,
                borderRadius: 8,
                borderSkipped: false,
            }]
        },
        options: {
            responsive: true, 
            maintainAspectRatio: false,
            layout: { padding: { top: 30 } },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (context) => `총액: $${context.parsed.y.toFixed(2)}`
                    }
                },
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
            },
            onClick: (event, elements) => {
                if (onClickCallback && elements.length > 0) {
                    const chartElement = elements[0];
                    onClickCallback(chartElement.index);
                }
            }
        }
    });

    return chartInstance;
}
