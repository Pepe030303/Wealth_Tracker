// 전역 JavaScript 함수들

// 숫자 포맷팅
function formatCurrency(value) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 2
    }).format(value);
}

function formatPercent(value) {
    return new Intl.NumberFormat('en-US', {
        style: 'percent',
        minimumFractionDigits: 2
    }).format(value / 100);
}

// 색상 헬퍼
function getColorForValue(value) {
    return value >= 0 ? 'text-success' : 'text-danger';
}

// 토스트 알림
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toast-container') || createToastContainer();
    
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-bg-${type} border-0`;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');
    
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;
    
    toastContainer.appendChild(toast);
    
    const bsToast = new bootstrap.Toast(toast);
    bsToast.show();
    
    // 토스트가 숨겨진 후 DOM에서 제거
    toast.addEventListener('hidden.bs.toast', function() {
        toast.remove();
    });
}

function createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'toast-container position-fixed top-0 end-0 p-3';
    document.body.appendChild(container);
    return container;
}

// 로딩 스피너
function showLoading(element) {
    const spinner = document.createElement('div');
    spinner.className = 'spinner-border spinner-border-sm me-2';
    spinner.setAttribute('role', 'status');
    
    element.disabled = true;
    element.insertBefore(spinner, element.firstChild);
}

function hideLoading(element) {
    const spinner = element.querySelector('.spinner-border');
    if (spinner) {
        spinner.remove();
    }
    element.disabled = false;
}

// 폼 검증
function validateForm(form) {
    const inputs = form.querySelectorAll('input[required]');
    let isValid = true;
    
    inputs.forEach(input => {
        if (!input.value.trim()) {
            input.classList.add('is-invalid');
            isValid = false;
        } else {
            input.classList.remove('is-invalid');
        }
    });
    
    return isValid;
}

// 확인 대화상자
function confirmAction(message, callback) {
    if (confirm(message)) {
        callback();
    }
}

// 페이지 로드 시 초기화
document.addEventListener('DOMContentLoaded', function() {
    // 모든 폼에 기본 검증 추가
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            if (!validateForm(form)) {
                e.preventDefault();
                showToast('모든 필수 필드를 입력해주세요.', 'warning');
            }
        });
    });
    
    // 숫자 입력 필드에 포맷팅 추가
    const numberInputs = document.querySelectorAll('input[type="number"]');
    numberInputs.forEach(input => {
        input.addEventListener('blur', function() {
            if (this.value && !isNaN(this.value)) {
                this.value = parseFloat(this.value).toFixed(2);
            }
        });
    });
    
    // 툴팁 초기화
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    const tooltipList = [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl));
});

// 실시간 업데이트 관련 함수
let refreshInterval;

function startAutoRefresh(intervalMs = 5 * 60 * 1000) {
    if (refreshInterval) {
        clearInterval(refreshInterval);
    }
    
    refreshInterval = setInterval(function() {
        if (typeof refreshPrices === 'function') {
            refreshPrices();
        }
    }, intervalMs);
}

function stopAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
    }
}

// 페이지 가시성 API를 사용한 자동 업데이트 관리
document.addEventListener('visibilitychange', function() {
    if (document.visibilityState === 'visible') {
        startAutoRefresh();
    } else {
        stopAutoRefresh();
    }
});

// 에러 핸들링
window.addEventListener('error', function(e) {
    console.error('JavaScript Error:', e.error);
    showToast('예상치 못한 오류가 발생했습니다.', 'danger');
});

// 네트워크 상태 모니터링
window.addEventListener('online', function() {
    showToast('네트워크 연결이 복구되었습니다.', 'success');
});

window.addEventListener('offline', function() {
    showToast('네트워크 연결이 끊어졌습니다.', 'warning');
});
