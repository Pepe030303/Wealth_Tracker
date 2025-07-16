// 📄 static/js/dividend-analysis.js
// 🛠️ 신규 파일: dividends.html의 인라인 스크립트를 분리

document.addEventListener('DOMContentLoaded', function () {
    // 🛠️ 버그 수정: 플러그인 등록은 base.html에서 전역으로 처리하므로 여기서 제거
    // Chart.register(ChartDataLabels);

    const analysisContainer = document.getElementById('dividendAnalysisContainer');
    if (!analysisContainer) return;

    // 데이터 속성에서 데이터 로드
    const originalAllocationData = JSON.parse(analysisContainer.dataset.allocationData);
    const originalMonthlyData = JSON.parse(analysisContainer.dataset.monthlyData);
    const originalDetailedData = originalMonthlyData.detailed_data || {};
    const TAX_RATE = parseFloat(analysisContainer.dataset.taxRate);

    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) { return new bootstrap.Tooltip(tooltipTriggerEl); });
    
    const taxToggle = document.getElementById('taxToggleSwitch');
    const taxToggleLabel = document.getElementById('taxToggleLabel');
    
    let allocationChart;
    // 월별 배당 차트 생성 (공통 모듈 사용)
    const monthlyChart = createMonthlyDividendChart('monthlyDividendChart', originalMonthlyData, (index) => {
        renderMonthlyDetails(index);
    });

    function updateDisplayByTaxMode(isPostTax) {
        const factor = isPostTax ? (1 - TAX_RATE) : 1;
        document.querySelectorAll('.tax-value').forEach(el => {
            el.textContent = `$${(parseFloat(el.dataset.pretaxValue) * factor).toFixed(2)}`;
        });
        if (allocationChart) {
            allocationChart.data.datasets[0].data = originalAllocationData.map(item => item.value * factor);
            allocationChart.update();
        }
        if (monthlyChart) {
            const originalData = originalMonthlyData.datasets[0].data;
            monthlyChart.data.datasets[0].data = originalData.map(val => val * factor);
            monthlyChart.update();
        }
        taxToggleLabel.textContent = isPostTax ? '세후' : '세전';
    }

    const savedTaxMode = localStorage.getItem('taxMode');
    if (savedTaxMode === 'post-tax') taxToggle.checked = true;
    updateDisplayByTaxMode(taxToggle.checked);

    taxToggle.addEventListener('change', () => {
        const isPostTax = taxToggle.checked;
        localStorage.setItem('taxMode', isPostTax ? 'post-tax' : 'pre-tax');
        updateDisplayByTaxMode(isPostTax);
        const monthlyDetailContainer = document.getElementById('monthlyDetail');
        if (!monthlyDetailContainer.classList.contains('d-none')) {
            const currentIndex = parseInt(monthlyDetailContainer.dataset.monthIndex);
            if (!isNaN(currentIndex)) renderMonthlyDetails(currentIndex);
        }
    });

    const allocationModal = document.getElementById('allocationModal');
    allocationModal.addEventListener('shown.bs.modal', () => {
        if (allocationChart) {
            updateDisplayByTaxMode(taxToggle.checked); // 모달이 다시 열릴 때 세금 모드에 맞춰 데이터 업데이트
            return;
        }
        const allocationCtx = document.getElementById('dividendAllocationChart')?.getContext('2d');
        if (allocationCtx && originalAllocationData && originalAllocationData.length > 0) {
            allocationChart = new Chart(allocationCtx, {
                type: 'doughnut', data: { labels: originalAllocationData.map(i => i.symbol), datasets: [{ data: originalAllocationData.map(i => i.value), backgroundColor: ['#0d6efd', '#6c757d', '#198754', '#dc3545', '#ffc107', '#0dcaf0', '#6f42c1', '#fd7e14', '#20c997', '#6610f2'], borderColor: '#343a40' }] },
                options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right' }, datalabels: { display: false }, tooltip: { callbacks: { label: function(c) { const total = c.chart.data.datasets[0].data.reduce((s, v) => s + v, 0); return ` ${c.label}: $${c.parsed.toFixed(2)} (${(c.parsed / total * 100).toFixed(2)}%)`; } } } } }
            });
            updateDisplayByTaxMode(taxToggle.checked);
        }
    });

    const monthlyDetailContainer = document.getElementById('monthlyDetail');
    const monthlyDetailTitle = document.getElementById('monthlyDetailTitle');
    const monthlyDetailContent = document.getElementById('monthlyDetailContent');
    const closeButton = document.getElementById('closeMonthlyDetail');
    
    function renderMonthlyDetails(index) {
        monthlyDetailContainer.dataset.monthIndex = index;
        const factor = taxToggle.checked ? (1 - TAX_RATE) : 1;
        let dataForMonth = originalDetailedData[index] || [];
        if (dataForMonth.length === 0) { monthlyDetailContainer.classList.add('d-none'); return; }
        
        // 클릭된 막대 강조
        if (monthlyChart) {
            const activeColor = 'rgba(25, 135, 84, 1)';
            const defaultColor = 'rgba(25, 135, 84, 0.6)';
            monthlyChart.data.datasets[0].backgroundColor = monthlyChart.data.labels.map((_, i) => i === index ? activeColor : defaultColor);
            monthlyChart.update('none'); // 애니메이션 없이 업데이트
        }

        dataForMonth.sort((a, b) => new Date(a.ex_dividend_date) - new Date(b.ex_dividend_date));
        const totalForMonth = dataForMonth.reduce((s, i) => s + i.amount, 0) * factor;
        monthlyDetailTitle.innerHTML = `${originalMonthlyData.labels[index]} 배당 상세 <span class="text-success fw-bold ms-3">$${totalForMonth.toFixed(2)}</span>`;
        monthlyDetailContent.innerHTML = '';
        dataForMonth.forEach(item => {
            const logoUrl = item.profile?.logo_url || `https://via.placeholder.com/32/cccccc/FFFFFF?text=${item.symbol[0]}`;
            const exDay = new Date(item.ex_dividend_date).getDate();
            const itemHtml = `<div class="list-group-item d-flex align-items-center p-2 bg-transparent"><span class="badge bg-secondary-subtle text-secondary-emphasis rounded-pill me-3 p-2" style="width: 2.5rem; height: 2.5rem; display: flex; align-items-center; justify-content: center; font-size: 1rem;">${exDay}</span><img src="${logoUrl}" class="stock-logo me-3" alt="${item.symbol} logo" loading="lazy" onerror="this.onerror=null; this.src='https://via.placeholder.com/32/cccccc/FFFFFF?text=${item.symbol[0]}';"><div class="flex-grow-1"><div class="d-flex justify-content-between"><strong class="mb-0">${item.symbol}</strong><strong class="text-success fs-5 ms-3">$${(item.amount*factor).toFixed(2)}</strong></div><div class="d-flex justify-content-between"><small class="company-name text-muted">${item.profile?.name || ''}</small><small class="text-muted text-nowrap">${item.quantity.toFixed(2)}주 @ $${(item.dps_per_payout*factor).toFixed(4)}</small></div></div></div>`;
            monthlyDetailContent.innerHTML += itemHtml;
        });
        monthlyDetailContainer.classList.remove('d-none');
        monthlyDetailContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    closeButton.addEventListener('click', () => { 
        monthlyDetailContainer.classList.add('d-none');
        // 강조 효과 제거
        if (monthlyChart) {
            monthlyChart.data.datasets[0].backgroundColor = 'rgba(25, 135, 84, 0.6)';
            monthlyChart.update('none');
        }
    });

    let activeDetailChart = null;
    let activeDetailSymbol = null;
    
    document.querySelectorAll('.stock-card-interactive').forEach(card => {
        card.addEventListener('click', (e) => {
            const symbol = card.dataset.symbol;
            const historyData = JSON.parse(card.dataset.history);
            const detailContainer = document.getElementById(`detail-${symbol}`);

            if (activeDetailSymbol && activeDetailSymbol !== symbol) {
                const lastContainer = document.getElementById(`detail-${activeDetailSymbol}`);
                if (lastContainer) new bootstrap.Collapse(lastContainer, {toggle: false}).hide();
                if (activeDetailChart) activeDetailChart.destroy();
            }

            const bsCollapse = new bootstrap.Collapse(detailContainer, { toggle: false });
            bsCollapse.toggle();

            if (detailContainer.classList.contains('show')) {
                activeDetailSymbol = symbol;
                renderStockDetailChart(detailContainer, symbol, historyData);
            } else {
                activeDetailSymbol = null;
                if(activeDetailChart) activeDetailChart.destroy();
            }
        });
    });

    function renderStockDetailChart(container, symbol, history) {
        if (!history || history.length === 0) {
            container.innerHTML = `<div class="p-3 text-center text-muted">배당 이력 데이터가 없습니다.</div>`;
            return;
        }

        const df = {};
        history.forEach(item => {
            const year = new Date(item.date).getFullYear();
            df[year] = (df[year] || 0) + item.amount;
        });

        const last5YearsData = Object.entries(df).sort((a, b) => b[0] - a[0]).slice(0, 5).reverse();
        
        const labels = last5YearsData.map(d => d[0]);
        const data = last5YearsData.map(d => d[1]);

        container.innerHTML = `<div class="card card-body"><div class="chart-container" style="height: 150px;"><canvas id="chart-${symbol}"></canvas></div></div>`;
        const ctx = document.getElementById(`chart-${symbol}`).getContext('2d');
        
        activeDetailChart = new Chart(ctx, {
            type: 'bar',
            data: { labels: labels, datasets: [{ label: `${symbol} 연간 배당금 (보정)`, data: data, backgroundColor: 'rgba(13, 110, 253, 0.6)' }] },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, datalabels: { display: false }, tooltip: { callbacks: { label: (c) => `총액: $${c.parsed.y.toFixed(4)}` } } }, scales: { y: { beginAtZero: true, ticks: { callback: (v) => `$${v.toFixed(2)}` } } } }
        });
    }
});
