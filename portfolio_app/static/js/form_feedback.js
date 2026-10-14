/* Shared validation/feedback lifecycle. This module never sends a request or
   owns an overlay focus trap. Financial rules are registered by main.js;
   account forms retain their server validation and normal POST behavior. */
(() => {
    'use strict';
    const controllers = new WeakMap();
    let nextId = 0;

    function associate(element, id, add) {
        const ids = new Set((element.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean));
        if (add) ids.add(id);
        else ids.delete(id);
        if (ids.size) element.setAttribute('aria-describedby', [...ids].join(' '));
        else element.removeAttribute('aria-describedby');
    }

    class FormController {
        constructor(form) {
            this.form = form;
            this.rules = [];
            this.serverErrors = new Map();
            this.generalMessages = new Map();
            this.session = 0;
            this.pending = false;
            this.modal = form.closest('.modal');
            this.form.noValidate = true;
            this.hydrate();
            this.preserveInitialErrors = this.submitted && Boolean(this.modal);

            form.addEventListener('submit', event => {
                if (this.pending || this.fields().some(field => window.OnePortfolioNumeric?.isComposing(field))) {
                    event.preventDefault();
                    event.stopImmediatePropagation();
                    return;
                }
                this.submitted = true;
                this.clearGeneral('fields');
                // A new submit always asks the server to reconsider its own
                // rules. No client rule can establish server-side acceptance.
                this.serverErrors.clear();
                if (!this.validateAll()) {
                    event.preventDefault();
                    event.stopImmediatePropagation();
                    this.focusErrors();
                }
            });
            for (const type of ['input', 'change']) {
                // Capture also observes existing non-bubbling synthetic updates
                // from date pickers, transaction type buttons, and Max.
                form.addEventListener(type, event => {
                    const session = this.session;
                    // Read settled edits after the numeric target listener.
                    // Ignore provisional/rejected edits and old records.
                    queueMicrotask(() => {
                        if (this.session === session &&
                            !window.OnePortfolioNumeric?.isComposing(event.target) &&
                            !window.OnePortfolioNumeric?.shouldIgnoreEvent(event)) this.correct(event.target);
                    });
                }, true);
            }
            form.addEventListener('reset', event => {
                const session = this.session;
                // Native default values are applied after reset listeners.
                // Rebase numeric state only after that action, and never clear
                // feedback for a cancelled reset or a newly prepared record.
                queueMicrotask(() => {
                    if (!event.defaultPrevented && session === this.session) this.reset();
                });
            });
            if (this.modal) {
                this.modal.addEventListener('show.bs.modal', () => {
                    if (!this.preserveInitialErrors) this.reset();
                });
                this.modal.addEventListener('shown.bs.modal', () => {
                    if (this.preserveInitialErrors) {
                        // Page code may restore values just before show().
                        this.hydrate();
                        this.preserveInitialErrors = false;
                        this.focusErrors();
                    }
                });
                this.modal.addEventListener('hidden.bs.modal', () => this.reset());
            } else if (this.submitted) {
                this.focusErrors();
            }
        }

        fields() {
            return Array.from(this.form.querySelectorAll('input, select, textarea'));
        }

        targets(field) {
            const proxies = Array.from(this.form.querySelectorAll('[data-feedback-for]'))
                .filter(element => element.dataset.feedbackFor === field.id);
            return proxies.length ? proxies : [field];
        }

        canFocus(element) {
            return !element.disabled && element.type !== 'hidden' &&
                element.getAttribute('aria-hidden') !== 'true' &&
                !element.closest('[hidden], .d-none') && element.getClientRects().length > 0;
        }

        feedback(field) {
            if (!field.id) field.id = `form-field-${++nextId}`;
            const id = `${field.id}-error`;
            let node = document.getElementById(id);
            if (!node) {
                node = document.createElement('div');
                node.id = id;
                node.className = 'invalid-feedback';
                node.setAttribute('data-field-error', field.id);
                node.setAttribute('role', 'alert');
                const container = field.closest('[data-field], .mb-3, .field-group, .settings-field') || field.parentElement;
                container.appendChild(node);
            }
            return node;
        }

        setFieldError(field, message, server = false) {
            const node = this.feedback(field);
            node.textContent = String(message);
            node.hidden = false;
            node.classList.add('d-block');
            field.classList.add('is-invalid');
            for (const target of new Set([field, ...this.targets(field)])) {
                target.setAttribute('aria-invalid', 'true');
                associate(target, node.id, true);
            }
            if (server) this.serverErrors.set(field, { value: field.value, message: String(message) });
        }

        clearFieldError(field) {
            const node = document.getElementById(`${field.id}-error`);
            field.classList.remove('is-invalid');
            for (const target of new Set([field, ...this.targets(field)])) {
                target.removeAttribute('aria-invalid');
                if (node) associate(target, node.id, false);
            }
            if (node) {
                node.textContent = '';
                node.classList.remove('d-block');
                node.hidden = true;
            }
            this.serverErrors.delete(field);
        }

        general() {
            let node = this.form.querySelector('[data-form-error]');
            if (!node) {
                node = document.createElement('div');
                node.className = 'alert alert-danger mb-3 d-none';
                node.setAttribute('data-form-error', '');
                node.setAttribute('role', 'alert');
                node.setAttribute('tabindex', '-1');
                node.hidden = true;
                const body = this.form.querySelector('.modal-body') || this.form;
                body.insertBefore(node, body.firstChild);
            }
            return node;
        }

        showGeneral(messages, focus = false, source = 'server') {
            this.generalMessages.set(source, [].concat(messages).filter(Boolean).map(String));
            this.renderGeneral();
            if (focus) this.focusErrors();
        }

        renderGeneral() {
            const node = this.general();
            node.textContent = [...new Set([...this.generalMessages.values()].flat())].join(' ');
            node.hidden = !node.textContent;
            node.classList.toggle('d-none', node.hidden);
        }

        clearGeneral(source) {
            if (source) this.generalMessages.delete(source);
            else this.generalMessages.clear();
            if (this.form.querySelector('[data-form-error]')) this.renderGeneral();
        }

        hydrate() {
            this.serverErrors.clear();
            const summary = this.form.querySelector('[data-form-error]')?.textContent.trim();
            if (summary) this.generalMessages.set('server', [summary]);
            for (const field of this.fields()) {
                const node = document.getElementById(`${field.id}-error`);
                if (node?.textContent.trim()) this.setFieldError(field, node.textContent.trim(), true);
            }
            this.submitted = this.serverErrors.size > 0 || Boolean(this.form.querySelector('[data-form-error]')?.textContent.trim());
        }

        validateField(field) {
            if (field.disabled || field.type === 'hidden') return true;
            const server = this.serverErrors.get(field);
            if (server && server.value === field.value) return false;
            const rule = this.rules.find(candidate =>
                (candidate.getEl ? candidate.getEl(this.form) : this.form.querySelector(candidate.selector)) === field);
            let message = '';
            if (rule) {
                const result = rule.validate(field.value || '', field, this.form);
                if (result?.ok === false) message = result.message || 'Invalid input.';
            } else if (field.validity && !field.validity.valid) {
                // Native constraints are read only after submit; never use
                // reportValidity(), remove required, or reimplement domain rules.
                message = field.validity.valueMissing ? 'This field is required.' : field.validationMessage;
            }
            if (message) this.setFieldError(field, message);
            else this.clearFieldError(field);
            return !message;
        }

        validateAll() {
            let valid = true;
            for (const field of this.fields()) {
                if (!this.validateField(field)) valid = false;
            }
            return valid;
        }

        correct(field) {
            if (!this.submitted || this.preserveInitialErrors || !this.fields().includes(field)) return;
            this.validateField(field);
        }

        applyErrors(errors) {
            // Replace feedback only when an authoritative response arrives.
            // Merely editing inputs or passing client checks cannot resolve
            // a financial/history error from a previous response.
            this.clearErrors();
            this.submitted = true;
            const general = [];
            const fields = [];
            for (const [name, message] of Object.entries(errors)) {
                // Some forms keep a disabled contextual input alongside the
                // editable control with the same name (transfer source).
                const field = this.fields().find(element =>
                    (element.name === name || element.id === name) &&
                    this.targets(element).some(target => this.canFocus(target)));
                if (name !== '__all__' && field) {
                    fields.push([field, message]);
                } else general.push(message);
            }
            for (const [field, message] of fields) {
                // Defensive de-duplication, never classification by wording.
                if (!general.includes(message)) this.setFieldError(field, message, true);
            }
            if (general.length) this.showGeneral(general);
            this.focusErrors();
        }

        focusErrors() {
            // Bootstrap owns containment. Initial POST errors wait for shown;
            // late AJAX responses must never move focus into a closed dialog.
            if (this.modal && !this.modal.classList.contains('show')) return;
            let first = null;
            const inaccessible = [];
            for (const field of this.fields()) {
                if (field.getAttribute('aria-invalid') !== 'true') continue;
                const target = this.targets(field).find(element => this.canFocus(element));
                if (target && !first) first = target;
                if (!target) {
                    inaccessible.push(this.feedback(field).textContent);
                    // Move an unaddressable error, rather than rendering it
                    // beside a hidden control and again in the summary.
                    this.clearFieldError(field);
                }
            }
            if (inaccessible.length) {
                this.showGeneral([...(this.generalMessages.get('fields') || []), ...inaccessible], false, 'fields');
            }
            if (first) first.focus();
            else {
                const node = this.form.querySelector('[data-form-error]');
                if (node?.textContent.trim()) node.focus();
            }
        }

        clearErrors() {
            for (const field of this.fields()) this.clearFieldError(field);
            this.clearGeneral();
        }

        reset() {
            this.session++;
            for (const field of this.fields()) {
                if (window.OnePortfolioNumeric?.state(field)) window.OnePortfolioNumeric.reset(field);
            }
            window.OnePortfolioPreviews?.reset(this.form);
            this.submitted = false;
            this.preserveInitialErrors = false;
            this.clearErrors();
        }
    }

    function register(form, rules) {
        if (!controllers.has(form)) controllers.set(form, new FormController(form));
        const controller = controllers.get(form);
        if (rules) controller.rules = rules;
        return controller;
    }

    // Programmatic record openers call this before prefilling. Bootstrap does
    // not emit another show event when an already-open dialog changes records.
    function prepare(modalId) {
        const form = document.getElementById(modalId)?.querySelector('form');
        if (!form) return;
        const controller = register(form);
        if (!controller.preserveInitialErrors) controller.reset();
    }

    window.OnePortfolioForms = { register, prepare };
    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('form[method="post" i], .modal form').forEach(form => register(form));
    });
})();
