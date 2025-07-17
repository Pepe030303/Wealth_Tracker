// 📄 static/js/allocation-chart.js
// 🛠️ Refactor: templates/allocation.html에서 분리된 스크립트
document.addEventListener('DOMContentLoaded', function() {
    const container = document.getElementById('allocationPageContainer');
    if (!container) return;

    const allocationData = JSON.parse(container.dataset.allocationData);

    if (allocationData && allocationData.length > 0) {
        // 총 가치 계산
        const totalValue = allocationData.reduce((sum, item) => sum + item.value, 0);
        
        // 차트 데이터 준비
        const labels = allocationData.map(item => item.symbol);
        const values = allocationData.map(item => item.value);
        
        // 색상 팔레트
        const colors = [
            '#0d6efd', '#6c757d', '#198754', '#dc3545', '#ffc107', 
            '#0dcaf0', '#6f42c1', '#fd7e14', '#20c997', '#6610f2'
        ];
        
        // 도넛 차트 생성
        const ctx = document.getElementById('allocationChart')?.getContext('2d');
        if (!ctx) return;
        
        window.ChartUtils.requestPlugins(['datalabels'], () => {
            Chart.register(ChartDataLabels);

            const allocationChart = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: labels,
                    datasets: [{
                        data: values,
                        backgroundColor: colors,
                        borderColor: '#343a40' // Dark theme background color for borders
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'right'
                        },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    const label = context.label || '';
                                    const value = context.parsed;
                                    const percentage = (value / totalValue * 100).toFixed(2);
                                    return ` ${label}: $${value.toFixed(2)} (${percentage}%)`;
                                }
                            }
                        },
                        datalabels: { // 도넛 차트에서는 라벨을 숨김
                            display: false
                        }
                    }
                }
            });
        });
        
        // 비중 테이블 생성
        const tableBody = document.getElementById('allocation-table-body');
        if (tableBody) {
            allocationData.forEach((item, index) => {
                const percentage = (item.value / totalValue * 100).toFixed(2);
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>
                        <span class="d-inline-block rounded-circle me-2" 
                              style="width: 12px; height: 12px; background-color: ${colors[index % colors.length]}; vertical-align: middle;"></span>
                        <strong>${item.symbol}</strong>
                    </td>
                    <td class="text-end">$${item.value.toFixed(2)}</td>
                    <td class="text-end">${percentage}%</td>
                `;
                tableBody.appendChild(row);
            });
        }
    }
});
