/* Advisory arithmetic only. Python owns all transaction acceptance/persistence.
   BigInt coefficients preserve exact decimals; rounding happens only for display. */
(() => {
    'use strict';
    const controllers = new WeakMap();
    const numeric = () => window.OnePortfolioNumeric;
    const span = 8192n; // Preview work budget, never an input/storage precision cap.
    const min = (...values) => values.reduce((a, b) => a < b ? a : b);
    const max = (...values) => values.reduce((a, b) => a > b ? a : b);

    function decimal(text) {
        if (typeof text !== 'string' || text.length > 4096 || !numeric().classify(text).complete) return null;
        const [mantissa, exponent = '0'] = text.trim().replace(/,/g, '').split(/[eE]/);
        const coefficient = BigInt(mantissa.replace('.', ''));
        const exp = BigInt(exponent) - BigInt((mantissa.split('.')[1] || '').length);
        const digits = BigInt(coefficient.toString().replace('-', '').length);
        if (max(exp + digits, 0n) - min(exp, 0n) > span) return null;
        return {coefficient, exp, adjusted: exp + digits - 1n};
    }

    function fixed(coefficient, exp) {
        const sign = coefficient < 0n ? '-' : '';
        const absolute = coefficient < 0n ? -coefficient : coefficient;
        if (exp >= 0n) return sign + (absolute * 10n ** exp).toString();
        const unit = 10n ** -exp;
        return sign + (absolute / unit).toString() + '.' +
            (absolute % unit).toString().padStart(unit.toString().length - 1, '0');
    }

    function calculate(type, price, quantity, fees) {
        if (!['Buy', 'Sell'].includes(type)) return null;
        const p = decimal(price), q = decimal(quantity), f = decimal(fees);
        if (!p || !q || !f) return null;
        const productExp = p.exp + q.exp;
        const low = min(productExp, f.exp, -2n);
        const high = max(p.adjusted + q.adjusted + 2n, f.adjusted + 1n, 0n) + 1n;
        if (high - low > span) return null;
        const exp = min(productExp, f.exp);
        const gross = p.coefficient * q.coefficient * 10n ** (productExp - exp);
        const fee = f.coefficient * 10n ** (f.exp - exp);
        const total = type === 'Sell' ? gross - fee : gross + fee;
        const absolute = total < 0n ? -total : total;
        const shift = exp + 2n;
        let cents;
        if (shift >= 0n) cents = absolute * 10n ** shift;
        else {
            const divisor = 10n ** -shift;
            // Python fmt_money uses ROUND_HALF_UP, including negative ties.
            cents = absolute / divisor + (absolute % divisor * 2n >= divisor ? 1n : 0n);
        }
        const whole = (cents / 100n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
        const formatted = (total < 0n ? '-' : '') + whole + '.' + (cents % 100n).toString().padStart(2, '0');
        return {amount: fixed(total, exp), formatted_amount: formatted};
    }

    class Preview {
        constructor(form, output, edit) {
            this.form = form;
            this.output = output;
            this.edit = edit;
            this.revision = 0;
            this.active = false;
            this.fields = ['price', 'quantity', 'fees'].map(name =>
                form.querySelector(`#${edit ? 'edit_' : ''}${name}`));
            this.type = form.querySelector(edit ? '#edit_transaction_type_display' : '#transaction_type');
            const changed = event => {
                if (![...this.fields, this.type].includes(event.target)) return;
                const revision = this.revision;
                // Let the numeric editor settle/reject an edit before rendering.
                // No debounce, HTTP request or stale amount window.
                const update = () => {
                    if (revision === this.revision) this.refresh();
                };
                queueMicrotask(() => event.type === 'compositionend' ? queueMicrotask(update) : update());
            };
            for (const event of ['input', 'change']) form.addEventListener(event, changed, true);
            form.addEventListener('compositionstart', () => this.render(), true);
            form.addEventListener('compositionend', changed, true);
            form.addEventListener('reset', () => this.reset());
            const modal = form.closest('.modal');
            modal?.addEventListener('shown.bs.modal', () => this.open());
            modal?.addEventListener('hide.bs.modal', () => { this.active = false; this.reset(); });
            this.reset();
        }

        render(result = null, failedFees = false) {
            const label = document.createElement('span');
            label.className = 'tx-preview__label';
            label.textContent = this.type.value === 'Sell' ? 'Net Proceeds:' : 'Purchase Cost:';
            const value = document.createElement('span');
            value.className = 'tx-preview__value';
            value.textContent = result ? result.formatted_amount : failedFees ? 'Stored fees unavailable' : '—';
            // Avoid duplicate live announcements from input/change notifications.
            if (this.output.textContent !== label.textContent + value.textContent) this.output.replaceChildren(label, value);
        }

        reset() {
            this.revision++;
            this.request?.abort();
            this.request = null;
            this.retained = null;
            this.feeAction = null;
            this.feesFailed = false;
            this.render();
        }

        refresh() {
            // Record preparation can happen while Bootstrap's modal is already
            // open (and therefore will not emit another shown event).
            if (this.edit && this.active && this.feeAction !== this.form.action) {
                this.request?.abort();
                this.retained = null;
                this.feesFailed = false;
                this.feeAction = this.form.action;
                this.loadFees();
            }
            if (this.fields.some(field => numeric().isComposing(field))) return this.render();
            const [price, quantity, fieldFees] = this.fields.map(field => field.value);
            if (!numeric().classify(price).complete || !numeric().classify(quantity).complete) return this.render();
            let fees = fieldFees;
            if (!fees.trim()) {
                if (this.edit) {
                    if (!this.retained || this.retained.action !== this.form.action) return this.render(null, this.feesFailed);
                    fees = this.retained.fees;
                } else fees = '0';
            }
            this.render(calculate(this.type.value, price, quantity, fees));
        }

        open() {
            this.active = true;
            this.reset();
            this.refresh();
        }

        async loadFees() {
            const action = this.form.action;
            const match = /\/transactions\/edit\/(\d+)$/.exec(action);
            if (!match) return;
            const revision = this.revision;
            const request = new AbortController();
            this.request = request;
            const current = () => revision === this.revision && action === this.form.action && !request.signal.aborted;
            try {
                // One protected read per edit opening, independent of typing.
                const response = await fetch('/transactions/preview', {
                    method: 'POST', credentials: 'same-origin', cache: 'no-store',
                    headers: {'Content-Type': 'application/json', 'Accept': 'application/json',
                        'X-CSRFToken': this.form.querySelector('[name="csrf_token"]').value},
                    body: JSON.stringify({mode: 'retained', transaction_id: match[1]}), signal: request.signal
                });
                const result = await response.json();
                if (!current()) return;
                if (!response.ok || !result.success || !decimal(result.fees)) throw new Error('Unavailable');
                this.retained = {action, fees: result.fees};
                this.refresh(); // Current inputs, never request-time operands.
            } catch (error) {
                if (current()) { this.feesFailed = true; this.refresh(); }
            } finally {
                if (this.request === request) this.request = null;
            }
        }
    }

    window.OnePortfolioPreviews = Object.freeze({
        calculate,
        initialize() {
            for (const [id, edit] of [['transaction_amount_preview', false], ['edit_transaction_amount_preview', true]]) {
                const output = document.getElementById(id);
                const form = output?.closest('form');
                if (form && !controllers.has(form)) controllers.set(form, new Preview(form, output, edit));
            }
        },
        reset(form) { controllers.get(form)?.reset(); }
    });
})();
