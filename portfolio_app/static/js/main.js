const AppConfig = {
    successDismissDelay: 3000,  // 3 seconds for success messages
    errorDismissDelay: 6000,    // 6 seconds for error messages
    validation: {
        symbolPattern: /^[A-Z0-9][A-Z0-9._\-]{0,19}$/,
        datePattern: /^\d{4}-\d{2}-\d{2}$/
    }
};


const Utils = {
    normalizeSymbol(raw) {
        return String(raw || '').trim().toUpperCase();
    },

    isValidSymbol(raw) {
        const value = this.normalizeSymbol(raw);
        if (!value) return false;
        return AppConfig.validation.symbolPattern.test(value);
    },

    isValidDateYMD(raw) {
        const str = String(raw || '').trim();
        if (!str) return false;

        if (!AppConfig.validation.datePattern.test(str)) return false;

        const [year, month, day] = str.split('-').map(x => parseInt(x, 10));
        const date = new Date(Date.UTC(year, month - 1, day));

        return date.getUTCFullYear() === year &&
               (date.getUTCMonth() + 1) === month &&
               date.getUTCDate() === day;
    },


};


/* Shared client-side pagination presentation. Pages retain ownership of
   their item lists, page size, filtering, and state; this component owns the
   semantic controls and accessible Nova/Tabler presentation only. */
const Pagination = {
    render(container, options) {
        if (!container) return;

        const currentPage = options.currentPage;
        const totalPages = options.totalPages;
        const onPageChange = options.onPageChange;

        container.replaceChildren();
        container.hidden = totalPages <= 1;
        if (totalPages <= 1) return;

        const navigation = document.createElement('nav');
        navigation.className = 'pagination';
        navigation.setAttribute('aria-label', options.label || 'Pagination');

        const appendControl = ({ label, page, icon, current = false, disabled = false }) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'pagination__control' + (icon ? ' pagination__control--icon' : '');
            button.setAttribute('aria-label', label);
            button.disabled = disabled;

            if (current) {
                button.classList.add('is-current');
                button.setAttribute('aria-current', 'page');
            }

            if (icon) {
                button.appendChild(window.OnePortfolioIcons.create(icon));
            } else {
                button.textContent = String(page);
            }

            button.addEventListener('click', () => {
                if (!button.disabled && page !== currentPage) onPageChange(page);
            });
            navigation.appendChild(button);
        };

        appendControl({
            label: 'Previous Page',
            page: currentPage - 1,
            icon: 'chevron-left',
            disabled: currentPage <= 1,
        });

        let windowStart = Math.max(1, currentPage - 1);
        const windowEnd = Math.min(totalPages, windowStart + 2);
        if (windowEnd - windowStart < 2) windowStart = Math.max(1, windowEnd - 2);

        for (let page = windowStart; page <= windowEnd; page += 1) {
            appendControl({
                label: `Page ${page}`,
                page,
                current: page === currentPage,
            });
        }

        appendControl({
            label: 'Next Page',
            page: currentPage + 1,
            icon: 'chevron-right',
            disabled: currentPage >= totalPages,
        });

        container.appendChild(navigation);
    },
};

window.OnePortfolioPagination = Object.freeze(Pagination);

function todayStr() {
    const d = new Date();
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}

function browserTimeZone() {
    try {
        return Intl.DateTimeFormat().resolvedOptions().timeZone || '';
    } catch (e) {
        return '';
    }
}

function applyBrowserTimeZone(root) {
    const scope = root || document;
    const tz = browserTimeZone();
    scope.querySelectorAll('input[name="user_timezone"]').forEach(function(input) {
        input.value = tz;
    });
}

class ActionMenuManager {
    static nextId = 0;

    constructor(root) {
        if (!window.bootstrap || !window.bootstrap.Dropdown) return;

        const scope = root || document;
        scope.querySelectorAll('.action-menu__trigger').forEach(function(trigger) {
            if (trigger.dataset.menuMounted) return;
            const menu = trigger.closest('.action-menu').querySelector('.action-menu__menu');
            if (!menu) return;
            trigger.dataset.menuMounted = 'true';
            const dropdown = window.bootstrap.Dropdown.getOrCreateInstance(trigger, {
                boundary: 'viewport',
                popperConfig: function(defaultConfig) {
                    return Object.assign({}, defaultConfig, { strategy: 'fixed' });
                }
            });
            const id = ++ActionMenuManager.nextId;
            trigger.id = trigger.id || 'action-trigger-' + id;
            menu.id = menu.id || 'action-menu-' + id;
            trigger.setAttribute('aria-haspopup', 'menu');
            trigger.setAttribute('aria-controls', menu.id);
            menu.setAttribute('role', 'menu');
            menu.setAttribute('aria-labelledby', trigger.id);
            menu.querySelectorAll('li').forEach(item => item.setAttribute('role', 'none'));
            menu.querySelectorAll('.dropdown-divider').forEach(item => item.setAttribute('role', 'separator'));
            menu.querySelectorAll('.dropdown-item').forEach(item => {
                item.setAttribute('role', 'menuitem');
                item.tabIndex = -1;
            });
            const items = () => Array.from(menu.querySelectorAll('.dropdown-item')).filter(item =>
                !item.disabled && !item.classList.contains('disabled') &&
                item.getAttribute('aria-disabled') !== 'true' && item.getClientRects().length);
            trigger.addEventListener('keydown', event => {
                if (!['Enter', ' '].includes(event.key) || trigger.disabled) return;
                event.preventDefault();
                dropdown.show();
                const first = items()[0];
                if (first) first.focus();
            });
            let search = '';
            let lastKeyAt = 0;
            trigger.addEventListener('hidden.bs.dropdown', () => { search = ''; });
            menu.addEventListener('keydown', event => {
                // Bootstrap alone owns arrows, Escape and Tab dismissal.
                if (event.altKey || event.ctrlKey || event.metaKey || event.isComposing ||
                    event.target.matches('input, textarea, select')) return;
                const choices = items();
                if (!choices.length) return;
                let next;
                if (event.key === 'Home') next = choices[0];
                else if (event.key === 'End') next = choices[choices.length - 1];
                else if (event.key.length === 1 && event.key !== ' ') {
                    const now = Date.now();
                    search = now - lastKeyAt > 700 ? event.key.toLowerCase() : search + event.key.toLowerCase();
                    lastKeyAt = now;
                    const query = Array.from(search).every(letter => letter === search[0]) ? search[0] : search;
                    const start = choices.indexOf(document.activeElement);
                    const ordered = choices.slice(start + 1).concat(choices.slice(0, start + 1));
                    next = ordered.find(item => item.textContent.trim().toLowerCase().startsWith(query));
                } else return;
                event.preventDefault();
                if (next) next.focus();
            });
        });
    }
}

document.addEventListener('DOMContentLoaded', function() {
    applyBrowserTimeZone(document);
});

document.addEventListener('submit', function(ev) {
    if (ev.target && ev.target.querySelectorAll) {
        applyBrowserTimeZone(ev.target);
    }
}, true);

function initDateField(el) {
    if (!el || el._flatpickr || !window.flatpickr) return null;

    const currentValue = el.value;
    if (el.type === 'date') {
        el.dataset.nativeType = 'date';
        el.type = 'text';
    }

    const modal = el.closest('.modal');
    const positionInModal = function(fp) {
        const calendar = fp.calendarContainer;
        const bounds = el.getBoundingClientRect();
        const container = modal.getBoundingClientRect();
        const height = calendar.offsetHeight;
        const width = calendar.offsetWidth;
        const above = bounds.bottom + height + 8 > window.innerHeight && bounds.top > height;
        const top = Math.max(8, Math.min(above ? bounds.top - height - 2 : bounds.bottom + 2,
            window.innerHeight - height - 8));
        const left = Math.max(8, Math.min(bounds.left, document.documentElement.clientWidth - width - 8));
        calendar.style.top = (top - container.top + modal.scrollTop) + 'px';
        calendar.style.left = (left - container.left + modal.scrollLeft) + 'px';
        calendar.style.right = 'auto';
    };
    const instance = window.flatpickr(el, {
        dateFormat: 'Y-m-d',
        shorthandCurrentMonth: true,
        allowInput: true,
        clickOpens: !el.disabled && !el.readOnly,
        appendTo: modal || document.body,
        position: modal ? positionInModal : 'auto',
        disableMobile: true,
        static: false,
        prevArrow: '<svg class="icon" aria-hidden="true"><use href="#op-icon-chevron-left"></use></svg>',
        nextArrow: '<svg class="icon" aria-hidden="true"><use href="#op-icon-chevron-right"></use></svg>',
        onReady: function(selectedDates, dateStr, fp) {
            fp.calendarContainer.classList.add('op-flatpickr');
        }
    });

    if (modal) {
        // Keep the calendar inside Bootstrap's existing trap, outside the
        // scrolling form. Flatpickr remains the date/selection owner.
        modal.addEventListener('scroll', event => {
            if (!instance.isOpen || instance.calendarContainer.contains(event.target)) return;
            if (instance.calendarContainer.contains(document.activeElement)) el.focus();
            instance.close();
        }, true);
        modal.addEventListener('keydown', event => {
            if (event.key !== 'Escape' || !instance.isOpen ||
                (event.target !== el && !instance.calendarContainer.contains(event.target))) return;
            event.preventDefault();
            event.stopPropagation();
            el.focus();
            instance.close();
        }, true);
    }

    if (currentValue && el.value !== currentValue) {
        el.value = currentValue;
    }

    return instance;
}

function initDateFields(root) {
    const scope = root || document;
    scope.querySelectorAll('[data-datepicker="flatpickr"]').forEach(initDateField);
}

function closeDatePickers(root) {
    const scope = root || document;
    scope.querySelectorAll('[data-datepicker="flatpickr"]').forEach(function(el) {
        if (el._flatpickr) el._flatpickr.close();
    });
}

class AlertManager {
    constructor() {
        this.initialize();
    }

    initialize() {
        // Show any pending flash message from sessionStorage (set by AJAX handlers)
        const pendingMsg = sessionStorage.getItem('flashMessage');
        const pendingType = sessionStorage.getItem('flashType') || 'success';
        if (pendingMsg) {
            sessionStorage.removeItem('flashMessage');
            sessionStorage.removeItem('flashType');
            if (window.showToast) {
                window.showToast(pendingMsg, pendingType);
            } else {
                this.showAlert(pendingMsg, pendingType);
            }
        }

        // Auto-dismiss existing server-rendered alerts (skip alerts inside modals)
        document.querySelectorAll('.alert:not(.alert-info):not(.alert-warning)').forEach(alert => {
            if (alert.closest('.modal') || alert.hasAttribute('data-form-error')) return;
            const isError = alert.classList.contains('alert-danger');
            const delay = isError ? AppConfig.errorDismissDelay : AppConfig.successDismissDelay;
            setTimeout(() => {
                try {
                    const bsAlert = new bootstrap.Alert(alert);
                    bsAlert.close();
                } catch (e) {}
            }, delay);
        });
    }

    showAlert(message, type = 'success') {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
        alertDiv.setAttribute('role', 'alert');
        alertDiv.innerHTML = `
            ${Utils.escapeHtml(message)}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;

        const container = document.querySelector('.container') || document.body;
        container.insertBefore(alertDiv, container.firstChild);

        const delay = type === 'danger' ? AppConfig.errorDismissDelay : AppConfig.successDismissDelay;
        setTimeout(() => {
            alertDiv.classList.remove('show');
            setTimeout(() => alertDiv.remove(), 150);
        }, delay);
    }

}

class TooltipManager {
    constructor() {
        this.initialize();
    }

    initialize() {
        const tooltipElements = document.querySelectorAll('[data-bs-toggle="tooltip"]');

        tooltipElements.forEach(element => {
            try {
                // `getOrCreateInstance`, never `new`. Constructing a second
                // Tooltip over the same element does not replace the first:
                // Bootstrap overwrites its own instance map, but the orphan
                // keeps every listener it attached, so the element ends up
                // with two live tooltips whose show/hide state can drift
                // apart. The first one also moves `title` into
                // `data-bs-original-title`, so the second reads an empty
                // title and which of the two actually renders is incidental.
                //
                // This is the one place tooltips are mounted. Templates must
                // not mount their own — see `TooltipManager` in the design
                // notes.
                bootstrap.Tooltip.getOrCreateInstance(element);
            } catch (e) {
                // Ignore tooltip initialization errors
            }
        });
    }
}

const ValidationRules = {
    // Funds validation rules
    fundsAmount: {
        name: 'amount_delta',
        validate: (raw) => {
            const parsed = window.OnePortfolioNumeric.classify(raw);
            if (!parsed.complete) {
                return { ok: false, message: 'This field is required.' };
            }
            if (parsed.negative || parsed.zero) {
                return { ok: false, message: 'Must be more than 0.' };
            }
            return { ok: true };
        }
    },

    // Portfolio dropdown selection
    portfolioSelect: {
        name: 'portfolio_id',
        validate: (raw) => {
            if (!String(raw || '').trim()) {
                return { ok: false, message: 'Please select a portfolio.' };
            }
            return { ok: true };
        }
    },

    // Non-empty text field (used for portfolio name)
    requiredText: {
        name: 'text',
        validate: (raw) => {
            if (!String(raw || '').trim()) {
                return { ok: false, message: 'This field is required.' };
            }
            return { ok: true };
        }
    },

    // Ticker symbol
    symbol: {
        name: 'symbol',
        validate: (raw, element) => {
            const value = Utils.normalizeSymbol(raw);
            if (element) element.value = value;

            if (!value) {
                return { ok: false, message: 'This field is required.' };
            }
            if (!Utils.isValidSymbol(value)) {
                return { ok: false, message: 'Invalid asset symbol format.' };
            }
            return { ok: true };
        }
    },

    // Transaction type
    transactionType: {
        name: 'transaction_type',
        validate: (raw) => {
            const value = String(raw || '').trim();
            if (!value) {
                return { ok: false, message: 'Select an entry type.' };
            }
            return { ok: true };
        }
    },

    // Price validation
    price: {
        name: 'price',
        validate: (raw) => {
            const parsed = window.OnePortfolioNumeric.classify(raw);
            if (!parsed.complete) {
                return { ok: false, message: 'This field is required.' };
            }
            if (parsed.negative || parsed.zero) {
                return { ok: false, message: 'Must be more than 0.' };
            }
            return { ok: true };
        }
    },

    // Quantity validation
    quantity: {
        name: 'quantity',
        validate: (raw) => {
            const parsed = window.OnePortfolioNumeric.classify(raw);
            if (!parsed.complete) {
                return { ok: false, message: 'This field is required.' };
            }
            if (parsed.negative || parsed.zero) {
                return { ok: false, message: 'Must be more than 0.' };
            }
            return { ok: true };
        }
    },

    // Fees validation (optional, non-negative)
    fees: {
        name: 'fees',
        validate: (raw) => {
            const str = String(raw || '').trim();
            if (!str) return { ok: true };

            const parsed = window.OnePortfolioNumeric.classify(str);
            if (!parsed.complete) {
                return { ok: false, message: 'Invalid fees.' };
            }
            if (parsed.negative) {
                return { ok: false, message: 'Non-negative number required.' };
            }
            return { ok: true };
        }
    },

    /**
     * Wrap a rule's validate to skip when transaction type is not selected
     */
    requiresTransactionType(baseRule) {
        return (raw) => {
            const typeEl = document.getElementById('transaction_type');
            if (!typeEl || !String(typeEl.value || '').trim()) {
                return { ok: true };
            }
            return baseRule.validate(raw);
        };
    },

    // Date validation
    date: {
        name: 'date',
        validate: (raw) => {
            const str = String(raw || '').trim();
            if (!str) {
                return { ok: false, message: 'This field is required.' };
            }
            if (!Utils.isValidDateYMD(str)) {
                return { ok: false, message: 'Invalid date.' };
            }
            return { ok: true };
        }
    }
};

class FormValidatorsInitializer {
    constructor() {
        this.initializeAllValidators();
    }

    initializeAllValidators() {
        // Deposit funds modal
        this.initValidator('#depositFundsForm', [
            { ...ValidationRules.fundsAmount, selector: '#add_funds_amount' },
            { ...ValidationRules.date, selector: '#deposit_date', name: 'deposit_date' }
        ]);

        // Withdraw funds modal
        this.initValidator('#withdrawFundsForm', [
            { ...ValidationRules.fundsAmount, selector: '#withdraw_funds_amount' },
            { ...ValidationRules.date, selector: '#withdraw_date', name: 'withdraw_date' }
        ]);

        // New portfolio form — only requires a non-empty name
        this.initValidator('form[action$="/portfolios/add"]', [
            { ...ValidationRules.requiredText, selector: '#portfolio_name', name: 'name' }
        ]);

        // Edit portfolio cash event
        this.initValidator('#editPortfolioEventForm', [
            { ...ValidationRules.date, selector: '#edit_event_date' },
            { ...ValidationRules.fundsAmount, selector: '#edit_cash_event_amount', name: 'amount' }
        ]);

        // Track a new symbol
        this.initValidator('form[action$="/symbols/add"]', [
            { ...ValidationRules.portfolioSelect, selector: '#symbol_portfolio_id', name: 'portfolio_id' },
            { ...ValidationRules.symbol, selector: '#symbol_ticker' }
        ]);

        // Buy/Sell and dividends have separate forms and validation contracts.
        this.initValidator('form[action$="/transactions/add"]', [
            { ...ValidationRules.portfolioSelect, selector: '#portfolio_id' },
            { ...ValidationRules.symbol, selector: '#symbol' },
            { ...ValidationRules.transactionType, selector: '#transaction_type' },
            { ...ValidationRules.price, selector: '#price', validate: ValidationRules.requiresTransactionType(ValidationRules.price) },
            { ...ValidationRules.quantity, selector: '#quantity', validate: ValidationRules.requiresTransactionType(ValidationRules.quantity) },
            { ...ValidationRules.fees, selector: '#fees', validate: ValidationRules.requiresTransactionType(ValidationRules.fees) },
            { ...ValidationRules.date, selector: '#add_tx_date' }
        ]);
        this.initValidator('#transferForm', [
            { ...ValidationRules.fundsAmount, selector: '#transfer_amount', name: 'amount' }
        ]);

        // Edit transaction
        this.initValidator('#editTransactionForm', [
            { ...ValidationRules.price, selector: '#edit_price' },
            { ...ValidationRules.quantity, selector: '#edit_quantity' },
            { ...ValidationRules.fees, selector: '#edit_fees' },
            { ...ValidationRules.date, selector: '#edit_date' }
        ]);

        // Standalone Add Dividends modal (separate from addTransactionModal).
        // Without this, the amount field had no client-side rule and zero
        // entries only got caught at the server with a different message.
        this.initValidator('form[action$="/dividends/add"]', [
            { ...ValidationRules.fundsAmount, selector: '#add_div_amount', name: 'amount' },
            { ...ValidationRules.date, selector: '#add_div_date' }
        ]);

        // Edit Dividend modal
        this.initValidator('#editDividendForm', [
            { ...ValidationRules.fundsAmount, selector: '#edit_amount', name: 'edit_amount' },
            { ...ValidationRules.date, selector: '#edit_dividend_date', name: 'edit_date' }
        ]);
    }

    initValidator(formSelector, rules) {
        const formElement = document.querySelector(formSelector);
        if (formElement) {
            window.OnePortfolioForms.register(formElement, rules);
        }
    }
}

/**
 * Live character counter for `.js-notes-input` textareas. Turns red within
 * 30 chars of (or at) the maxlength cap. Browser enforces the hard stop.
 */
class NotesCounterHandler {
    constructor() {
        this.DANGER_THRESHOLD = 30;
        this.init();
    }

    init() {
        document.querySelectorAll('.js-notes-input').forEach(el => this.update(el));

        document.addEventListener('input', (e) => {
            if (e.target.classList && e.target.classList.contains('js-notes-input')) {
                this.update(e.target);
            }
        });

        document.addEventListener('shown.bs.modal', (e) => {
            e.target.querySelectorAll('.js-notes-input').forEach(el => this.update(el));
        });
    }

    update(textarea) {
        const counter = textarea.nextElementSibling;
        if (!counter || !counter.classList.contains('notes-counter')) return;
        const max = parseInt(textarea.getAttribute('maxlength'), 10) || 0;
        const len = textarea.value.length;
        counter.textContent = `${len} / ${max}`;
        counter.classList.toggle('is-danger', max > 0 && (max - len) <= this.DANGER_THRESHOLD);
    }
}


/**
 * Handle AJAX form submissions for modals.
 *
 * Server replies use one of two shapes:
 *   {success: true, message: "..."}  → success toast + reload
 *   {success: false, errors: {field: "msg", ..., __all__: "msg"}}
 *                                    → per-field inline errors + modal banner
 *   {success: false, error: "..."}    → legacy single-string fallback
 */
class ModalAjaxHandler {
    constructor() {
        this.init();
    }

    init() {
        // Every modal that has a form goes through here. Adding a new
        // modal? List it here and the AJAX path is wired automatically;
        // no need to write per-form JS.
        const modalForms = [
            { modalId: 'addTransactionModal',       formSelector: '#addTransactionModal form' },
            { modalId: 'editTransactionModal',      formSelector: '#editTransactionForm' },
            { modalId: 'addDividendModal',          formSelector: 'form[action$="/dividends/add"]' },
            { modalId: 'editDividendModal',         formSelector: '#editDividendForm' },
            { modalId: 'newPortfolioModal',         formSelector: 'form[action$="/portfolios/add"]' },
            { modalId: 'renamePortfolioModal',      formSelector: '#renamePortfolioForm' },
            { modalId: 'depositFundsModal',         formSelector: '#depositFundsForm' },
            { modalId: 'withdrawFundsModal',        formSelector: '#withdrawFundsForm' },
            { modalId: 'transferModal',             formSelector: '#transferForm' },
            { modalId: 'deleteTransferModal',       formSelector: '#deleteTransferForm' },
            { modalId: 'editPortfolioEventModal',   formSelector: '#editPortfolioEventForm' },
            { modalId: 'addSymbolModal',            formSelector: 'form[action$="/symbols/add"]' },
            // Delete-confirm dialogs share this owner so every workflow uses
            // the same modal-body error banner and submit lifecycle.
            { modalId: 'deletePortfolioEventModal', formSelector: '#deletePortfolioEventForm' },
            { modalId: 'deletePortfolioModal',      formSelector: '#deletePortfolioForm' },
            { modalId: 'deleteTransactionModal',    formSelector: '#deleteTransactionForm' },
            { modalId: 'deleteSymbolModal',         formSelector: '#deleteSymbolForm' },
            { modalId: 'deleteDividendModal',       formSelector: '#deleteDividendForm' },
        ];

        modalForms.forEach(({ modalId, formSelector }) => {
            const form = document.querySelector(formSelector);
            const modal = document.getElementById(modalId);
            if (form && modal) {
                this.handleForm(form, modal);
            }
        });
    }

    handleForm(form, modal) {
        const feedback = window.OnePortfolioForms.register(form);
        form.addEventListener('submit', async (event) => {
            event.preventDefault();
            feedback.pending = true;
            const session = feedback.session;
            const submitBtn = form.querySelector('button[type="submit"]');
            const originalText = submitBtn ? submitBtn.innerHTML : '';
            const originallyDisabled = submitBtn ? submitBtn.disabled : false;
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Processing...';
            }

            try {
                const formData = new FormData(form);
                const response = await fetch(form.action, {
                    method: 'POST',
                    headers: { 'X-Requested-With': 'XMLHttpRequest' },
                    body: formData
                });
                const data = await response.json();
                if (data.success) {
                    if (feedback.session === session) feedback.clearErrors();
                    // Reflect successful financial mutations even after closing.
                    sessionStorage.setItem('flashMessage', data.message || 'Success');
                    sessionStorage.setItem('flashType', 'success');
                    window.location.reload();
                    return;
                }
                if (feedback.session !== session) return;
                if (data.errors && typeof data.errors === 'object' && Object.keys(data.errors).length) {
                    feedback.applyErrors(data.errors);
                } else {
                    feedback.applyErrors({__all__: data.message || data.error || "We couldn't save your changes. Please try again."});
                }
            } catch (error) {
                console.error('Form submission error:', error);
                if (feedback.session === session) {
                    feedback.showGeneral('Network error', false, 'request');
                    feedback.focusErrors();
                }
            } finally {
                feedback.pending = false;
                if (submitBtn) {
                    submitBtn.disabled = originallyDisabled;
                    submitBtn.innerHTML = originalText;
                }
            }
        });
    }

}


class InvestmentPortfolioApp {
    constructor() {
        this.initialize();
    }

    initialize() {
        document.querySelectorAll('[data-numeric="decimal"]').forEach(field => window.OnePortfolioNumeric.register(field));
        new ActionMenuManager(document);
        initDateFields(document);
        new AlertManager();
        new TooltipManager();
        new FormValidatorsInitializer();
        window.OnePortfolioPreviews.initialize();
        new ModalAjaxHandler();
        new NotesCounterHandler();

        document.querySelectorAll('.modal').forEach(modal => {
            modal.addEventListener('shown.bs.modal', () => initDateFields(modal));
            modal.addEventListener('hidden.bs.modal', () => closeDatePickers(modal));
        });
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new InvestmentPortfolioApp();
});
