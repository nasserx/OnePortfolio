/* Shared horizontal scrolling for page-sticky disclosure headers.
 * CSS owns vertical sticking; Bootstrap/Popper owns menu positioning/focus.
 */
(function () {
    'use strict';

    function mount(root) {
        if (root.dataset.summaryMounted) return;
        const header = root.querySelector('[data-summary-header]');
        const body = root.querySelector('[data-summary-body]');
        if (!header || !body) return;
        root.dataset.summaryMounted = 'true';

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
