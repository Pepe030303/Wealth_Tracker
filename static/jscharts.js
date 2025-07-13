// 📄 static/js/charts.js

/**
 * 월별 배당금 차트를 렌더링하는 공통 함수
 * @param {string} canvasId - 차트를 그릴 캔버스 요소의 ID
 * @param {object} chartData - 차트 데이터 (labels, datasets 포함)
 * @param {boolean} isClickable - 차트 클릭 이벤트를 활성화할지 여부
 */
function renderMonthlyDividendChart(canvasId, chartData, isClickable = false) {
    const ctx = document.getElementById(canvasId)?.getContext('2d');
    if (!ctx) return;

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
                // dividends.html 페이지에만 존재하는 함수를 호출
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
