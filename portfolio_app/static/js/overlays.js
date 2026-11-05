/* Shell overlays own only their own focus. Bootstrap remains the sole modal
   trap; programmatic callers add only the return path missing from its data API. */
(function () {
    'use strict';

    const focusSelector = 'a[href], button, input, select, textarea, [tabindex]';
    let active = null;
    let lastClick = null;
    const modals = new Set();
    const programmaticDialogs = new WeakSet();

    function available(element) {
        return !!element && element.isConnected && !element.disabled &&
            element.getAttribute('aria-disabled') !== 'true' &&
            !element.closest('[inert], [hidden]') && element.getClientRects().length > 0 &&
            window.getComputedStyle(element).visibility !== 'hidden';
    }

    function returnTarget(element) {
        const menu = element && element.closest('.action-menu');
        return menu ? menu.querySelector('.action-menu__trigger') : element;
    }

    function restore(element) {
        if (available(element)) element.focus({ preventScroll: true });
    }

    function blocked() {
        return modals.size > 0 || !!document.querySelector('.modal.show');
    }

    function close(root, returnFocus = true) {
        if (!active || active.root !== root) return;
        const previous = active;
        active = null;
        previous.background.forEach(([element, inert]) => { element.inert = inert; });
        document.body.style.overflow = previous.overflow;
        previous.onClose();
        if (returnFocus) restore(previous.opener);
    }

    function open(root, onClose, opener) {
        if (blocked()) return false;
        if (active && active.root === root) return true;
        let target = returnTarget(opener || document.activeElement);
        if (active) {
            if (active.root.contains(target)) target = active.opener;
            close(active.root, false);
        }
        const background = [];
        // Inert siblings along the ancestor path, never an ancestor of the
        // active surface. This also supports the drawer nested in .shell.
        for (let branch = root; branch && branch !== document.body; branch = branch.parentElement) {
            Array.from(branch.parentElement.children).forEach(element => {
                if (element === branch || element.matches('script, style, link, .shell__backdrop')) return;
                background.push([element, element.inert]);
                element.inert = true;
            });
        }
        active = { root, onClose, opener: target, background, overflow: document.body.style.overflow };
        document.body.style.overflow = 'hidden';
        return true;
    }

    function focusable(root) {
        return Array.from(root.querySelectorAll(focusSelector)).filter(element =>
            element.tabIndex >= 0 && available(element));
    }

    document.addEventListener('keydown', function (event) {
        if (!active || event.defaultPrevented || blocked()) return;
        if (event.key === 'Escape') {
            event.preventDefault();
            close(active.root);
        } else if (event.key === 'Tab') {
            const items = focusable(active.root);
            const first = items[0] || active.root;
            const last = items[items.length - 1] || active.root;
            if (!active.root.contains(document.activeElement) ||
                (event.shiftKey && document.activeElement === first) ||
                (!event.shiftKey && document.activeElement === last) || !items.length) {
                event.preventDefault();
                (event.shiftKey ? last : first).focus();
            }
        }
    });

    document.addEventListener('focusin', function (event) {
        if (active && !blocked() && !active.root.contains(event.target)) {
            (focusable(active.root)[0] || active.root).focus();
        }
    });

    document.addEventListener('show.bs.modal', function (event) {
        if (event.defaultPrevented) return;
        // Runs before Bootstrap activates its trap or locks document scrolling.
        if (active) close(active.root, false);
        modals.add(event.target);
        queueMicrotask(() => { if (event.defaultPrevented) modals.delete(event.target); });
    });
    document.addEventListener('hidden.bs.modal', event => { modals.delete(event.target); });

    // Native input can run microtasks between capture and delegated listeners.
    // eventPhase identifies the active dispatch; release its reference afterwards.
    document.addEventListener('click', function (event) {
        lastClick = event;
        setTimeout(() => { if (lastClick === event) lastClick = null; }, 0);
    }, true);

    // Restored pointer focus is not a request to keep the ledger actions open.
    // Resume hover on the next pointer movement, even if the row never changes.
    function restoreRecordAction(button, group) {
        const row = group.closest('tr');
        group.dataset.dialogReturn = 'idle';
        function resumeHover() { group.dataset.dialogReturn = 'hover'; }
        function clear() {
            group.removeAttribute('data-dialog-return');
            row.removeEventListener('pointermove', resumeHover);
            button.removeEventListener('blur', clear);
            button.removeEventListener('keydown', clear);
        }
        row.addEventListener('pointermove', resumeHover, {once: true});
        button.addEventListener('blur', clear);
        button.addEventListener('keydown', clear);
        restore(button);
    }

    function showDialog(element, opener) {
        if (!element || programmaticDialogs.has(element) || element.classList.contains('show')) return;
        const click = lastClick?.eventPhase ? lastClick : null;
        const clickOpener = click?.target.closest(focusSelector);
        const target = returnTarget(opener || clickOpener || document.activeElement);
        const recordGroup = click?.detail > 0 && target === clickOpener && target?.closest('.record-actions');
        const modal = window.bootstrap.Modal.getOrCreateInstance(element);
        programmaticDialogs.add(element);
        const onHidden = () => {
            if (blocked()) return;
            if (recordGroup && available(target)) restoreRecordAction(target, recordGroup);
            else restore(target);
        };
        // Document's hidden listener clears ownership before this callback.
        const onHiddenAfterBubble = () => {
            programmaticDialogs.delete(element);
            queueMicrotask(onHidden);
        };
        element.addEventListener('hidden.bs.modal', onHiddenAfterBubble, { once: true });
        const onShow = event => {
            queueMicrotask(() => {
                if (event.defaultPrevented) {
                    programmaticDialogs.delete(element);
                    element.removeEventListener('hidden.bs.modal', onHiddenAfterBubble);
                }
            });
        };
        element.addEventListener('show.bs.modal', onShow, { once: true });
        modal.show(target);
    }

    window.OnePortfolioOverlays = Object.freeze({ open, close, blocked, available });
    window.OnePortfolioDialogs = Object.freeze({ show: showDialog });
}());
