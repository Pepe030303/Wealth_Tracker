# 📄 static/js/charts.js
// ✨ New File: 여러 차트에서 공통으로 사용하는 유틸리티 함수

// Chart.js에 전역 색상 팔레트 유틸리티를 추가합니다.
// 사용법: Chart.Colors.get(index) 또는 Chart.Colors.get(index, count)
(function(Chart) {
    const COLORS = [
        '#4dc9f6', '#f67019', '#f53794', '#537bc4', '#acc236', '#166a8f',
        '#00a950', '#58595b', '#8549ba', '#ffc107', '#28a745', '#dc3545'
    ];

    Chart.Colors = {
        _colors: COLORS,
        get: function(index, count = 1) {
            if (count > 1) {
                const colorSet = [];
                for (let i = 0; i < count; i++) {
                    colorSet.push(this._colors[(index + i) % this._colors.length]);
                }
                return colorSet;
            }
            return this._colors[index % this._colors.length];
        }
    };
}(this.Chart));
