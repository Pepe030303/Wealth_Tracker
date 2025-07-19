# 📄 static/js/dividend-analysis.js
// ✨ New File: 배당 분석 페이지의 차트 및 상호작용을 처리하는 스크립트

document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('dividendAnalysisContainer');
    if (!container) return;

    try {
        const allocationData = JSON.parse(container.dataset.allocationData || '[]');
        const monthlyData = JSON.parse(container.dataset.monthlyData || '{}');
        const taxRate = parseFloat(container.dataset.taxRate);

        // 월별 배당금 차트
        const monthlyCtx = document.getElementById('monthlyDividendChart').getContext('2d');
        window.createMonthlyDividendChart(monthlyCtx, monthlyData, (event, elements) => {
            if (elements.length > 0) {
                const monthIndex = elements[0].index;
                displayMonthlyDetail(monthIndex, monthlyData.detailed_data[monthIndex], monthlyData.labels[monthIndex]);
            }
        });

        // 배당금 비중 차트 (모달 내부)
        const allocationModal = document.getElementById('allocationModal');
        allocationModal.addEventListener('shown.bs.modal', () => {
            const allocationCtx = document.getElementById('dividendAllocationChart').getContext('2d');
            // 차트가 이미 그려져 있다면 다시 그리지 않음
            if (!Chart.getChart(allocationCtx)) { 
                window.createDividendAllocationChart(allocationCtx, allocationData);
            }
        }, { once: true }); // 이벤트 리스너는 한 번만 실행

        // 세금 토글 스위치 이벤트 처리
        const taxToggle = document.getElementById('taxToggleSwitch');
        const taxLabel = document.getElementById('taxToggleLabel');
        taxToggle.addEventListener('change', (event) => {
            const isPostTax = event.target.checked;
            taxLabel.textContent = isPostTax ? '세후' : '세전';
            document.querySelectorAll('.tax-value').forEach(el => {
                const pretaxValue = parseFloat(el.dataset.pretaxValue);
                const value = isPostTax ? pretaxValue * (1 - taxRate) : pretaxValue;
                el.textContent = `$${value.toFixed(2)}`;
            });
        });

        // 월별 상세 정보 닫기 버튼
        document.getElementById('closeMonthlyDetail').addEventListener('click', () => {
            document.getElementById('monthlyDetail').classList.add('d-none');
        });

    } catch (e) {
        console.error('Error rendering dividend analysis charts:', e);
    }
});

function displayMonthlyDetail(monthIndex, detailData, monthLabel) {
    const detailContainer = document.getElementById('monthlyDetail');
    const titleEl = document.getElementById('monthlyDetailTitle');
    const contentEl = document.getElementById('monthlyDetailContent');

    titleEl.textContent = `${monthLabel} 상세 배당 내역`;
    contentEl.innerHTML = ''; // 기존 내용 초기화

    if (detailData && detailData.length > 0) {
        detailData.forEach(item => {
            const pretaxAmount = item.amount;
            const isPostTax = document.getElementById('taxToggleSwitch').checked;
            const taxRate = parseFloat(document.getElementById('dividendAnalysisContainer').dataset.taxRate);
            const displayAmount = isPostTax ? pretaxAmount * (1 - taxRate) : pretaxAmount;
            
            const itemHtml = `
                <div class="list-group-item d-flex justify-content-between align-items-center">
                    <div>
                        <strong>${item.symbol}</strong>
                        <small class="text-muted d-block">
                            ${item.quantity}주 x $${item.dps_per_payout.toFixed(4)}
                            (배당락일: ${item.ex_dividend_date})
                        </small>
                    </div>
                    <strong class="text-success tax-value" data-pretax-value="${pretaxAmount}">
                        $${displayAmount.toFixed(2)}
                    </strong>
                </div>`;
            contentEl.innerHTML += itemHtml;
        });
    } else {
        contentEl.innerHTML = `<p class="text-muted text-center p-3">해당 월의 배당 내역이 없습니다.</p>`;
    }
    detailContainer.classList.remove('d-none');
}
