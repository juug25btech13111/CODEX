const chartConfig = {
    // Colors matching our Tailwind theme with vibrant gradient-like values
    colors: {
        positive: '#10b981', // Emerald-500
        negative: '#f43f5e', // Rose-500
        neutral: '#8b5cf6',  // Violet-500
        primary: '#3b82f6',  // Blue-500
        purple: '#a855f7',   // Purple-500
        bgPositive: 'rgba(16, 185, 129, 0.15)',
        bgNegative: 'rgba(244, 63, 94, 0.15)',
        bgNeutral: 'rgba(139, 92, 246, 0.15)',
        bgPrimary: 'rgba(59, 130, 246, 0.15)',
    },
    textColor: function() {
        return document.documentElement.classList.contains('dark') ? '#e5e7eb' : '#374151';
    },
    gridColor: function() {
        return document.documentElement.classList.contains('dark') ? '#374151' : '#e5e7eb';
    }
};

function renderSentimentPieChart(ctxId, data) {
    const ctx = document.getElementById(ctxId);
    if (!ctx) return;

    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Positive', 'Negative', 'Neutral'],
            datasets: [{
                data: [data.positive, data.negative, data.neutral],
                backgroundColor: [
                    chartConfig.colors.positive,
                    chartConfig.colors.negative,
                    chartConfig.colors.neutral
                ],
                borderWidth: 0,
                hoverOffset: 12
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: {
                padding: 10
            },
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { 
                        color: chartConfig.textColor(),
                        padding: 20,
                        usePointStyle: true,
                        pointStyle: 'circle'
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(15, 23, 42, 0.9)',
                    titleColor: '#fff',
                    bodyColor: '#cbd5e1',
                    borderColor: 'rgba(255, 255, 255, 0.1)',
                    borderWidth: 1,
                    padding: 12,
                    displayColors: true,
                    boxPadding: 6
                }
            },
            cutout: '75%',
            animation: { animateScale: true, animateRotate: true, duration: 1500, easing: 'easeOutQuart' }
        }
    });
}

function renderDepartmentBarChart(ctxId, labels, data) {
    const ctx = document.getElementById(ctxId);
    if (!ctx) return;
    
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Feedback Count',
                data: data,
                backgroundColor: chartConfig.colors.bgPrimary,
                borderColor: chartConfig.colors.primary,
                borderWidth: 2,
                borderRadius: 6,
                hoverBackgroundColor: chartConfig.colors.primary,
                hoverBorderColor: '#60a5fa'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: {
                padding: { top: 10, right: 10, bottom: 0, left: 0 }
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(15, 23, 42, 0.9)',
                    titleColor: '#fff',
                    bodyColor: '#cbd5e1',
                    borderColor: 'rgba(255, 255, 255, 0.1)',
                    borderWidth: 1,
                    padding: 12,
                    displayColors: false,
                    cornerRadius: 8
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { color: chartConfig.textColor(), precision: 0, padding: 10 },
                    grid: { color: chartConfig.gridColor(), drawBorder: false, borderDash: [5, 5] },
                    border: { display: false }
                },
                x: {
                    ticks: { color: chartConfig.textColor(), padding: 10 },
                    grid: { display: false },
                    border: { display: false }
                }
            },
            animation: {
                duration: 1200,
                easing: 'easeOutQuart'
            }
        }
    });
    });
}
// Re-render charts on theme change to update text colors
document.getElementById('theme-toggle')?.addEventListener('click', () => {
    // A quick hack is just to reload the page or we could store chart instances and update them.
    // For simplicity, we delay and let the CSS transition finish, though proper way is updating chart config.
    setTimeout(() => {
        window.dispatchEvent(new Event('resize'));
        // If we want actual color updates without reload, we need to loop Chart.instances
        for (let id in Chart.instances) {
            let chart = Chart.instances[id];
            
            // Update Pie border color
            if (chart.config.type === 'doughnut') {
                 chart.data.datasets[0].borderColor = document.documentElement.classList.contains('dark') ? '#1f2937' : '#ffffff';
            }
            
            // Update texts
            if (chart.options.plugins?.legend?.labels) {
                chart.options.plugins.legend.labels.color = chartConfig.textColor();
            }
            if (chart.options.scales?.y?.ticks) {
                chart.options.scales.y.ticks.color = chartConfig.textColor();
                chart.options.scales.x.ticks.color = chartConfig.textColor();
                chart.options.scales.y.grid.color = chartConfig.gridColor();
            }
            chart.update();
        }
    }, 150);
});
