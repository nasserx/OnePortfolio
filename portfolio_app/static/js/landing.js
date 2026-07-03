(function () {
    'use strict';

    const sampleData = {
        portfolios: [
            {
                key: 'stocks',
                name: 'Stocks',
                bookValue: 18000,
                capital: 20000,
                income: 1100,
                realizedPnl: 1700,
                return: '+16%',
            },
            {
                key: 'etfs',
                name: 'ETFs',
                bookValue: 14000,
                capital: 16000,
                income: 800,
                realizedPnl: 1200,
                return: '+14%',
            },
            {
                key: 'crypto',
                name: 'Crypto',
                bookValue: 10000,
                capital: 12000,
                income: 500,
                realizedPnl: 700,
                return: '+12%',
            },
        ],
        totals: {
            cash: 6000,
            income: 2400,
            realizedPnl: 3600,
        },
        charts: {
            bookValue: {
                canvasId: 'landingBookValueChart',
                legendId: 'landingBookValueLegend',
                centerLabel: 'Book Value',
                valueKey: 'bookValue',
            },
            capital: {
                canvasId: 'landingCapitalChart',
                legendId: 'landingCapitalLegend',
                centerLabel: 'Capital',
                valueKey: 'capital',
            },
        },
    };

    window.OnePortfolioLandingData = sampleData;

    function cssVar(name, fallback) {
        const scope = document.querySelector('.landing-page') || document.documentElement;
        const value = getComputedStyle(scope).getPropertyValue(name).trim();
        return value || fallback;
    }

    function chartNumber(name, fallback) {
        const value = parseFloat(cssVar(name, ''));
        return Number.isFinite(value) ? value : fallback;
    }

    const integerFormatter = new Intl.NumberFormat('en-US', {
        maximumFractionDigits: 0,
    });

    function formatLandingNumber(value) {
        return integerFormatter.format(Math.round(Number(value) || 0));
    }

    function formatSignedNumber(value) {
        const number = Number(value) || 0;
        return (number > 0 ? '+' : '') + formatLandingNumber(number);
    }

    function portfolioTotal(valueKey) {
        return sampleData.portfolios.reduce(function (sum, portfolio) {
            return sum + (Number(portfolio[valueKey]) || 0);
        }, 0);
    }

    function portfolioByKey(key) {
        return sampleData.portfolios.find(function (portfolio) {
            return portfolio.key === key;
        });
    }

    function prefersReducedMotion() {
        return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }

    function palette() {
        return [
            cssVar('--chart-allocation-1', '#6bb6d8'),
            cssVar('--chart-allocation-2', '#8f82c8'),
            cssVar('--chart-allocation-3', '#45b883'),
            cssVar('--chart-allocation-4', '#b884b7'),
            cssVar('--chart-allocation-5', '#5fa6ce'),
        ];
    }

    function buildChartData(config) {
        const values = sampleData.portfolios.map(function (portfolio) {
            return Number(portfolio[config.valueKey]) || 0;
        });
        const total = portfolioTotal(config.valueKey);
        const percentages = values.map(function (value) {
            return total > 0 ? (value / total) * 100 : 0;
        });

        return {
            labels: sampleData.portfolios.map(function (portfolio) {
                return portfolio.name;
            }),
            values,
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

    function renderMetrics() {
        const metrics = {
            bookValue: formatLandingNumber(portfolioTotal('bookValue')),
            totalCapital: formatLandingNumber(portfolioTotal('capital')),
            totalCash: formatLandingNumber(sampleData.totals.cash),
            totalIncome: formatLandingNumber(sampleData.totals.income),
            realizedPnl: formatSignedNumber(sampleData.totals.realizedPnl),
        };

        document.querySelectorAll('[data-landing-metric]').forEach(function (element) {
            const key = element.getAttribute('data-landing-metric');
            element.textContent = metrics[key] || '';
        });
    }

    function renderTableValues() {
        document.querySelectorAll('[data-landing-row][data-landing-field]').forEach(function (element) {
            const portfolio = portfolioByKey(element.getAttribute('data-landing-row'));
            const field = element.getAttribute('data-landing-field');

            if (!portfolio || !Object.prototype.hasOwnProperty.call(portfolio, field)) {
                element.textContent = '';
                return;
            }

            if (field === 'return') {
                element.textContent = portfolio[field];
                return;
            }

            if (field === 'income' || field === 'realizedPnl') {
                element.textContent = formatSignedNumber(portfolio[field]);
                return;
            }

            element.textContent = formatLandingNumber(portfolio[field]);
        });
    }

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
            value.textContent = formatLandingNumber(data.values[index]) + ' (' + data.percentages[index].toFixed(1) + '%)';

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
                                return ' ' + ctx.label + ': ' + formatLandingNumber(value) + ' (' + pct.toFixed(1) + '%)';
                            },
                        },
                    },
                    landingCenterText: {
                        label: config.centerLabel,
                        value: formatLandingNumber(data.total),
                    },
                },
            },
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        renderMetrics();
        renderTableValues();
        renderDoughnut(sampleData.charts.bookValue);
        renderDoughnut(sampleData.charts.capital);
    });
}());
