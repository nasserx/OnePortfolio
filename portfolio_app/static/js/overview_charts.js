/* ==========================================================================
   OnePortfolio — Allocation chart
   ==========================================================================

   One doughnut, two datasets. The segmented control swaps which basis is
   shown; colours are assigned once across BOTH datasets so a portfolio keeps
   the same colour whichever basis is active — that consistency is the whole
   reason the two views can share a chart.
   ========================================================================== */

(function () {
  'use strict';

  var PALETTE_SIZE = 7;

  function cssVar(name, fallback) {
    var value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return value || fallback;
  }

  function prefersReducedMotion() {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  function palette() {
    var colors = [];
    for (var i = 1; i <= PALETTE_SIZE; i += 1) {
      colors.push(cssVar('--cat-' + i, '#7461f3'));
    }
    return colors;
  }

  /* Large figures collapse to B/M so the ring's centre label always fits;
     everything else keeps two decimals so the legend column stays aligned. */
  function compact(value) {
    var number = Number(value) || 0;
    var magnitude = Math.abs(number);

    if (magnitude >= 1e9) return (number / 1e9).toFixed(2) + 'B';
    if (magnitude >= 1e6) return (number / 1e6).toFixed(2) + 'M';

    return number.toLocaleString('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    });
  }

  function truncate(text, max) {
    var value = text || '';
    return value.length > max ? value.slice(0, max) + '…' : value;
  }

  function hasData(dataset) {
    return Boolean(
      dataset
      && Array.isArray(dataset.categories)
      && dataset.categories.length
      && Array.isArray(dataset.allocations)
      && dataset.allocations.some(function (value) { return Number(value) > 0; })
    );
  }

  /* One colour index per portfolio name, shared across both datasets. */
  function buildColorMap(chartData) {
    var map = {};
    var next = 0;

    ['book_value_chart', 'capital_chart'].forEach(function (key) {
      var dataset = chartData[key] || {};
      (dataset.categories || []).forEach(function (name) {
        if (name !== 'Other Portfolios' && map[name] === undefined) {
          map[name] = next;
          next += 1;
        }
      });
    });

    return map;
  }

  /* Centre label plugin — the total belongs inside the ring, not beside it. */
  var centreText = {
    id: 'centreText',
    afterDraw: function (chart) {
      var options = chart.config.options.plugins.centreText;
      if (!options || !options.value) return;

      var arc = chart.getDatasetMeta(0).data[0];
      if (!arc) return;

      /* The ring is not a fixed size — it grows with the panel. Sizing the
         centre label off the hole it sits in keeps the type in proportion
         instead of leaving a 15px figure marooned in a large ring. The
         bounds reproduce the previous sizes at the previous diameter. */
      var hole = arc.innerRadius || 49;
      var valueSize = Math.max(15, Math.min(22, Math.round(hole * 0.30)));
      var labelSize = Math.max(11, Math.min(14, Math.round(hole * 0.20)));

      var ctx = chart.ctx;
      ctx.save();
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';

      ctx.fillStyle = cssVar('--fg-subtle', '#82828e');
      ctx.font = '500 ' + labelSize + 'px Inter, sans-serif';
      ctx.fillText(options.label, arc.x, arc.y - Math.round(valueSize * 0.72));

      ctx.fillStyle = cssVar('--fg-default', '#ededf1');
      ctx.font = '600 ' + valueSize + 'px Inter, sans-serif';
      ctx.fillText(options.value, arc.x, arc.y + Math.round(valueSize * 0.55));

      ctx.restore();
    }
  };

  function AllocationChart(chartData) {
    this.data = chartData || {};
    this.colorMap = buildColorMap(this.data);
    this.colors = palette();
    this.chart = null;
    this.view = 'book_value_chart';

    this.canvas = document.getElementById('allocationChart');
    this.legend = document.getElementById('allocationLegend');
    this.empty = document.querySelector('[data-alloc-empty]');
    this.switcher = document.querySelector('[data-alloc-switch]');
  }

  AllocationChart.prototype.colorFor = function (name) {
    if (name === 'Other Portfolios') return cssVar('--cat-other', '#7b7b8a');
    var index = this.colorMap[name];
    if (!isFinite(index)) index = 0;
    return this.colors[index % this.colors.length];
  };

  AllocationChart.prototype.swatchClass = function (name) {
    if (name === 'Other Portfolios') return 'swatch swatch-other';
    var index = this.colorMap[name];
    if (!isFinite(index)) index = 0;
    return 'swatch swatch-' + ((index % PALETTE_SIZE) + 1);
  };

  AllocationChart.prototype.mount = function () {
    if (!this.canvas || !this.legend || !window.Chart) return;

    var self = this;

    this.mountSwitcher();
    this.render();

    // Canvas pixels do not follow CSS custom properties, so the chart has to
    // be rebuilt from the new palette whenever the theme flips.
    window.addEventListener('op:themechange', function () {
      self.colors = palette();
      window.Chart.defaults.color = cssVar('--fg-muted', '#a3a3ae');
      self.render();
    });
  };

  AllocationChart.prototype.mountSwitcher = function () {
    if (!this.switcher) return;

    var self = this;
    var options = Array.prototype.slice.call(
      this.switcher.querySelectorAll('[data-alloc-view]'));
    var thumb = this.switcher.querySelector('.segmented__thumb');

    function moveThumb(active) {
      if (!thumb) return;
      thumb.style.width = active.offsetWidth + 'px';
      thumb.style.transform = 'translateX(' + (active.offsetLeft - 3) + 'px)';
    }

    options.forEach(function (option) {
      option.addEventListener('click', function () {
        options.forEach(function (other) {
          other.setAttribute('aria-selected', other === option ? 'true' : 'false');
        });
        moveThumb(option);
        self.view = option.getAttribute('data-alloc-view');
        self.render();
      });
    });

    var selected = this.switcher.querySelector('[aria-selected="true"]') || options[0];
    if (selected) {
      // Layout is not settled during DOMContentLoaded inside a flex row, so
      // the initial thumb placement waits one frame for real geometry.
      window.requestAnimationFrame(function () { moveThumb(selected); });
      window.addEventListener('resize', function () { moveThumb(selected); });
    }
  };

  AllocationChart.prototype.render = function () {
    var dataset = this.data[this.view] || {};

    if (this.chart) {
      this.chart.destroy();
      this.chart = null;
    }
    this.legend.replaceChildren();

    if (!hasData(dataset)) {
      this.canvas.hidden = true;
      this.legend.hidden = true;
      if (this.empty) this.empty.hidden = false;
      return;
    }

    this.canvas.hidden = false;
    this.legend.hidden = false;
    if (this.empty) this.empty.hidden = true;

    this.renderChart(dataset);
    this.renderLegend(dataset);
  };

  AllocationChart.prototype.renderChart = function (dataset) {
    var self = this;

    this.chart = new window.Chart(this.canvas, {
      type: 'doughnut',
      data: {
        labels: dataset.categories,
        datasets: [{
          data: dataset.allocations,
          backgroundColor: dataset.categories.map(function (name) {
            return self.colorFor(name);
          }),
          borderColor: cssVar('--chart-ring-gap', '#121216'),
          borderWidth: 2,
          hoverOffset: 6
        }]
      },
      plugins: [centreText],
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '68%',
        animation: prefersReducedMotion() ? false : { duration: 420 },
        layout: { padding: 6 },
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
                var pct = Number(ctx.parsed);
                return ' ' + (isFinite(pct) ? pct.toFixed(1) : '0.0') + '%';
              }
            }
          },
          centreText: {
            label: this.view === 'capital_chart' ? 'Total capital' : 'Book value',
            value: compact(dataset.total || 0)
          }
        }
      }
    });
  };

  AllocationChart.prototype.renderLegend = function (dataset) {
    var self = this;
    var fragment = document.createDocumentFragment();

    dataset.categories.forEach(function (name, index) {
      var row = document.createElement('li');
      row.title = name;
      row.dataset.idx = String(index);
      row.setAttribute('role', 'button');
      row.setAttribute('tabindex', '0');
      row.setAttribute('aria-pressed', 'false');

      var swatch = document.createElement('span');
      swatch.className = self.swatchClass(name);

      var label = document.createElement('span');
      label.className = 'name';
      label.textContent = truncate(name, 20);

      var value = document.createElement('span');
      value.className = 'value';
      value.textContent = compact((dataset.values || [])[index]);

      var pct = document.createElement('span');
      pct.className = 'pct';
      var share = Number(dataset.allocations[index]);
      pct.textContent = (isFinite(share) ? share.toFixed(1) : '0.0') + '%';

      row.append(swatch, label, value, pct);
      fragment.appendChild(row);
    });

    this.legend.appendChild(fragment);
    this.wireLegend();
  };

  AllocationChart.prototype.wireLegend = function () {
    var self = this;

    function toggle(row) {
      var index = parseInt(row.dataset.idx, 10);
      if (isNaN(index) || !self.chart) return;

      var nowHidden = !row.classList.contains('is-hidden');
      row.classList.toggle('is-hidden', nowHidden);
      row.setAttribute('aria-pressed', nowHidden ? 'true' : 'false');
      self.chart.toggleDataVisibility(index);
      self.chart.update();
    }

    this.legend.addEventListener('click', function (event) {
      var row = event.target.closest('[data-idx]');
      if (row) toggle(row);
    });

    this.legend.addEventListener('keydown', function (event) {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      var row = event.target.closest('[data-idx]');
      if (!row) return;
      event.preventDefault();
      toggle(row);
    });
  };

  window.initPortfolioAllocationChart = function (chartData) {
    if (!window.Chart || !chartData) return;
    window.Chart.defaults.color = cssVar('--fg-muted', '#a3a3ae');
    window.Chart.defaults.font.family = 'Inter, sans-serif';
    new AllocationChart(chartData).mount();
  };
}());
