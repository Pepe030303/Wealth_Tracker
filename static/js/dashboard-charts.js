# 📄 static/js/dashboard-charts.js
// ✨ New File: 대시보드 페이지의 차트를 초기화하는 스크립트

document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('dashboardPageContainer');
    if (!container) return;

    try {
        const monthlyData = JSON.parse(container.dataset.monthlyData || '{}');
        const sectorData = JSON.parse(container.dataset.sectorData || '[]');

        // 월별 배당금 차트
        if (monthlyData.labels) {
            const monthlyCtx = document.getElementById('monthlyDividendChart').getContext('2d');
            window.createMonthlyDividendChart(monthlyCtx, monthlyData, (event, elements) => {
                 if (elements.length > 0) {
                     window.location.href = '/dividends'; // 클릭 시 배당 분석 페이지로 이동
                 }
            });
        }

        // 섹터 비중 차트
        if (sectorData.length > 0) {
            const sectorCtx = document.getElementById('sectorAllocationChart').getContext('2d');
            window.createSectorAllocationChart(sectorCtx, sectorData);
        }
    } catch (e) {
        console.error('Error rendering dashboard charts:', e);
    }
});
