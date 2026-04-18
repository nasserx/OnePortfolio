

const AppConfig = {
    successDismissDelay: 3000,  // 3 seconds for success messages
    errorDismissDelay: 6000,    // 6 seconds for error messages
    validation: {
        symbolPattern: /^[A-Z0-9][A-Z0-9._\-]{0,19}$/,
        numberPattern: /^[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?$/,
        datePattern: /^\d{4}-\d{2}-\d{2}$/
    },
    currency: {
        locale: 'en-US',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }
};


const Utils = {
    /**
     * Sanitize decimal input to allow only valid decimal numbers
     */
    sanitizeDecimalInput(value) {
        const raw = String(value || '');
        let output = '';
        let dotSeen = false;
        
        for (const char of raw) {
            if (char >= '0' && char <= '9') {
                output += char;
            } else if (char === '.' && !dotSeen) {
                output += char;
                dotSeen = true;
            }
        }
        
        return output;
    },

    /**
     * Normalize stock symbol to uppercase
     */
    normalizeSymbol(raw) {
        return String(raw || '').trim().toUpperCase();
    },

    /**
     * Format number as money
     */
    formatMoney(value) {
        if (!Number.isFinite(value)) return '0.00';
        return value.toLocaleString(
            AppConfig.currency.locale,
            {
                minimumFractionDigits: AppConfig.currency.minimumFractionDigits,
                maximumFractionDigits: AppConfig.currency.maximumFractionDigits
            }
        );
    },

    /**
     * Validate stock symbol format
     */
    isValidSymbol(raw) {
        const value = this.normalizeSymbol(raw);
        if (!value) return false;
        return AppConfig.validation.symbolPattern.test(value);
    },

    /**
     * Parse number strictly (reject invalid formats)
     */
    parseNumberStrict(raw) {
        const str = String(raw || '').trim();
        if (!str) return { ok: false, value: null };
        
        if (!AppConfig.validation.numberPattern.test(str)) {
            return { ok: false, value: null };
        }
        
        const num = Number(str);
        if (!Number.isFinite(num)) {
            return { ok: false, value: null };
        }
        
        return { ok: true, value: num };
    },

    /**
     * Validate date in YYYY-MM-DD format
     */
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

    /**
     * Convert exponential notation to plain decimal string
     */
    toPlainDecimalString(numStr) {
        if (!numStr || typeof numStr !== 'string') return numStr;
        if (!/[eE]/.test(numStr)) return numStr;

        const parts = numStr.toLowerCase().split('e');
        if (parts.length !== 2) return numStr;

        let coefficient = parts[0];
        const exponent = parseInt(parts[1], 10);
        if (!Number.isFinite(exponent)) return numStr;

        let sign = '';
        if (coefficient.startsWith('-')) {
            sign = '-';
            coefficient = coefficient.slice(1);
        } else if (coefficient.startsWith('+')) {
            coefficient = coefficient.slice(1);
        }

        if (!coefficient) return numStr;

        const coeffParts = coefficient.split('.');
        const intPart = coeffParts[0] || '0';
        const fracPart = coeffParts[1] || '';

        const intPartNormalized = intPart.replace(/^0+(?=\d)/, '');
        const digits = (intPartNormalized + fracPart).replace(/^0+(?=\d)/, '') || '0';

        const decimalIndex = intPartNormalized.length;
        const newIndex = decimalIndex + exponent;

        if (exponent >= 0) {
            if (newIndex >= digits.length) {
                return sign + digits.padEnd(newIndex, '0');
            }
            const left = digits.slice(0, newIndex) || '0';
            const right = digits.slice(newIndex);
            return sign + left + (right ? ('.' + right) : '');
        }

        if (newIndex <= 0) {
            return sign + '0.' + '0'.repeat(-newIndex) + digits;
        }

        return sign + digits.slice(0, newIndex) + '.' + digits.slice(newIndex);
    },

    /**
     * Find field container element
     */
    findFieldContainer(element) {
        return element.closest('.mb-3') || 
               element.closest('.form-group') || 
               element.parentElement;
    },

    /**
     * Get or create feedback element for validation
     */
    ensureFeedbackElement(inputElement) {
        const container = this.findFieldContainer(inputElement);
        if (!container) return null;

        let feedback = container.querySelector('.invalid-feedback');
        if (!feedback) {
            feedback = document.createElement('div');
            feedback.className = 'invalid-feedback';
            container.appendChild(feedback);
        }
        return feedback;
    },

    /**
     * Escape HTML special characters to prevent XSS
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
};

class CSRFManager {
    constructor() {
        this.token = this.getTokenFromMeta();
    }

    getTokenFromMeta() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? (meta.getAttribute('content') || '') : '';
    }

    injectTokenToForms() {
        if (!this.token) return;

        document.querySelectorAll('form[method="post"], form[method="POST"]')
            .forEach(form => {
                if (form.querySelector('input[name="csrf_token"]')) return;
                
                const input = document.createElement('input');
                input.type = 'hidden';
                input.name = 'csrf_token';
                input.value = this.token;
                form.insertBefore(input, form.firstChild);
            });
    }
}

class FormValidator {
    constructor(formElement, rules) {
        this.form = formElement;
        this.rules = rules;
        this.touched = new Set();
        this.submittedOnce = false;
        
        if (this.form) {
            this.initialize();
        }
    }

    initialize() {
        this.disableNativeValidation();
        this.attachFieldListeners();
        this.attachSubmitListener();
        this.hideFeedbackPlaceholders();
    }

    disableNativeValidation() {
        this.form.noValidate = true;
        this.form.setAttribute('novalidate', 'novalidate');
    }

    shouldShowError(fieldName) {
        return this.submittedOnce || this.touched.has(fieldName);
    }

    getFieldElement(rule) {
        if (rule.getEl) {
            return rule.getEl(this.form);
        }
        return rule.selector ? this.form.querySelector(rule.selector) : null;
    }

    validateRule(rule) {
        const element = this.getFieldElement(rule);
        if (!element) return { ok: true };

        const rawValue = (element.value != null) ? element.value : '';
        const result = rule.validate(rawValue, element, this.form);

        if (result && result.ok === false) {
            return {
                ok: false,
                message: result.message || 'Invalid input.',
                element
            };
        }

        return { ok: true, element };
    }

    validateFieldByName(fieldName) {
        const rule = this.rules.find(r => r.name === fieldName);
        if (!rule) return true;

        const result = this.validateRule(rule);
        
        if (!this.shouldShowError(fieldName)) {
            return result.ok;
        }

        if (!result.ok) {
            this.setFieldError(result.element, result.message);
        } else {
            this.clearFieldError(result.element);
        }

        return result.ok;
    }

    validateAll() {
        let firstInvalidField = null;
        let allValid = true;

        for (const rule of this.rules) {
            const result = this.validateRule(rule);
            
            if (!result.ok) {
                allValid = false;
                if (!firstInvalidField) {
                    firstInvalidField = result;
                }
                
                if (this.shouldShowError(rule.name)) {
                    this.setFieldError(result.element, result.message);
                }
            } else {
                if (this.shouldShowError(rule.name)) {
                    this.clearFieldError(result.element);
                }
            }
        }

        if (!allValid && firstInvalidField && firstInvalidField.element) {
            this.focusElement(firstInvalidField.element);
        }

        return allValid;
    }

    setFieldError(inputElement, message) {
        if (!inputElement) return;
        
        inputElement.classList.add('is-invalid');
        const feedback = Utils.ensureFeedbackElement(inputElement);
        
        if (feedback) {
            feedback.textContent = String(message || 'Invalid input.');
            feedback.style.display = 'block';
        }
    }

    clearFieldError(inputElement) {
        if (!inputElement) return;
        
        inputElement.classList.remove('is-invalid');
        const feedback = Utils.ensureFeedbackElement(inputElement);
        
        if (feedback) {
            feedback.textContent = '';
            feedback.style.display = 'none';
        }
    }

    focusElement(element) {
        if (typeof element.focus === 'function') {
            try {
                element.focus();
            } catch (e) {
                // Ignore focus errors
            }
        }
    }

    attachFieldListeners() {
        for (const rule of this.rules) {
            const element = this.getFieldElement(rule);
            if (!element) continue;

            element.addEventListener('blur', () => {
                this.touched.add(rule.name);
                this.validateFieldByName(rule.name);
            });

            element.addEventListener('input', () => {
                if (this.touched.has(rule.name) || this.submittedOnce) {
                    this.validateFieldByName(rule.name);
                }
            });

            element.addEventListener('change', (event) => {
                if (event && event.isTrusted) {
                    this.touched.add(rule.name);
                }
                if (this.touched.has(rule.name) || this.submittedOnce) {
                    this.validateFieldByName(rule.name);
                }
            });
        }
    }

    attachSubmitListener() {
        this.form.addEventListener('submit', (event) => {
            this.submittedOnce = true;
            
            if (!this.validateAll()) {
                event.preventDefault();
                event.stopImmediatePropagation();
            }
        });
    }

    hideFeedbackPlaceholders() {
        for (const rule of this.rules) {
            const element = this.getFieldElement(rule);
            if (!element) continue;

            const feedback = Utils.ensureFeedbackElement(element);
            
            if (feedback && 
                !feedback.textContent.trim() && 
                !element.classList.contains('is-invalid')) {
                feedback.style.display = 'none';
            }
        }
    }
}

class DecimalInputHandler {
    static SELECTOR = 'input[type="number"], input[inputmode="decimal"]';

    constructor() {
        this.initialize();
    }

    initialize() {
        this.attachSanitization();
        this.attachFormatting();
        this.disableSpinners();
    }

    attachSanitization() {
        document.querySelectorAll('input[inputmode="decimal"]')
            .forEach(element => {
                element.addEventListener('input', () => {
                    const sanitized = Utils.sanitizeDecimalInput(element.value);
                    if (sanitized !== element.value) {
                        element.value = sanitized;
                    }
                });
            });
    }

    attachFormatting() {
        const numberInputs = document.querySelectorAll(DecimalInputHandler.SELECTOR);

        numberInputs.forEach(input => {
            // Select all on focus
            input.addEventListener('focus', function() {
                this.select();
            });

            // Normalize exponential notation
            const normalizeDisplay = () => {
                const value = String(input.value || '');
                if (!/[eE]/.test(value)) return;
                
                const plain = Utils.toPlainDecimalString(value);
                if (plain && plain !== value) {
                    input.value = plain;
                }
            };

            input.addEventListener('input', normalizeDisplay);
            input.addEventListener('change', normalizeDisplay);
            input.addEventListener('blur', normalizeDisplay);
        });
    }

    disableSpinners() {
        const numberInputs = document.querySelectorAll(DecimalInputHandler.SELECTOR);

        numberInputs.forEach(input => {
            // Prevent arrow key stepping
            input.addEventListener('keydown', (event) => {
                if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
                    event.preventDefault();
                }
            });

            // Prevent mouse wheel stepping
            input.addEventListener('wheel', (event) => {
                if (document.activeElement === input) {
                    event.preventDefault();
                }
            }, { passive: false });
        });
    }
}

class TransactionFormHandler {
    constructor() {
        this.form = document.querySelector('form[action$="/transactions/add"]');
        this.priceInput = document.getElementById('price');
        this.quantityInput = document.getElementById('quantity');
        this.feesInput = document.getElementById('fees');
        this.typeInput = document.getElementById('transaction_type');
        this.preview = document.getElementById('total_cost_preview');
        
        if (this.form && this.preview) {
            this.initialize();
        }
    }

    initialize() {
        this.attachPreviewCalculation();
        this.enforceTypeSelection();
        this.attachBuySelectors();
    }

    calculateTotal() {
        const price = parseFloat(this.priceInput.value) || 0;
        const quantity = parseFloat(this.quantityInput.value) || 0;
        const fees = parseFloat(this.feesInput.value) || 0;
        
        const gross = price * quantity;
        const isSell = (this.typeInput && this.typeInput.value === 'Sell');
        const total = isSell ? (gross - fees) : (gross + fees);
        
        const hasType = Boolean(
            this.typeInput && String(this.typeInput.value || '').trim()
        );
        
        if (!hasType) {
            this.preview.textContent = '';
            return;
        }

        const formatted = Utils.formatMoney(total);
        this.preview.innerHTML = isSell
            ? `Total Received: <span class="tx-preview-amount">${formatted}</span>`
            : `Total Spent: <span class="tx-preview-amount">${formatted}</span>`;
    }

    attachPreviewCalculation() {
        ['input', 'change'].forEach(eventType => {
            this.priceInput?.addEventListener(eventType, () => this.calculateTotal());
            this.quantityInput?.addEventListener(eventType, () => this.calculateTotal());
            this.feesInput?.addEventListener(eventType, () => this.calculateTotal());
            this.typeInput?.addEventListener(eventType, () => this.calculateTotal());
        });

        this.calculateTotal();
    }

    enforceTypeSelection() {
        if (!this.typeInput) return;

        // Clear the type error once a valid type is selected
        this.typeInput.addEventListener('change', () => {
            if (String(this.typeInput.value || '').trim()) {
                const validator = new FormValidator(this.form, []);
                validator.clearFieldError(this.typeInput);
            }
        });
    }

    attachBuySelectors() {
        const buyButton = document.getElementById('add_tx_type_buy_btn');
        const sellButton = document.getElementById('add_tx_type_sell_btn');
        
        const triggerChange = () => {
            try {
                this.typeInput?.dispatchEvent(new Event('change'));
            } catch (e) {
                // Ignore
            }
        };

        buyButton?.addEventListener('click', triggerChange);
        sellButton?.addEventListener('click', triggerChange);
    }
}

class ModalManager {
    constructor() {
        this.initialize();
    }

    initialize() {
        this.markUserOpenedModals();
        this.clearErrorsOnModalEvents();
    }

    markUserOpenedModals() {
        document.addEventListener('click', (event) => {
            const trigger = event.target?.closest?.(
                '[data-bs-toggle="modal"],[data-bs-target]'
            );
            
            if (!trigger) return;

            const targetSelector = trigger.getAttribute('data-bs-target');
            if (!targetSelector) return;

            const modalElement = document.querySelector(targetSelector);
            if (modalElement) {
                modalElement.dataset.clearOnOpen = '1';
            }
        });
    }

    clearErrorsOnModalEvents() {
        document.querySelectorAll('.modal').forEach(modalElement => {
            modalElement.addEventListener('hidden.bs.modal', () => {
                this.clearModalErrors(modalElement);
            });

            modalElement.addEventListener('show.bs.modal', () => {
                if (modalElement.dataset.clearOnOpen === '1') {
                    this.clearModalErrors(modalElement);
                    delete modalElement.dataset.clearOnOpen;
                }
            });
        });
    }

    clearModalErrors(modalElement) {
        if (!modalElement) return;

        modalElement.querySelectorAll('.is-invalid')
            .forEach(element => element.classList.remove('is-invalid'));

        modalElement.querySelectorAll('.invalid-feedback').forEach(feedback => {
            feedback.textContent = '';
            feedback.style.display = 'none';
        });
    }
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
            this.showAlert(pendingMsg, pendingType);
        }

        // Auto-dismiss existing server-rendered alerts (skip alerts inside modals)
        document.querySelectorAll('.alert:not(.alert-info):not(.alert-warning)').forEach(alert => {
            if (alert.closest('.modal')) return;
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
                new bootstrap.Tooltip(element);
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
            const parsed = Utils.parseNumberStrict(raw);
            if (!parsed.ok) {
                return { ok: false, message: 'Required.' };
            }
            if (parsed.value <= 0) {
                return { ok: false, message: 'Amount must be greater than 0.' };
            }
            return { ok: true };
        }
    },

    // Category selection
    category: {
        name: 'category',
        validate: (raw) => {
            if (!String(raw || '').trim()) {
                return { ok: false, message: 'Select asset class.' };
            }
            return { ok: true };
        }
    },

    // Asset symbol
    symbol: {
        name: 'symbol',
        validate: (raw, element) => {
            const value = Utils.normalizeSymbol(raw);
            if (element) element.value = value;
            
            if (!value) {
                return { ok: false, message: 'Required.' };
            }
            if (!Utils.isValidSymbol(value)) {
                return { ok: false, message: 'Invalid symbol format.' };
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
                return { ok: false, message: 'Select a transaction type.' };
            }
            return { ok: true };
        }
    },

    // Price validation
    price: {
        name: 'price',
        validate: (raw) => {
            const parsed = Utils.parseNumberStrict(raw);
            if (!parsed.ok) {
                return { ok: false, message: 'Required.' };
            }
            if (parsed.value <= 0) {
                return { ok: false, message: 'Price must be greater than 0.' };
            }
            return { ok: true };
        }
    },

    // Quantity validation
    quantity: {
        name: 'quantity',
        validate: (raw) => {
            const parsed = Utils.parseNumberStrict(raw);
            if (!parsed.ok) {
                return { ok: false, message: 'Required.' };
            }
            if (parsed.value <= 0) {
                return { ok: false, message: 'Quantity must be greater than 0.' };
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
            
            const parsed = Utils.parseNumberStrict(str);
            if (!parsed.ok) {
                return { ok: false, message: 'Invalid fees.' };
            }
            if (parsed.value < 0) {
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
                return { ok: false, message: 'Required.' };
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

        // Add funds entry form
        this.initValidator('form[action$="/funds/add"]', [
            { ...ValidationRules.category, selector: '#category' },
            { ...ValidationRules.fundsAmount, selector: '#amount', name: 'amount' },
            { ...ValidationRules.date, selector: '#add_fund_date', name: 'add_fund_date' }
        ]);

        // Edit fund event
        this.initValidator('#editFundEventForm', [
            { ...ValidationRules.date, selector: '#edit_event_date' },
            { ...ValidationRules.fundsAmount, selector: '#edit_event_amount', name: 'amount' }
        ]);

        // Add asset symbol
        this.initValidator('form[action$="/assets/add"]', [
            { ...ValidationRules.category, selector: '#asset_fund_id', name: 'fund_id' },
            { ...ValidationRules.symbol, selector: '#asset_symbol' }
        ]);

        // Add transaction — rules are mode-aware (Buy/Sell vs Dividend)
        const skipInDividendMode = (baseRule) => (raw, el, form) => {
            if (window.isDividendMode) return { ok: true };
            if (typeof baseRule === 'function') return baseRule(raw, el, form);
            return baseRule.validate(raw, el, form);
        };

        this.initValidator('form[action$="/transactions/add"]', [
            { ...ValidationRules.category, selector: '#fund_id', name: 'fund_id' },
            { ...ValidationRules.symbol, selector: '#symbol',
                validate: skipInDividendMode(ValidationRules.symbol) },
            { ...ValidationRules.transactionType, selector: '#transaction_type',
                validate: skipInDividendMode(ValidationRules.transactionType) },
            { ...ValidationRules.price, selector: '#price',
                validate: skipInDividendMode(ValidationRules.requiresTransactionType(ValidationRules.price)) },
            { ...ValidationRules.quantity, selector: '#quantity',
                validate: skipInDividendMode(ValidationRules.requiresTransactionType(ValidationRules.quantity)) },
            { ...ValidationRules.fees, selector: '#fees',
                validate: skipInDividendMode(ValidationRules.requiresTransactionType(ValidationRules.fees)) },
            { ...ValidationRules.date, selector: '#add_tx_date',
                validate: skipInDividendMode(ValidationRules.date) },
            // Dividend-only fields
            { name: 'amount', selector: '#amount',
                validate: (raw) => {
                    if (!window.isDividendMode) return { ok: true };
                    const str = String(raw || '').trim();
                    if (!str) return { ok: false, message: 'Amount must be greater than 0.' };
                    const n = parseFloat(str);
                    if (!isFinite(n) || n <= 0) return { ok: false, message: 'Amount must be greater than 0.' };
                    return { ok: true };
                }
            },
            { name: 'add_dividend_date', selector: '#add_dividend_date',
                validate: (raw) => {
                    if (!window.isDividendMode) return { ok: true };
                    return ValidationRules.date.validate(raw);
                }
            },
        ]);

        // Edit transaction
        this.initValidator('#editTransactionForm', [
            { ...ValidationRules.price, selector: '#edit_price' },
            { ...ValidationRules.quantity, selector: '#edit_quantity' },
            { ...ValidationRules.fees, selector: '#edit_fees' },
            { ...ValidationRules.date, selector: '#edit_date' }
        ]);
    }

    initValidator(formSelector, rules) {
        const formElement = document.querySelector(formSelector);
        if (formElement) {
            new FormValidator(formElement, rules);
        }
    }
}

class NativeValidationDisabler {
    constructor() {
        this.disableForAllForms();
        this.removeRequiredAttributes();
    }

    disableForAllForms() {
        document.querySelectorAll('form').forEach(form => {
            form.noValidate = true;
            form.setAttribute('novalidate', 'novalidate');
        });
    }

    removeRequiredAttributes() {
        document.querySelectorAll('input[required], select[required], textarea[required]')
            .forEach(element => {
                element.removeAttribute('required');
            });
    }
}


/**
 * Handle AJAX form submissions for modals to show errors inline
 */
class ModalAjaxHandler {
    constructor() {
        this.init();
    }

    init() {
        // Forms to handle with AJAX (in modals)
        // Map modal IDs to their forms
        const modalForms = [
            // Add Transaction handles both buy/sell AND dividend (action changes dynamically)
            { modalId: 'addTransactionModal', formSelector: '#addTransactionModal form' },
            { modalId: 'editTransactionModal', formSelector: '#editTransactionForm' },
            { modalId: 'newFundModal', formSelector: 'form[action$="/funds/add"]' },
            { modalId: 'depositFundsModal', formSelector: '#depositFundsForm' },
            { modalId: 'withdrawFundsModal', formSelector: '#withdrawFundsForm' }
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
        form.addEventListener('submit', async (e) => {
            e.preventDefault();

            // Clear previous errors
            this.clearErrors(modal);

            // Show loading state
            const submitBtn = form.querySelector('button[type="submit"]');
            const originalText = submitBtn ? submitBtn.innerHTML : '';
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Processing...';
            }

            // Get form data
            const formData = new FormData(form);

            try {
                const response = await fetch(form.action, {
                    method: 'POST',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: formData
                });

                const data = await response.json();

                if (data.success) {
                    // Store message for display after reload
                    sessionStorage.setItem('flashMessage', data.message || 'Success');
                    sessionStorage.setItem('flashType', 'success');

                    // Reload immediately - message shows on fresh page
                    window.location.reload();
                } else {
                    // Restore button
                    if (submitBtn) {
                        submitBtn.disabled = false;
                        submitBtn.innerHTML = originalText;
                    }
                    // Show error in modal
                    this.showModalError(modal, data.error || 'Operation failed');
                }
            } catch (error) {
                // Restore button
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = originalText;
                }
                console.error('Form submission error:', error);
                this.showModalError(modal, 'Network error');
            }
        });
    }

    showModalError(modal, message) {
        // Show error as inline field validation on the relevant field
        const msg = (message || '').toLowerCase();
        let targetField = null;

        if (msg.includes('amount')) {
            targetField = modal.querySelector('#amount');
        } else if (msg.includes('quantity')) {
            targetField = modal.querySelector('#edit_quantity, #quantity');
        } else if (msg.includes('fund') || msg.includes('cash')) {
            const preview = modal.querySelector('#total_cost_preview, #edit_total_cost_preview');
            if (preview) {
                preview.innerHTML = `<span class="text-danger">${Utils.escapeHtml(message)}</span>`;
                return;
            }
            targetField = modal.querySelector('#edit_price, #price');
        } else if (msg.includes('price')) {
            targetField = modal.querySelector('#edit_price, #price');
        } else if (msg.includes('date')) {
            targetField = modal.querySelector('#edit_date, #add_tx_date, #add_dividend_date, #edit_event_date, #deposit_date, #withdraw_date, #add_fund_date');
        }

        // Fallback: first visible input (not hidden/disabled/readonly)
        if (!targetField) {
            targetField = modal.querySelector('.modal-body input:not([type="hidden"]):not([disabled]):not([readonly])');
        }

        if (targetField) {
            targetField.classList.add('is-invalid');
            const feedback = Utils.ensureFeedbackElement(targetField);
            if (feedback) {
                feedback.textContent = message;
                feedback.style.display = 'block';
            }
        }
    }

    clearErrors(modal) {
        modal.querySelectorAll('.is-invalid').forEach(el => el.classList.remove('is-invalid'));
        modal.querySelectorAll('.invalid-feedback').forEach(el => {
            el.textContent = '';
            el.style.display = 'none';
        });
        modal.querySelectorAll('.tx-preview .text-danger').forEach(el => el.remove());
    }
}


class DropdownHoverManager {
    constructor() {
        document.querySelectorAll('.settings-dropdown').forEach(el => {
            const toggle = el.querySelector('[data-bs-toggle="dropdown"]');
            const menu   = el.querySelector('.dropdown-menu');
            const dropdown = bootstrap.Dropdown.getOrCreateInstance(toggle, {
                offset: [0, 0],
                popperConfig: { modifiers: [{ name: 'preventOverflow', enabled: false }] }
            });
            let hideTimer;

            const scheduleHide = () => { hideTimer = setTimeout(() => dropdown.hide(), 80); };
            const cancelHide   = () => clearTimeout(hideTimer);

            el.addEventListener('mouseenter', () => { cancelHide(); dropdown.show(); });
            el.addEventListener('mouseleave', scheduleHide);
            menu?.addEventListener('mouseenter', cancelHide);
            menu?.addEventListener('mouseleave', scheduleHide);
        });
    }
}


class NumericFitManager {
    // Shrinks numeric value elements that overflow their container so they
    // stay on one line. Uses overflow:hidden temporarily to force an accurate
    // scrollWidth measurement (overflow:visible makes scrollWidth == clientWidth).
    static SELECTOR = '.card-value, .summary-value, .stat-card .card-body h2';
    static MIN_FONT_SIZE = 10;

    constructor() {
        this._elements = [];
        this._resizeTimer = null;
        this.fit();
        window.addEventListener('resize', () => {
            clearTimeout(this._resizeTimer);
            this._resizeTimer = setTimeout(() => this.fit(), 200);
        });
    }

    fit() {
        this._elements = Array.from(document.querySelectorAll(NumericFitManager.SELECTOR));
        this._elements.forEach(el => this._fitOne(el));
    }

    _fitOne(el) {
        el.style.fontSize   = '';
        el.style.whiteSpace = '';

        // Skip elements inside collapsed/hidden containers
        if (el.clientWidth === 0) return;

        el.style.overflow = 'hidden';
        el.style.whiteSpace = 'nowrap';

        if (el.scrollWidth <= el.clientWidth) {
            el.style.whiteSpace = '';
            el.style.overflow   = '';
            return;
        }

        let size = parseFloat(getComputedStyle(el).fontSize);
        while (el.scrollWidth > el.clientWidth && size > NumericFitManager.MIN_FONT_SIZE) {
            size -= 0.5;
            el.style.fontSize = size + 'px';
        }
        el.style.overflow = '';
    }
}


class InvestmentPortfolioApp {
    constructor() {
        this.initialize();
    }

    initialize() {
        new NativeValidationDisabler();

        const csrfManager = new CSRFManager();
        csrfManager.injectTokenToForms();

        new DecimalInputHandler();
        new AlertManager();
        new TooltipManager();
        new FormValidatorsInitializer();
        new TransactionFormHandler();
        new ModalManager();
        new ModalAjaxHandler();
        new DropdownHoverManager();
        new NumericFitManager();

        const navbar = document.querySelector('.app-navbar');
        if (navbar) {
            const onScroll = () => navbar.classList.toggle('scrolled', window.scrollY > 8);
            window.addEventListener('scroll', onScroll, { passive: true });
            onScroll();
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new InvestmentPortfolioApp();
});