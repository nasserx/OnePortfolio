/* Shared disclosures, record pagination and synchronized header scrolling.
 * CSS owns vertical sticking; Bootstrap/Popper owns menu positioning/focus.
 */
(function () {
    'use strict';

    function mountDisclosures(root) {
        const key = root.dataset.summaryList === 'assets' ? 'txOpen' : 'portfoliosOpen';
        const open = new Set();
        const paginated = new WeakSet();

        function setOpen(toggle, expanded) {
            const panel = document.getElementById(toggle.getAttribute('aria-controls'));
            if (!panel) return;
            panel.hidden = !expanded;
            toggle.setAttribute('aria-expanded', String(expanded));
            if (!expanded) {
                open.delete(toggle.dataset.disclosure);
                return;
            }
            open.add(toggle.dataset.disclosure);
            if (paginated.has(panel)) return;
            const bar = panel.querySelector('.pagination-bar');
            if (!bar) return;
            const rows = panel.querySelectorAll('tbody tr');
            const pageSize = 10;
            function showPage(page) {
                const start = (page - 1) * pageSize;
                rows.forEach((row, i) => { row.hidden = i < start || i >= start + pageSize; });
                window.OnePortfolioPagination.render(bar, {
                    currentPage: page,
                    totalPages: Math.max(1, Math.ceil(rows.length / pageSize)),
                    label: bar.dataset.paginationLabel,
                    onPageChange: showPage,
                });
            }
            showPage(1);
            paginated.add(panel);
        }

        let restored;
        try {
            const previous = sessionStorage.getItem(key + 'Ref');
            const navigation = window.performance?.getEntriesByType('navigation')[0];
            if (previous === window.location.href &&
                (navigation?.type === 'reload' || document.referrer === previous)) {
                restored = JSON.parse(sessionStorage.getItem(key));
            } else {
                sessionStorage.removeItem(key);
                sessionStorage.removeItem(key + 'Ref');
            }
        } catch {
            // Persistence is optional when browser storage is unavailable.
        }
        if (Array.isArray(restored) && restored.length) {
            const ids = new Set(restored);
            root.querySelectorAll('[data-disclosure]').forEach(toggle => {
                if (ids.has(toggle.dataset.disclosure)) setOpen(toggle, true);
            });
        }

        root.addEventListener('click', event => {
            const toggle = event.target.closest('[data-disclosure]');
            if (!toggle) return;
            setOpen(toggle, toggle.getAttribute('aria-expanded') !== 'true');
            try {
                sessionStorage.setItem(key, JSON.stringify([...open]));
                sessionStorage.setItem(key + 'Ref', window.location.href);
            } catch {
                // The panel and its accessibility state already reflect the click.
            }
        });
    }

    function mount(root) {
        if (root.dataset.summaryMounted) return;
        const header = root.querySelector('[data-summary-header]');
        const body = root.querySelector('[data-summary-body]');
        if (!header || !body) return;
        root.dataset.summaryMounted = 'true';
        mountDisclosures(root);

        function synchronize(source, target) {
            const max = Math.max(0, Math.min(
                source.scrollWidth - source.clientWidth,
                target.scrollWidth - target.clientWidth
            ));
            const left = Math.max(0, Math.min(source.scrollLeft, max));
            if (source.scrollLeft !== left) source.scrollLeft = left;
            if (target.scrollLeft !== left) target.scrollLeft = left;
        }

        header.addEventListener('scroll', function (event) {
            if (event.target === header) synchronize(header, body);
        }, {passive: true});
        body.addEventListener('scroll', function (event) {
            if (event.target === body) synchronize(body, header);
        }, {passive: true});

        function resize() {
            synchronize(body, header);
            root.style.setProperty('--summary-header-height', `${header.parentElement.offsetHeight}px`);
            for (const region of [header, body]) {
                region.tabIndex = region.scrollWidth > region.clientWidth ? 0 : -1;
            }
        }

        if (window.ResizeObserver) {
            const observer = new window.ResizeObserver(resize);
            observer.observe(header);
            observer.observe(body);
            // Font-size changes can alter the minimum track width without
            // changing the viewport, including mobile typography and zoom.
            observer.observe(header.firstElementChild);
            observer.observe(body.firstElementChild);
        } else {
            window.addEventListener('resize', resize, {passive: true});
            root.closest('.shell')?.addEventListener('transitionend', resize);
        }
        resize();
    }

    document.querySelectorAll('[data-summary-list]').forEach(mount);
}());
