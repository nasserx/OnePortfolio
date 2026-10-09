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

  var PALETTE_SIZE = 5;
  var display = window.OnePortfolioDisplay;

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function prefersReducedMotion() {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  function palette() {
    var colors = [];
    for (var i = 1; i <= PALETTE_SIZE; i += 1) {
      colors.push(cssVar('--portfolio-chart-' + i));
    }
    return colors;
  }

  /* Large figures collapse to B/M so the ring's centre label always fits;
     everything else keeps two decimals so the legend column stays aligned. */
  function compact(value) { return display.compactMoney(value); }

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

    ['book_value_chart', 'net_contributions_chart'].forEach(function (key) {
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

      ctx.fillStyle = cssVar('--muted-foreground');
      ctx.font = '500 ' + labelSize + 'px ' + cssVar('--font-sans');
      ctx.fillText(options.label, arc.x, arc.y - Math.round(valueSize * 0.72));

      ctx.fillStyle = cssVar('--foreground');
      ctx.font = '600 ' + valueSize + 'px ' + cssVar('--font-sans');
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
    this.canvasWrap = this.canvas ? this.canvas.closest('.alloc-canvas') : null;
    this.legend = document.getElementById('allocationLegend');
    this.empty = document.querySelector('[data-alloc-empty]');
    this.switcher = document.querySelector('[data-alloc-switch]');
    this.panel = document.getElementById('allocation-panel');
    this.status = document.getElementById('allocationChartStatus');
    this.legendWired = false;
  }

  AllocationChart.prototype.colorFor = function (name) {
    if (name === 'Other Portfolios') return this.colors[4];
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
      window.Chart.defaults.color = cssVar('--muted-foreground');
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

    // The thumb has to be re-placed on resize, because its offset is
    // measured in pixels. What it must be re-placed *under* is whatever is
    // selected at that moment — reading the selection once at mount and
    // closing over it meant a resize silently slid the thumb back to the
    // option the page opened with, leaving the indicator sitting under one
    // label while the chart showed the other.
    var current = this.switcher.querySelector('[aria-selected="true"]')
      || options[0];
    if (!current) return;

    function select(option, moveFocus) {
      options.forEach(function (other) {
        var selected = other === option;
        other.setAttribute('aria-selected', selected ? 'true' : 'false');
        other.setAttribute('tabindex', selected ? '0' : '-1');
      });
      current = option;
      moveThumb(current);
      self.view = option.getAttribute('data-alloc-view');
      if (self.panel && option.id) self.panel.setAttribute('aria-labelledby', option.id);
      self.render();
      if (moveFocus) option.focus();
    }

    options.forEach(function (option, index) {
      option.addEventListener('click', function () { select(option, false); });
      option.addEventListener('keydown', function (event) {
        var nextIndex;
        if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
          nextIndex = (index + 1) % options.length;
        } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
          nextIndex = (index - 1 + options.length) % options.length;
        } else if (event.key === 'Home') {
          nextIndex = 0;
        } else if (event.key === 'End') {
          nextIndex = options.length - 1;
        } else {
          return;
        }
        event.preventDefault();
        select(options[nextIndex], true);
      });
    });

    // Layout is not settled during DOMContentLoaded inside a flex row, so
    // the initial thumb placement waits one frame for real geometry.
    window.requestAnimationFrame(function () { moveThumb(current); });
    window.addEventListener('resize', function () { moveThumb(current); });
  };

  AllocationChart.prototype.render = function () {
    var dataset = this.data[this.view] || {};
    var basis = this.view === 'net_contributions_chart' ? 'net contributions' : 'book value';
    var accessibleLabel = 'Portfolio split by ' + basis;

    if (this.chart) {
      this.chart.destroy();
      this.chart = null;
    }
    this.legend.replaceChildren();
    this.canvas.setAttribute('aria-label', accessibleLabel);
    this.canvas.textContent = accessibleLabel + '. Details follow in the interactive legend.';
    this.legend.setAttribute('aria-label', accessibleLabel + ' legend');

    if (!hasData(dataset)) {
      this.canvas.hidden = true;
      if (this.canvasWrap) this.canvasWrap.hidden = true;
      this.legend.hidden = true;
      var emptyMessage = dataset && dataset.unavailable
        ? 'Chart unavailable for this numeric range. See the portfolio details below.'
        : 'No portfolio data available.';
      if (this.empty) {
        this.empty.hidden = false;
        this.empty.textContent = emptyMessage;
      }
      if (this.status) this.status.textContent = accessibleLabel + ': ' + emptyMessage;
      return;
    }

    this.canvas.hidden = false;
    if (this.canvasWrap) this.canvasWrap.hidden = false;
    this.legend.hidden = false;
    if (this.empty) this.empty.hidden = true;

    this.renderChart(dataset);
    this.renderLegend(dataset);
    if (this.status) {
      this.status.textContent = accessibleLabel + ' showing '
        + dataset.categories.length + (dataset.categories.length === 1 ? ' portfolio.' : ' portfolios.');
    }
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
          borderColor: cssVar('--card'),
          borderWidth: 2,
          hoverOffset: 6
        }]
      },
      plugins: [centreText],
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '68%',
        /* The ring draws itself once, when a page of numbers first appears.
           At 420ms with the default ease-out it snapped: the wedges were
           already at rest before the eye had found them, so the motion read
           as a flicker rather than as the chart being built.

           `easeInOutQuart` is the shape that makes a slow sweep feel
           deliberate instead of sluggish — it leaves and arrives gently and
           spends its speed in the middle, so most of the duration is not
           actually perceived as waiting. Ease-out alone at this length
           would look like it was dragging to a halt. */
        animation: prefersReducedMotion()
          ? false
          : { duration: 1150, easing: 'easeInOutQuart' },
        transitions: {
          legendToggle: { animation: { duration: 300, easing: 'easeOutQuart' } }
        },
        layout: { padding: 6 },
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
                var pct = Number(ctx.parsed);
                return ' ' + display.percentage(pct, 1, false);
              }
            }
          },
          centreText: {
            label: this.view === 'net_contributions_chart' ? 'Net Contributions' : 'Book Value',
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

      var toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'allocation-legend__row allocation-legend__toggle';
      toggle.setAttribute('aria-pressed', 'false');

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
      pct.textContent = display.percentage(share, 1, false);

      toggle.setAttribute(
        'aria-label',
        'Hide ' + name + ', ' + value.textContent + ', ' + pct.textContent
      );
      toggle.append(swatch, label, value, pct);
      row.appendChild(toggle);
      fragment.appendChild(row);
    });

    this.legend.appendChild(fragment);
    this.wireLegend();
  };

  AllocationChart.prototype.wireLegend = function () {
    if (this.legendWired) return;
    this.legendWired = true;

    var self = this;

    function toggle(row) {
      var index = parseInt(row.dataset.idx, 10);
      if (isNaN(index) || !self.chart) return;

      var nowHidden = !row.classList.contains('is-hidden');
      row.classList.toggle('is-hidden', nowHidden);
      var button = row.querySelector('.allocation-legend__toggle');
      if (button) {
        button.setAttribute('aria-pressed', nowHidden ? 'true' : 'false');
        button.setAttribute(
          'aria-label',
          (nowHidden ? 'Show ' : 'Hide ') + row.title
        );
      }
      self.chart.toggleDataVisibility(index);
      /* Hiding a slice answers the click, so it runs on its own short
         transition rather than replaying the chart's entrance. A 1150ms
         sweep is right once, when the ring first draws itself; repeating it
         every time a legend row is toggled would put the reader's own input
         behind an animation they have already watched. */
      self.chart.update(prefersReducedMotion() ? 'none' : 'legendToggle');
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
    window.Chart.defaults.color = cssVar('--muted-foreground');
    window.Chart.defaults.font.family = cssVar('--font-sans');
    new AllocationChart(chartData).mount();
  };
}());
