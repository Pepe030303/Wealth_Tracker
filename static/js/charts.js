# 📄 static/js/charts.js
// ✨ New File: 여러 페이지에서 공통으로 사용하는 차트 생성 함수 모음

/**
 * 차트 색상 팔레트를 생성합니다.
 * @param {number} count - 필요한 색상 수
 * @returns {string[]} 색상 배열
 */
function generateChartColors(count) {
    const colors = [
        '#667eea', '#764ba2', '#43e97b', '#38f9d7', '#209cff', '#6a11cb',
        '#fcb045', '#fd1d1d', '#fce38a', '#e0c3fc', '#8ec5fc', '#f093fb'
    ];
    let result = [];
    for (let i = 0; i < count; i++) {
        result.push(colors[i % colors.length]);
    }
    return result;
}

/**
 * 월별 배당금 막대 차트를 생성합니다.
 * @param {CanvasRenderingContext2D} ctx - 차트를 그릴 캔버스 컨텍스트
 * @param {object} monthlyData - 차트 데이터 (labels, datasets)
 * @param {function} onClickHandler - 막대 클릭 시 실행될 콜백 함수
 */
window.createMonthlyDividendChart = function(ctx, monthlyData, onClickHandler) {
    if (!ctx || !monthlyData) return;

    window.ChartUtils.requestPlugins(['datalabels'], () => {
        new Chart(ctx, {
            type: 'bar',
            data: {
                labels: monthlyData.labels,
                datasets: [{
                    label: '월별 배당금',
                    data: monthlyData.datasets[0].data,
                    backgroundColor: generateChartColors(12),
                    borderRadius: 4,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (c) => `$${Number(c.raw).toFixed(2)}`
                        }
                    },
                    datalabels: {
                        anchor: 'end',
                        align: 'end',
                        formatter: (value) => value > 0 ? `$${Math.round(value)}` : '',
                        color: '#adb5bd',
                        font: { size: 12 }
                    }
                },
                scales: {
                    x: { ticks: { color: '#868e96' }, grid: { display: false } },
                    y: { display: false, beginAtZero: true }
                },
                onClick: onClickHandler || null
            }
        });
    });
};

/**
 * 섹터 비중 트리맵 차트를 생성합니다.
 * @param {CanvasRenderingContext2D} ctx - 차트를 그릴 캔버스 컨텍스트
 * @param {object[]} sectorData - 섹터 데이터 배열
 */
window.createSectorAllocationChart = function(ctx, sectorData) {
    if (!ctx || !sectorData) return;

    window.ChartUtils.requestPlugins(['treemap', 'datalabels'], () => {
        const data = {
            datasets: [{
                tree: sectorData,
                key: 'value',
                groups: ['sector'],
                labels: {
                    display: true,
                    color: 'white',
                    font: { size: 14, weight: 'bold' },
                    formatter: (c) => [c.raw._data.sector, `$${c.raw.v.toFixed(0)}`]
                },
                backgroundColor: (c) => {
                    const colors = generateChartColors(sectorData.length);
                    return colors[c.index % colors.length];
                }
            }],
        };

        new Chart(ctx, {
            type: 'treemap',
            data: data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: { display: false },
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            title: (c) => c[0].raw._data.sector,
                            label: (c) => {
                                const item = c.raw._data;
                                const total = c.chart.getDatasetMeta(0).total;
                                const percentage = (item.value / total * 100).toFixed(2);
                                let details = item.holdings.slice(0, 5).map(h => `  - ${h.symbol}: $${h.value.toFixed(0)}`).join('\n');
                                if (item.holdings.length > 5) details += '\n  ...';
                                return [`$${item.value.toFixed(2)} (${percentage}%)`, details];
                            }
                        }
                    }
                }
            }
        });
    });
};

/**
 * 배당금 비중 도넛 차트를 생성합니다.
 * @param {CanvasRenderingContext2D} ctx - 차트를 그릴 캔버스 컨텍스트
 * @param {object[]} allocationData - 배당 비중 데이터
 */
window.createDividendAllocationChart = function(ctx, allocationData) {
    if (!ctx || !allocationData) return;
    
    const labels = allocationData.map(d => d.symbol);
    const data = allocationData.map(d => d.value);

    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                backgroundColor: generateChartColors(labels.length),
                borderColor: '#343a40',
                borderWidth: 2,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '60%',
            plugins: {
                legend: { position: 'bottom', labels: { color: '#adb5bd', padding: 15 } },
                tooltip: {
                    callbacks: {
                        label: (c) => {
                            const total = c.chart.data.datasets[0].data.reduce((a, b) => a + b, 0);
                            const percentage = (c.parsed / total * 100).toFixed(2);
                            return `${c.label}: $${c.parsed.toFixed(2)} (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });
};
