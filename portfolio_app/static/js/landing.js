(function () {
    'use strict';

    const sampleData = {
        portfolios: ['Stocks', 'ETFs', 'Crypto', 'Gold', 'Bonds'],
        charts: {
            bookValue: {
                canvasId: 'landingBookValueChart',
                legendId: 'landingBookValueLegend',
                centerLabel: 'Book Value',
                values: [5200, 3600, 2400, 1700, 1100],
                total: 14000,
            },
            capital: {
                canvasId: 'landingCapitalChart',
                legendId: 'landingCapitalLegend',
                centerLabel: 'Capital',
                values: [5600, 3900, 2600, 1900, 1300],
                total: 15300,
            },
        },
    };

    window.OnePortfolioLandingData = sampleData;

    function cssVar(name, fallback) {
        const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
        return value || fallback;
    }

    function chartNumber(name, fallback) {
        const value = parseFloat(cssVar(name, ''));
        return Number.isFinite(value) ? value : fallback;
    }

    const moneyFormatter = new Intl.NumberFormat('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });

    function formatMoney(value) {
        return moneyFormatter.format(Number(value) || 0);
    }

    function formatCompact(value) {
        const number = Number(value) || 0;
        if (Math.abs(number) >= 1000000) return (number / 1000000).toFixed(2) + 'M';
        if (Math.abs(number) >= 1000) return (number / 1000).toFixed(1) + 'K';
        return formatMoney(number);
    }

    function prefersReducedMotion() {
        return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }

    function palette() {
        return [
            cssVar('--chart-allocation-1', '#7dd3fc'),
            cssVar('--chart-allocation-2', '#a78bfa'),
            cssVar('--chart-allocation-3', '#34d399'),
            cssVar('--chart-allocation-4', '#f0abfc'),
            cssVar('--chart-allocation-5', '#38bdf8'),
        ];
    }

    function buildChartData(config) {
        const total = Number(config.total) || 0;
        const percentages = config.values.map(function (value) {
            return total > 0 ? (Number(value) / total) * 100 : 0;
        });

        return {
            labels: sampleData.portfolios,
            values: config.values,
            total,
            percentages,
        };
    }

    const centerTextPlugin = {
        id: 'landingCenterText',
        afterDraw: function (chart) {
            if (chart.config.type !== 'doughnut') return;

            const opts = chart.config.options.plugins.landingCenterText;
            if (!opts || !opts.value) return;

            const arc = chart.getDatasetMeta(0).data[0];
            if (!arc) return;

            const ctx = chart.ctx;
            ctx.save();
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillStyle = cssVar('--text-primary', '#e8eaed');
            ctx.globalAlpha = 0.65;
            ctx.font = '400 ' + chartNumber('--font-size-chart-center-label', 10) + 'px Inter, sans-serif';
            ctx.fillText(opts.label, arc.x, arc.y - 10);
            ctx.globalAlpha = 1;
            ctx.font = '500 ' + chartNumber('--font-size-chart-center-value', 13) + 'px Inter, sans-serif';
            ctx.fillText(opts.value, arc.x, arc.y + 9);
            ctx.restore();
        },
    };

    function renderLegend(legend, data) {
        const fragment = document.createDocumentFragment();

        data.labels.forEach(function (name, index) {
            const item = document.createElement('li');

            const swatch = document.createElement('span');
            swatch.className = 'swatch swatch-' + ((index % 5) + 1);
            swatch.setAttribute('aria-hidden', 'true');

            const label = document.createElement('span');
            label.className = 'name';
            label.textContent = name;

            const value = document.createElement('span');
            value.className = 'value';
            value.textContent = formatMoney(data.values[index]) + ' (' + data.percentages[index].toFixed(1) + '%)';

            item.append(swatch, label, value);
            fragment.appendChild(item);
        });

        legend.replaceChildren(fragment);
    }

    function renderDoughnut(config) {
        const canvas = document.getElementById(config.canvasId);
        const legend = document.getElementById(config.legendId);

        if (!canvas || !legend || !window.Chart) return;

        const data = buildChartData(config);
        const colors = palette();
        renderLegend(legend, data);

        window.Chart.defaults.color = cssVar('--text-secondary', '#bdc1c6');

        new window.Chart(canvas, {
            type: 'doughnut',
            data: {
                labels: data.labels,
                datasets: [{
                    data: data.percentages,
                    backgroundColor: colors,
                    borderColor: cssVar('--surface-2', '#111113'),
                    borderWidth: 2,
                    hoverOffset: 3,
                }],
            },
            plugins: [centerTextPlugin],
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '64%',
                animation: {
                    duration: prefersReducedMotion() ? 0 : 420,
                },
                layout: {
                    padding: 6,
                },
                plugins: {
                    legend: {
                        display: false,
                    },
                    tooltip: {
                        callbacks: {
                            label: function (ctx) {
                                const value = data.values[ctx.dataIndex] || 0;
                                const pct = data.percentages[ctx.dataIndex] || 0;
                                return ' ' + ctx.label + ': ' + formatMoney(value) + ' (' + pct.toFixed(1) + '%)';
                            },
                        },
                    },
                    landingCenterText: {
                        label: config.centerLabel,
                        value: formatCompact(data.total),
                    },
                },
            },
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        renderDoughnut(sampleData.charts.bookValue);
        renderDoughnut(sampleData.charts.capital);
    });
}());
