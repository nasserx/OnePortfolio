// Run with node tests/precision_boundaries.js. No browser, server or database.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const elements = new Map();
const document = new EventTarget();
document.defaultView = {Event};
document.getElementById = id => {
    if (!elements.has(id)) {
        const field = new EventTarget();
        Object.assign(field, {value: '', type: 'text', tagName: 'INPUT',
            dataset: {numeric: 'decimal'}, ownerDocument: document,
            selectionStart: 0, selectionEnd: 0, selectionDirection: 'none'});
        field.setSelectionRange = () => {};
        elements.set(id, field);
    }
    return elements.get(id);
};
const context = vm.createContext({
    document, queueMicrotask, window: {OnePortfolioForms: {prepare() {}}, OnePortfolioDialogs: {show() {}}}, Event,
});
vm.runInContext(read('portfolio_app/static/js/numeric_inputs.js'), context);
vm.runInContext(read('portfolio_app/static/js/main.js') + '\nglobalThis.rules = ValidationRules;', context);
let checks = 0;
const equal = (actual, expected) => { assert.equal(actual, expected); checks++; };
for (const value of ['0.' + '0'.repeat(1000) + '1', '9'.repeat(1000), ' +1,000.00100 ', '1e-1000', '.25', '1.']) {
    for (const name of ['fundsAmount', 'price', 'quantity', 'fees']) equal(context.rules[name].validate(value).ok, true);
}
for (const value of ['', '.', '0', '-1', '-0e99', '1x2', 'NaN', 'Infinity', '1,5']) {
    for (const name of ['fundsAmount', 'price', 'quantity']) equal(context.rules[name].validate(value).ok, false);
}
for (const value of ['', '0', '-0e99']) equal(context.rules.fees.validate(value).ok, true);
for (const value of ['-1', '.', 'NaN', '1x2']) equal(context.rules.fees.validate(value).ok, false);

// Execute the production edit-population functions against minimal DOM stubs.
const assets = read('portfolio_app/templates/assets.html');
let start = assets.indexOf('function editTransaction(');
let end = assets.indexOf('// Submit handling for #deleteTransactionForm', start);
vm.runInContext(assets.slice(start, end), context);
start = assets.indexOf('function openEditDividendModal(');
end = assets.indexOf('// ModalAjaxHandler in static/js/main.js is the sole submit owner here too.', start);
vm.runInContext(assets.slice(start, end), context);
context.editTransaction(1, 1, 'Buy', 'BTC', '1234567890.1234567890',
    '0.0000000001', '0.0123456789', 'notes', '2024-01-01');
equal(document.getElementById('edit_price').value, '1234567890.1234567890');
equal(document.getElementById('edit_quantity').value, '0.0000000001');
equal(document.getElementById('edit_fees').value, '0.0123456789');
context.openEditDividendModal(1, '1234567890.1234567890', '2024-01-01', 'notes');
equal(document.getElementById('edit_amount').value, '1234567890.1234567890');
context.openEditDividendModal(1, '1.234567890123456789e9', '2024-01-01', 'notes');
equal(document.getElementById('edit_amount').value, '1.234567890123456789e9');
console.log(`${checks} precision boundary assertions passed`);
