# 📄 static/js/dividend-analysis.js
// ✨ New File: 배당금 분석 페이지의 차트 렌더링 및 인터랙티브 로직
document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('dividendAnalysisContainer');
    if (!container) return;

    const taxRate = parseFloat(container.dataset.taxRate || '0.154');
    let isTaxApplied = false;

    // 1. 월별 배당금 차트
    const monthlyCtx = document.getElementById('monthlyDividendChart')?.getContext('2d');
    const monthlyData = JSON.parse(container.dataset.monthlyData || '{}');
    let monthlyChart;
    if (monthlyCtx && monthlyData.labels) {
        monthlyChart = createInteractiveMonthlyChart(monthlyCtx, monthlyData, taxRate);
    }
    
    // 2. 배당 비중 차트 (모달 내)
    const allocationModal = document.getElementById('allocationModal');
    if (allocationModal) {
        const allocationCtx = document.getElementById('dividendAllocationChart')?.getContext('2d');
        const allocationData = JSON.parse(container.dataset.dividendAllocationData || '[]');
        if (allocationCtx && allocationData.length > 0) {
             // 모달이 열릴 때 차트를 생성하여 렌더링 오류 방지
            allocationModal.addEventListener('shown.bs.modal', () => {
                createDonutChart(allocationCtx, allocationData, '종목별 연간 배당금 비중');
            }, { once: true }); // 한 번만 실행
        }
    }
    
    // 3. 세금 토글 스위치 로직
    const taxToggle = document.getElementById('taxToggleSwitch');
    const taxLabel = document.getElementById('taxToggleLabel');
    if (taxToggle) {
        taxToggle.addEventListener('change', (e) => {
            isTaxApplied = e.target.checked;
            taxLabel.textContent = isTaxApplied ? '세후' : '세전';

            // 모든 tax-value 클래스를 가진 요소들의 값을 업데이트
            document.querySelectorAll('.tax-value').forEach(el => {
                const preTaxValue = parseFloat(el.dataset.pretaxValue);
                const displayValue = isTaxApplied ? preTaxValue * (1 - taxRate) : preTaxValue;
                el.textContent = `$${displayValue.toFixed(2)}`;
            });

            // 월별 차트 데이터 업데이트
            if (monthlyChart) {
                const originalData = monthlyData.datasets[0].data;
                monthlyChart.data.datasets[0].data = originalData.map(val => 
                    isTaxApplied ? val * (1 - taxRate) : val
                );
                monthlyChart.update();
            }
        });
    }

    // 4. 월별 상세 정보 닫기 버튼
    document.getElementById('closeMonthlyDetail')?.addEventListener('click', () => {
        document.getElementById('monthlyDetail').classList.add('d-none');
    });
});

function createInteractiveMonthlyChart(ctx, data, taxRate) {
    const chart = new Chart(ctx, {
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
                hoverBackgroundColor: 'rgba(102, 126, 234, 1)',
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (c) => `배당금: $${c.parsed.y.toFixed(2)}`
                    }
                }
            },
            scales: {
                y: { display: false },
                x: { grid: { display: false } }
            },
            onClick: (e, elements) => {
                if (elements.length > 0) {
                    const monthIndex = elements[0].index;
                    const monthLabel = data.labels[monthIndex];
                    const detailData = data.detailed_data[monthIndex] || [];
                    
                    const detailContainer = document.getElementById('monthlyDetail');
                    const titleEl = document.getElementById('monthlyDetailTitle');
                    const contentEl = document.getElementById('monthlyDetailContent');

                    if (detailContainer && titleEl && contentEl) {
                        titleEl.textContent = `${monthLabel} 배당 상세 내역`;
                        contentEl.innerHTML = ''; // Clear previous content

                        if (detailData.length > 0) {
                            detailData.forEach(item => {
                                const isTaxApplied = document.getElementById('taxToggleSwitch').checked;
                                const amount = isTaxApplied ? item.amount * (1 - taxRate) : item.amount;
                                
                                const itemHtml = `
                                    <div class="list-group-item d-flex justify-content-between align-items-center">
                                        <div>
                                            <strong class="me-2">${item.symbol}</strong>
                                            <small class="text-muted">
                                                (예측 배당락일: ${item.ex_dividend_date})
                                            </small>
                                        </div>
                                        <span class="badge bg-success-subtle text-success-emphasis rounded-pill fs-6">
                                            $${amount.toFixed(2)}
                                        </span>
                                    </div>`;
                                contentEl.insertAdjacentHTML('beforeend', itemHtml);
                            });
                        } else {
                            contentEl.innerHTML = '<p class="text-muted p-3">해당 월의 배당 내역이 없습니다.</p>';
                        }
                        
                        detailContainer.classList.remove('d-none');
                    }
                }
            }
        }
    });
    return chart;
}


function createDonutChart(ctx, data, label) {
    const totalValue = data.reduce((sum, item) => sum + item.value, 0);
    const chartData = data.map(item => ({
        symbol: item.symbol,
        value: item.value,
    }));

    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: chartData.map(d => d.symbol),
            datasets: [{
                label: label,
                data: chartData.map(d => d.value),
                backgroundColor: Object.values(Chart.Colors.get(0, chartData.length)),
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'right' },
                tooltip: {
                    callbacks: {
                        label: (c) => {
                            const value = c.raw;
                            const percentage = ((value / totalValue) * 100).toFixed(2);
                            return ` ${c.label}: $${value.toFixed(2)} (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });
}
