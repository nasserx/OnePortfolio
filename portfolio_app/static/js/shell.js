/* ==========================================================================
   OnePortfolio — Application shell
   ==========================================================================

   Owns everything that lives outside a page's content: theme, density,
   navigation state, toasts, the command palette, and the shared motion
   helpers. Page-level behaviour stays in main.js and the page templates.

   Each concern is a small class with a single `mount()` entry point, so a
   failure in one never takes the rest of the shell down with it.
   ========================================================================== */

(function () {
  'use strict';

  var STORAGE = {
    theme: 'op:theme',
    density: 'op:density',
    sidebar: 'op:sidebar'
  };

  var prefersReducedMotion = function () {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  };

  function readStored(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (e) {
      return null;
    }
  }

  function writeStored(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (e) {
      /* Private mode / storage disabled — the preference just won't persist. */
    }
  }

  /* ======================================================================
     Theme & density
     The initial theme is applied by an inline script in <head> so the page
     never paints in the wrong palette; this class only handles changes.
     ====================================================================== */

  function ThemePreference() {}

  ThemePreference.prototype.mount = function () {
    var root = document.documentElement;

    document.querySelectorAll('[data-theme-toggle]').forEach(function (button) {
      button.addEventListener('click', function () {
        var current = root.getAttribute('data-theme');

        if (!current) {
          // No explicit choice yet — flip away from whatever the system gave us.
          var systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
          current = systemDark ? 'dark' : 'light';
        }

        var next = current === 'dark' ? 'light' : 'dark';
        root.setAttribute('data-theme', next);
        writeStored(STORAGE.theme, next);
        ThemePreference.syncControls(next);

        // CSS repaints itself, but anything drawn into a <canvas> has already
        // baked in the old palette. Canvas owners listen for this and redraw.
        window.dispatchEvent(new CustomEvent('op:themechange', {
          detail: { theme: next }
        }));
      });
    });

    document.querySelectorAll('[data-density-toggle]').forEach(function (button) {
      button.addEventListener('click', function () {
        var next = root.getAttribute('data-density') === 'compact' ? 'comfortable' : 'compact';
        root.setAttribute('data-density', next);
        writeStored(STORAGE.density, next);
        ThemePreference.syncControls();
      });
    });

    ThemePreference.syncControls(root.getAttribute('data-theme'));
  };

  /* Keep every toggle's icon and label in step with the active preference. */
  ThemePreference.syncControls = function (theme) {
    var root = document.documentElement;
    var resolved = theme || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    var compact = root.getAttribute('data-density') === 'compact';

    document.querySelectorAll('[data-theme-toggle]').forEach(function (button) {
      var icon = button.querySelector('.bi');
      if (icon) {
        icon.className = 'bi ' + (resolved === 'dark' ? 'bi-sun' : 'bi-moon-stars');
      }
      button.setAttribute(
        'aria-label',
        resolved === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'
      );
    });

    document.querySelectorAll('[data-density-toggle] [data-density-label]').forEach(function (label) {
      label.textContent = compact ? 'Comfortable density' : 'Compact density';
    });
  };

  /* ======================================================================
     Side navigation — desktop collapse + mobile drawer
     ====================================================================== */

  function SideNav() {
    this.shell = document.querySelector('.shell');
  }

  SideNav.prototype.mount = function () {
    if (!this.shell) return;

    var shell = this.shell;
    var self = this;

    // Collapse state lives on <html> rather than .shell so the inline head
    // script can restore it before the first paint.
    var root = document.documentElement;

    document.querySelectorAll('[data-sidebar-toggle]').forEach(function (button) {
      button.addEventListener('click', function () {
        var next = root.getAttribute('data-sidebar') === 'collapsed' ? 'expanded' : 'collapsed';
        root.setAttribute('data-sidebar', next);
        writeStored(STORAGE.sidebar, next);
        button.setAttribute(
          'aria-label', next === 'collapsed' ? 'Expand navigation' : 'Collapse navigation');
      });
    });

    document.querySelectorAll('[data-nav-open-toggle]').forEach(function (button) {
      button.addEventListener('click', function () {
        self.setOpen(shell.getAttribute('data-nav-open') !== 'true');
      });
    });

    var backdrop = shell.querySelector('.shell__backdrop');
    if (backdrop) {
      backdrop.addEventListener('click', function () { self.setOpen(false); });
    }

    // Following a link inside the drawer should close it, otherwise the
    // new page loads behind an open overlay on mobile.
    shell.querySelectorAll('.sidenav a[href]').forEach(function (link) {
      link.addEventListener('click', function () { self.setOpen(false); });
    });

    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') self.setOpen(false);
    });
  };

  SideNav.prototype.setOpen = function (open) {
    if (!this.shell) return;
    this.shell.setAttribute('data-nav-open', open ? 'true' : 'false');
    document.body.style.overflow = open ? 'hidden' : '';

    document.querySelectorAll('[data-nav-open-toggle]').forEach(function (button) {
      button.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  };

  /* ======================================================================
     Toasts
     `window.showToast` is the app-wide entry point; main.js's AJAX layer
     calls it after a successful modal submit.
     ====================================================================== */

  var TOAST_ICONS = {
    success: 'bi-check-circle-fill',
    danger: 'bi-exclamation-circle-fill',
    warning: 'bi-exclamation-triangle-fill',
    info: 'bi-info-circle-fill'
  };

  var TOAST_DISMISS_MS = 4200;

  function Toasts() {}

  Toasts.prototype.mount = function () {
    document.querySelectorAll('.flash-alert').forEach(Toasts.wire);
    window.showToast = Toasts.show;
  };

  Toasts.container = function () {
    var container = document.querySelector('.flash-container');
    if (!container) {
      container = document.createElement('div');
      container.className = 'flash-container';
      container.setAttribute('aria-live', 'polite');
      document.body.appendChild(container);
    }
    return container;
  };

  Toasts.dismiss = function (element) {
    element.style.transition = 'opacity 200ms ease, transform 200ms ease';
    element.style.opacity = '0';
    element.style.transform = 'translate3d(0, 8px, 0)';
    window.setTimeout(function () {
      if (element.parentNode) element.remove();
    }, 220);
  };

  Toasts.wire = function (element) {
    var close = element.querySelector('.flash-alert__close');
    if (close) {
      close.addEventListener('click', function () { Toasts.dismiss(element); });
    }

    var timer = window.setTimeout(function () {
      if (element.parentNode) Toasts.dismiss(element);
    }, TOAST_DISMISS_MS);

    // Reading a message should not race a timer.
    element.addEventListener('mouseenter', function () { window.clearTimeout(timer); });
  };

  Toasts.show = function (message, type) {
    var category = TOAST_ICONS[type] ? type : 'info';

    var element = document.createElement('div');
    element.className = 'flash-alert flash-alert--' + category;
    element.setAttribute('role', 'alert');

    var icon = document.createElement('i');
    icon.className = 'bi ' + TOAST_ICONS[category] + ' flash-alert__icon';
    icon.setAttribute('aria-hidden', 'true');

    var text = document.createElement('span');
    text.className = 'flash-alert__msg';
    text.textContent = message;

    var closeIcon = document.createElement('i');
    closeIcon.className = 'bi bi-x';
    closeIcon.setAttribute('aria-hidden', 'true');

    var close = document.createElement('button');
    close.type = 'button';
    close.className = 'flash-alert__close';
    close.setAttribute('aria-label', 'Close');
    close.appendChild(closeIcon);

    element.append(icon, text, close);
    Toasts.container().appendChild(element);
    Toasts.wire(element);
  };

  /* ======================================================================
     Command palette
     Items come from two sources: the static navigation set rendered by
     base.html, and anything on the current page tagged with
     `data-command="Label"`. Pages therefore extend the palette by adding
     one attribute — no registration step.
     ====================================================================== */

  function CommandPalette() {
    this.root = document.getElementById('commandPalette');
    this.input = document.getElementById('commandPaletteInput');
    this.list = document.getElementById('commandPaletteList');
    this.items = [];
    this.matches = [];
    this.activeIndex = 0;
    this.lastFocused = null;
  }

  CommandPalette.prototype.mount = function () {
    if (!this.root || !this.input || !this.list) return;

    var self = this;
    this.items = this.collect();

    document.addEventListener('keydown', function (event) {
      var isOpenShortcut = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k';
      if (isOpenShortcut) {
        event.preventDefault();
        self.toggle();
        return;
      }
      if (event.key === 'Escape' && !self.root.hidden) self.close();
    });

    document.querySelectorAll('[data-palette-open]').forEach(function (button) {
      button.addEventListener('click', function () { self.open(); });
    });

    this.root.addEventListener('mousedown', function (event) {
      if (event.target === self.root) self.close();
    });

    this.input.addEventListener('input', function () { self.render(); });

    this.input.addEventListener('keydown', function (event) {
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        self.move(1);
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        self.move(-1);
      } else if (event.key === 'Enter') {
        event.preventDefault();
        self.run(self.matches[self.activeIndex]);
      }
    });

    this.list.addEventListener('click', function (event) {
      var row = event.target.closest('[data-index]');
      if (row) self.run(self.matches[parseInt(row.dataset.index, 10)]);
    });
  };

  CommandPalette.prototype.collect = function () {
    var items = [];

    var source = document.getElementById('commandPaletteData');
    if (source) {
      try {
        JSON.parse(source.textContent).forEach(function (entry) { items.push(entry); });
      } catch (e) {
        /* Malformed payload should not break the shortcut entirely. */
      }
    }

    document.querySelectorAll('[data-command]').forEach(function (element) {
      items.push({
        label: element.getAttribute('data-command'),
        group: element.getAttribute('data-command-group') || 'On this page',
        icon: element.getAttribute('data-command-icon') || 'arrow-return-right',
        href: element.getAttribute('href') || null,
        element: element
      });
    });

    return items;
  };

  CommandPalette.prototype.toggle = function () {
    if (this.root.hidden) this.open();
    else this.close();
  };

  CommandPalette.prototype.open = function () {
    this.lastFocused = document.activeElement;
    this.root.hidden = false;
    this.input.value = '';
    this.activeIndex = 0;
    this.render();
    this.input.focus();
  };

  CommandPalette.prototype.close = function () {
    this.root.hidden = true;
    if (this.lastFocused && this.lastFocused.focus) this.lastFocused.focus();
  };

  CommandPalette.prototype.move = function (delta) {
    if (!this.matches.length) return;
    var count = this.matches.length;
    this.activeIndex = (this.activeIndex + delta + count) % count;
    this.paintSelection();
  };

  CommandPalette.prototype.run = function (item) {
    if (!item) return;
    this.close();
    if (item.href) {
      window.location.href = item.href;
    } else if (item.element) {
      item.element.click();
    }
  };

  CommandPalette.prototype.render = function () {
    var query = this.input.value.trim().toLowerCase();

    this.matches = query
      ? this.items.filter(function (item) {
          return item.label.toLowerCase().indexOf(query) !== -1
            || (item.group || '').toLowerCase().indexOf(query) !== -1;
        })
      : this.items.slice();

    this.activeIndex = 0;
    this.list.replaceChildren();

    if (!this.matches.length) {
      var empty = document.createElement('li');
      empty.className = 'palette__empty';
      empty.textContent = 'No matches';
      this.list.appendChild(empty);
      return;
    }

    var fragment = document.createDocumentFragment();

    this.matches.forEach(function (item, index) {
      var row = document.createElement('li');
      row.className = 'palette__item';
      row.dataset.index = String(index);
      row.setAttribute('role', 'option');

      var icon = document.createElement('i');
      icon.className = 'bi bi-' + item.icon;
      icon.setAttribute('aria-hidden', 'true');

      var label = document.createElement('span');
      label.textContent = item.label;

      var hint = document.createElement('span');
      hint.className = 'palette__hint';
      hint.textContent = item.group || '';

      row.append(icon, label, hint);
      fragment.appendChild(row);
    });

    this.list.appendChild(fragment);
    this.paintSelection();
  };

  CommandPalette.prototype.paintSelection = function () {
    var self = this;
    this.list.querySelectorAll('[data-index]').forEach(function (row, index) {
      var selected = index === self.activeIndex;
      row.setAttribute('aria-selected', selected ? 'true' : 'false');
      // Explicitly instant: this follows a keypress, so it has to be where
      // the caret is by the next one, not easing towards it.
      if (selected && row.scrollIntoView) {
        row.scrollIntoView({ block: 'nearest', behavior: 'instant' });
      }
    });
  };

  /* ======================================================================
     Number roll-up
     Animates a hero figure from zero to its rendered value, then snaps to
     the server-rendered text so the animation can never disagree with it.
     ====================================================================== */

  function CountUp() {}

  CountUp.prototype.mount = function () {
    var targets = document.querySelectorAll('[data-countup]');
    if (!targets.length) return;

    if (prefersReducedMotion()) return;

    targets.forEach(function (element) {
      var target = parseFloat(element.getAttribute('data-countup'));
      if (!isFinite(target) || Math.abs(target) < 0.005) return;

      var finalText = element.textContent;
      var decimals = (element.getAttribute('data-countup-decimals') || '2');
      var formatter = new Intl.NumberFormat('en-US', {
        minimumFractionDigits: parseInt(decimals, 10),
        maximumFractionDigits: parseInt(decimals, 10)
      });

      var duration = 900;
      var started = null;

      function frame(timestamp) {
        if (started === null) started = timestamp;
        var progress = Math.min((timestamp - started) / duration, 1);
        // easeOutExpo — fast start, long settle. Reads as the number
        // "arriving" rather than spinning.
        var eased = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress);

        if (progress < 1) {
          element.textContent = formatter.format(target * eased);
          window.requestAnimationFrame(frame);
        } else {
          element.textContent = finalText;
        }
      }

      window.requestAnimationFrame(frame);
    });
  };

  /* ======================================================================
     Scroll reveal — used by the marketing page and any long content page
     ====================================================================== */

  function ScrollReveal() {}

  ScrollReveal.prototype.mount = function () {
    // Tells the page that the thing which un-hides `[data-reveal]` is alive.
    // The stylesheet only hides content while this is set — see the inline
    // head script that sets it before first paint and drops it again if
    // this never runs.
    document.documentElement.setAttribute('data-reveal-mounted', '');

    var targets = document.querySelectorAll('[data-reveal]');
    if (!targets.length) return;

    if (prefersReducedMotion() || !('IntersectionObserver' in window)) {
      targets.forEach(function (element) { element.classList.add('is-revealed'); });
      return;
    }

    /* Reveal on the first pixel, not on a share of the element.
       `threshold: 0.12` with a negative bottom margin meant an element had
       to get an eighth of itself past a line 8% up from the fold before it
       was allowed to exist — so a block resting at the fold on load was
       *visible space with nothing in it*, and stayed that way until the
       reader scrolled. Worse for anyone who does not: at some window
       heights a section simply never appeared.

       A reveal is decoration. It may choose when to play; it may not
       decide whether content exists, so its trigger is the loosest one
       there is and every element still gets its entrance the moment it
       has any claim on the viewport. */
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-revealed');
        observer.unobserve(entry.target);
      });
    }, { threshold: 0 });

    targets.forEach(function (element) { observer.observe(element); });
  };

  /* ======================================================================
     Boot
     ====================================================================== */

  function mountAll() {
    [
      new ThemePreference(),
      new SideNav(),
      new Toasts(),
      new CommandPalette(),
      new CountUp(),
      new ScrollReveal()
    ].forEach(function (feature) {
      try {
        feature.mount();
      } catch (error) {
        // One broken shell feature must not stop the others from mounting.
        if (window.console) console.error('shell: mount failed', error);
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mountAll);
  } else {
    mountAll();
  }
}());
