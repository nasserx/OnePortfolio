/* ==========================================================================
   OnePortfolio — Marketing page
   ==========================================================================

   Fills the product shot with sample figures and renders its allocation
   ring. The numbers live here rather than in the template so the preview
   stays internally consistent — the totals are derived, never hand-typed.

   Header state, scroll reveal, and the theme toggle are shared shell concerns;
   this file owns only the deterministic preview metrics and allocation ring.
   ========================================================================== */

(function () {
  'use strict';

  var SAMPLE = {
    portfolios: [
      { name: 'Stocks', bookValue: 18400, capital: 20000 },
      { name: 'ETFs',   bookValue: 14200, capital: 16000 },
      { name: 'Crypto', bookValue: 9580,  capital: 12000 }
    ],
    cash: 6320,
    income: 2410,
    realizedPnl: 3640
  };

  var display = window.OnePortfolioDisplay;

  function total(key) {
    return SAMPLE.portfolios.reduce(function (sum, item) {
      return sum + (Number(item[key]) || 0);
    }, 0);
  }

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function prefersReducedMotion() {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  /* ---------------------------------------------------------------------
     Figures
     --------------------------------------------------------------------- */

  function renderMetrics() {
    var capital = total('capital');

    // Every figure in the preview is derived from SAMPLE, including the
    // headline return. Nothing is hand-typed into the template, so the
    // preview can never quietly contradict itself.
    var returnPercent = capital > 0 ? (SAMPLE.realizedPnl / capital) * 100 : 0;

    var values = {
      bookValue: display.money(total('bookValue'), false),
      totalCapital: display.money(capital, false),
      totalCash: display.money(SAMPLE.cash, false),
      totalIncome: display.money(SAMPLE.income, true),
      realizedPnl: display.money(SAMPLE.realizedPnl, true),
      returnPercent: display.percentage(returnPercent, 2, true)
    };

    document.querySelectorAll('[data-landing-metric]').forEach(function (element) {
      var key = element.getAttribute('data-landing-metric');
      element.textContent = values[key] || '';
    });
  }

  /* ---------------------------------------------------------------------
     Allocation ring
     --------------------------------------------------------------------- */

  var chart = null;

  function renderChart() {
    var canvas = document.getElementById('landingChart');
    var legend = document.getElementById('landingLegend');
    var status = document.getElementById('landingChartStatus');
    if (!canvas || !legend || !status || !window.Chart) return;

    if (chart) {
      chart.destroy();
      chart = null;
    }

    window.Chart.defaults.font.family = cssVar('--font-sans');

    var grandTotal = total('bookValue');
    var colors = ['--portfolio-chart-1', '--portfolio-chart-2', '--portfolio-chart-3'].map(function (name) {
      return cssVar(name);
    });

    var shares = SAMPLE.portfolios.map(function (item) {
      return grandTotal > 0 ? (item.bookValue / grandTotal) * 100 : 0;
    });

    chart = new window.Chart(canvas, {
      type: 'doughnut',
      data: {
        labels: SAMPLE.portfolios.map(function (item) { return item.name; }),
        datasets: [{
          data: shares,
          backgroundColor: colors,
          borderColor: cssVar('--card'),
          borderWidth: 2,
          hoverOffset: 5
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '66%',
        animation: prefersReducedMotion() ? false : { duration: 700 },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: cssVar('--popover'),
            borderColor: cssVar('--border'),
            borderWidth: 1,
            titleColor: cssVar('--popover-foreground'),
            bodyColor: cssVar('--muted-foreground'),
            padding: 10,
            displayColors: false,
            callbacks: {
              label: function (ctx) {
                return ' ' + display.percentage(shares[ctx.dataIndex], 1, false);
              }
            }
          }
        }
      }
    });

    var fragment = document.createDocumentFragment();

    SAMPLE.portfolios.forEach(function (item, index) {
      var row = document.createElement('li');
      row.className = 'allocation-legend__row';

      var swatch = document.createElement('span');
      swatch.className = 'swatch swatch-' + (index + 1);
      swatch.setAttribute('aria-hidden', 'true');

      var name = document.createElement('span');
      name.className = 'name';
      name.textContent = item.name;

      var value = document.createElement('span');
      value.className = 'value';
      value.textContent = display.money(item.bookValue, false);

      var pct = document.createElement('span');
      pct.className = 'pct';
      pct.textContent = display.percentage(shares[index], 1, false);

      row.append(swatch, name, value, pct);
      fragment.appendChild(row);
    });

    legend.replaceChildren(fragment);
    status.textContent = 'Sample allocation: ' + SAMPLE.portfolios.map(function (item, index) {
      return item.name + ', ' + display.money(item.bookValue, false) + ', '
        + display.percentage(shares[index], 1, false);
    }).join('; ') + '.';
  }

  function start() {
    renderMetrics();
    renderChart();

    // The ring is canvas-drawn, so a theme flip needs a full redraw.
    window.addEventListener('op:themechange', renderChart);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
}());
