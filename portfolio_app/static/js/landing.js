/* ==========================================================================
   OnePortfolio — Marketing page
   ==========================================================================

   Fills the product shot with sample figures and renders its allocation
   ring. The numbers live here rather than in the template so the preview
   stays internally consistent — the totals are derived, never hand-typed.

   Nothing here listens to scrolling. The header used to swap appearance at
   8px of scroll and this file drove it; the header now has one appearance,
   so the listener and the state class went with it. Scroll reveal and the
   theme toggle come from shell.js, which this page also loads.
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

  var formatter = new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });

  function format(value) {
    return formatter.format(Number(value) || 0);
  }

  function signed(value) {
    var number = Number(value) || 0;
    return (number > 0 ? '+' : '') + format(number);
  }

  function total(key) {
    return SAMPLE.portfolios.reduce(function (sum, item) {
      return sum + (Number(item[key]) || 0);
    }, 0);
  }

  function cssVar(name, fallback) {
    var value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return value || fallback;
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
      bookValue: format(total('bookValue')),
      totalCapital: format(capital),
      totalCash: format(SAMPLE.cash),
      totalIncome: signed(SAMPLE.income),
      realizedPnl: signed(SAMPLE.realizedPnl),
      returnPercent: (returnPercent > 0 ? '+' : '') + returnPercent.toFixed(2) + '%'
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
    if (!canvas || !legend || !window.Chart) return;

    if (chart) {
      chart.destroy();
      chart = null;
    }

    var grandTotal = total('bookValue');
    var colors = ['--cat-1', '--cat-2', '--cat-3'].map(function (name) {
      return cssVar(name, '#7461f3');
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
          borderColor: cssVar('--bg-surface', '#121216'),
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
            backgroundColor: cssVar('--bg-raised', '#18181d'),
            borderColor: cssVar('--line-default', 'rgba(255,255,255,.11)'),
            borderWidth: 1,
            titleColor: cssVar('--fg-default', '#ededf1'),
            bodyColor: cssVar('--fg-muted', '#a3a3ae'),
            padding: 10,
            displayColors: false,
            callbacks: {
              label: function (ctx) {
                return ' ' + shares[ctx.dataIndex].toFixed(1) + '%';
              }
            }
          }
        }
      }
    });

    var fragment = document.createDocumentFragment();

    SAMPLE.portfolios.forEach(function (item, index) {
      var row = document.createElement('li');

      var swatch = document.createElement('span');
      swatch.className = 'swatch swatch-' + (index + 1);
      swatch.setAttribute('aria-hidden', 'true');

      var name = document.createElement('span');
      name.className = 'name';
      name.textContent = item.name;

      var value = document.createElement('span');
      value.className = 'value';
      value.textContent = format(item.bookValue);

      var pct = document.createElement('span');
      pct.className = 'pct';
      pct.textContent = shares[index].toFixed(1) + '%';

      row.append(swatch, name, value, pct);
      fragment.appendChild(row);
    });

    legend.replaceChildren(fragment);
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
