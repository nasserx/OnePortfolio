(function() {
    function cssVar(name, fallback) {
        var value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
        return value || fallback;
    }

    function textColor() {
        return cssVar('--text-1', '#e8eaed');
    }

    function otherColor() {
        return cssVar('--chart-allocation-other', '#64748b');
    }

    function chartNumber(name, fallback) {
        var value = parseFloat(cssVar(name, ''));
        return Number.isFinite(value) ? value : fallback;
    }

    function displayNumber(value) {
        var number = Number(value) || 0;
        var absValue = Math.abs(number);
        if (absValue >= 1000000) {
            return (number / 1000000).toFixed(2) + 'M';
        }
        return number.toLocaleString('en-US', {
            minimumFractionDigits: 0,
            maximumFractionDigits: 2
        });
    }

    function truncate(name, maxLength) {
        return name && name.length > maxLength ? name.slice(0, maxLength) + '...' : (name || '');
    }

    function prefersReducedMotion() {
        return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }

    var allocationPalette = [
        cssVar('--chart-allocation-1', '#7dd3fc'),
        cssVar('--chart-allocation-2', '#a78bfa'),
        cssVar('--chart-allocation-3', '#34d399'),
        cssVar('--chart-allocation-4', '#f0abfc'),
        cssVar('--chart-allocation-5', '#38bdf8'),
        cssVar('--chart-allocation-6', '#c4b5fd'),
        cssVar('--chart-allocation-7', '#5eead4')
    ];

    function colorFor(name, colorMap) {
        if (name === 'Other Portfolios') return otherColor();
        var index = colorMap[name];
        if (!Number.isFinite(index)) index = 0;
        return allocationPalette[index % allocationPalette.length];
    }

    function swatchClass(name, colorMap) {
        if (name === 'Other Portfolios') return 'swatch swatch-other';
        var index = colorMap[name];
        if (!Number.isFinite(index)) index = 0;
        return 'swatch swatch-' + ((index % allocationPalette.length) + 1);
    }

    function hasMeaningfulData(data) {
        return data && Array.isArray(data.categories) && data.categories.length &&
            Array.isArray(data.allocations) && data.allocations.some(function(value) {
                return Number(value) > 0;
            });
    }

    function buildColorMap(chartData) {
        var colorMap = {};
        var next = 0;
        ['book_value_chart', 'capital_chart'].forEach(function(key) {
            var data = chartData[key] || {};
            (data.categories || []).forEach(function(name) {
                if (name !== 'Other Portfolios' && colorMap[name] === undefined) {
                    colorMap[name] = next;
                    next += 1;
                }
            });
        });
        return colorMap;
    }

    var centerTextPlugin = {
        id: 'centerText',
        afterDraw: function(chart) {
            if (chart.config.type !== 'doughnut') return;
            var opts = chart.config.options.plugins.centerText;
            if (!opts || !opts.value) return;
            var arc = chart.getDatasetMeta(0).data[0];
            if (!arc) return;
            var ctx = chart.ctx;
            ctx.save();
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillStyle = textColor();
            ctx.globalAlpha = 0.65;
            ctx.font = '400 ' + chartNumber('--font-size-chart-center-label', 10) + 'px Inter, sans-serif';
            ctx.fillText(opts.label, arc.x, arc.y - 11);
            ctx.globalAlpha = 1;
            ctx.font = '500 ' + chartNumber('--font-size-chart-center-value', 13) + 'px Inter, sans-serif';
            ctx.fillText(opts.value, arc.x, arc.y + 9);
            ctx.restore();
        }
    };

    function renderDoughnut(config, colorMap) {
        var canvas = document.getElementById(config.canvasId);
        var legend = document.getElementById(config.legendId);
        var card = canvas ? canvas.closest('[data-doughnut-card]') : null;
        var emptyState = card ? card.querySelector('[data-empty-state]') : null;
        var data = config.data || {};

        if (!canvas || !legend) return;

        if (!hasMeaningfulData(data)) {
            canvas.hidden = true;
            legend.hidden = true;
            if (emptyState) emptyState.hidden = false;
            return;
        }

        var chart = new Chart(canvas, {
            type: 'doughnut',
            data: {
                labels: data.categories,
                datasets: [{
                    data: data.allocations,
                    backgroundColor: data.categories.map(function(name) {
                        return colorFor(name, colorMap);
                    }),
                    borderColor: cssVar('--surface-card', '#111113'),
                    borderWidth: 2,
                    hoverOffset: 5
                }]
            },
            plugins: [centerTextPlugin],
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '64%',
                animation: prefersReducedMotion() ? false : { duration: 220 },
                layout: { padding: 8 },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function(ctx) {
                                var pct = Number(ctx.parsed);
                                var safePct = Number.isFinite(pct) ? pct.toFixed(1) : '0.0';
                                return ' ' + ctx.label + ': ' + safePct + '%';
                            }
                        }
                    },
                    centerText: {
                        label: config.centerLabel,
                        value: displayNumber(data.total || 0)
                    }
                }
            }
        });

        var frag = document.createDocumentFragment();
        data.categories.forEach(function(name, index) {
            var li = document.createElement('li');
            li.title = name;
            li.dataset.idx = String(index);
            li.setAttribute('role', 'button');
            li.setAttribute('tabindex', '0');
            li.setAttribute('aria-pressed', 'false');

            var swatch = document.createElement('span');
            swatch.className = swatchClass(name, colorMap);

            var nameEl = document.createElement('span');
            nameEl.className = 'name';
            nameEl.textContent = truncate(name, 22);

            var valueEl = document.createElement('span');
            valueEl.className = 'value';
            valueEl.textContent = displayNumber((data.values || [])[index]);

            var pctEl = document.createElement('span');
            pctEl.className = 'pct';
            var pct = Number(data.allocations[index]);
            pctEl.textContent = (Number.isFinite(pct) ? pct.toFixed(1) : '0.0') + '%';

            li.append(swatch, nameEl, valueEl, pctEl);
            frag.appendChild(li);
        });
        legend.appendChild(frag);

        function toggleLegendRow(row) {
            var index = parseInt(row.dataset.idx, 10);
            if (Number.isNaN(index)) return;
            var hidden = !row.classList.contains('is-hidden');
            row.classList.toggle('is-hidden', hidden);
            row.setAttribute('aria-pressed', hidden ? 'true' : 'false');
            chart.toggleDataVisibility(index);
            chart.update();
        }

        legend.addEventListener('click', function(event) {
            var target = event.target.closest && event.target.closest('[data-idx]');
            if (target && legend.contains(target)) toggleLegendRow(target);
        });
        legend.addEventListener('keydown', function(event) {
            if (event.key !== 'Enter' && event.key !== ' ') return;
            var target = event.target.closest && event.target.closest('[data-idx]');
            if (target && legend.contains(target)) {
                event.preventDefault();
                toggleLegendRow(target);
            }
        });
    }

    window.initPortfolioAllocationCharts = function(chartData) {
        if (!window.Chart || !chartData) return;
        Chart.defaults.color = textColor();
        var colorMap = buildColorMap(chartData);
        renderDoughnut({
            canvasId: 'bookValueChart',
            legendId: 'bookValueLegend',
            data: chartData.book_value_chart,
            centerLabel: 'BOOK VALUE'
        }, colorMap);
        renderDoughnut({
            canvasId: 'bookCapitalChart',
            legendId: 'bookCapitalLegend',
            data: chartData.capital_chart,
            centerLabel: 'CAPITAL'
        }, colorMap);
    };
})();
