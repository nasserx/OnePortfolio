// Exercise the shared modal error owner, not a transfer-only implementation.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('portfolio_app/static/js/main.js', 'utf8');
const modalClass = source.slice(source.indexOf('class ModalAjaxHandler'), source.indexOf('class InvestmentPortfolioApp'));
let banner;
const feedback = {style: {}, textContent: ''};
const input = {classList: {add(name) { input.invalid = name; }}};
const body = {firstChild: null, insertBefore(node) { banner = node; }};
const modal = {querySelector(selector) {
    if (selector === '.js-modal-banner') return banner;
    if (selector === '.modal-body') return body;
    if (selector === '[name="amount"]') return input;
    return null;
}};
const context = vm.createContext({
    document: {createElement() { return {
        attributes: {}, setAttribute(key, value) { this.attributes[key] = value; },
        remove() { banner = null; },
    }; }},
    window: {}, Utils: {ensureFeedbackElement() { return feedback; }},
});
vm.runInContext(modalClass + '\nModalAjaxHandler.prototype.init = function() {}; globalThis.handler = new ModalAjaxHandler();', context);
const handler = context.handler;
handler.applyFieldErrors(modal, {__all__: 'Insufficient cash for this transfer change.'});
assert.equal(banner.className, 'invalid-feedback d-block js-modal-banner mb-3');
assert.equal(banner.attributes.role, 'alert');
assert.equal(banner.textContent, 'Insufficient cash for this transfer change.');
assert.equal(banner.className.includes('alert-danger'), false);
const old = banner;
handler.applyFieldErrors(modal, {__all__: '<script>literal, never HTML</script>'});
assert.notEqual(banner, old);
assert.equal(banner.textContent, '<script>literal, never HTML</script>');
banner = null;
handler.applyFieldErrors(modal, {amount: 'Enter a valid amount.'});
assert.equal(input.invalid, 'is-invalid');
assert.equal(feedback.textContent, 'Enter a valid amount.');
assert.equal(feedback.style.display, 'block');
assert.equal(banner, null);
console.log('10 shared modal error assertions passed');
