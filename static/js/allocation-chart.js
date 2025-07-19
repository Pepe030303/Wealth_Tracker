// 📄 static/js/allocation-chart.js
// ✨ New File: 포트폴리오 비중 페이지의 도넛 차트 렌더링 스크립트

document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('allocationPageContainer');
    if (!container) return;

    try {
        const allocationData = JSON.parse(container.dataset.allocationData || '[]');
        
        if (allocationData.length > 0) {
            // 차트 렌더링
            window.ChartUtils.requestPlugins(['datalabels'], () => {
                const allocationCtx = document.getElementById('allocationChart').getContext('2d');
                createAllocationChart(allocationCtx, allocationData);
            });
            // 테이블 렌더링
            renderAllocationTable(allocationData);
        }
    } catch (e) {
        console.error("Error parsing or rendering allocation chart data:", e);
    }
});

function createAllocationChart(ctx, data) {
    const labels = data.map(item => item.symbol);
    const values = data.map(item => item.value);

    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: generateChartColors(values.length),
                borderColor: '#343a40',
                borderWidth: 2,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#adb5bd',
                        padding: 15,
                        font: { size: 14 }
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            let label = context.label || '';
                            if (label) {
                                label += ': ';
                            }
                            const value = context.parsed;
                            const total = context.chart.data.datasets[0].data.reduce((a, b) => a + b, 0);
                            const percentage = ((value / total) * 100).toFixed(2);
                            return `${label}$${value.toFixed(2)} (${percentage}%)`;
                        }
                    }
                },
                datalabels: {
                    display: false // 도넛 차트 위에 직접 라벨 표시 안함
                }
            },
            cutout: '60%'
        }
    });
}

function renderAllocationTable(data) {
    const tableBody = document.getElementById('allocation-table-body');
    if (!tableBody) return;

    const totalValue = data.reduce((sum, item) => sum + item.value, 0);
    tableBody.innerHTML = ''; // 기존 내용 초기화

    data.forEach(item => {
        const percentage = totalValue > 0 ? ((item.value / totalValue) * 100).toFixed(2) : 0;
        const row = `
            <tr>
                <td><strong>${item.symbol}</strong></td>
                <td class="text-end">$${item.value.toFixed(2)}</td>
                <td class="text-end">${percentage}%</td>
            </tr>
        `;
        tableBody.innerHTML += row;
    });
}

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
