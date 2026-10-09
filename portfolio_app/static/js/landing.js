/* ==========================================================================
   OnePortfolio — Marketing page
   ==========================================================================

   Renders the allocation ring from the public synthetic preview. Financial
   metrics are calculated with Decimal and rendered by the server; JavaScript
   converts only chart values to presentation numbers.

   Header state, scroll reveal, and the theme toggle are shared shell concerns;
   this file owns only the preview allocation ring.
   ========================================================================== */

(function () {
  'use strict';

  var SAMPLE = {
    portfolios: JSON.parse(document.getElementById('landing-preview-data').textContent).map(function (item) {
      return { name: item.name, bookValue: Number(item.bookValue) };
    })
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
