// Run with node tests/precision_boundaries.js. No browser, server or database.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const elements = new Map();
const document = {
    addEventListener() {},
    getElementById(id) {
        if (!elements.has(id)) elements.set(id, { value: '', dispatchEvent() {} });
        return elements.get(id);
    },
};
const context = vm.createContext({
    document, window: {}, Event: class {},
    bootstrap: { Modal: class { show() {} } },
});
vm.runInContext(read('portfolio_app/static/js/main.js') + '\nglobalThis.utils = Utils;', context);
const utils = context.utils;
let checks = 0;
const equal = (actual, expected) => { assert.equal(actual, expected); checks++; };
for (const [input, expected] of [
    ['1.234567890123456789e9', '1234567890.123456789'],
    ['0.001e2', '0.1'], ['1e-10', '0.0000000001'], ['0E-10', '0.0000000000'],
    ['-1.25e2', '-125'], ['1234567890.1234567890', '1234567890.1234567890'],
]) equal(utils.toPlainDecimalString(input), expected);
for (const [input, expected] of [
    [' 1,000.01 ', '1000.01'], ['1,5', '1,5'], ['-1', '-1'],
    ['1x2', '1x2'], ['NaN', 'NaN'], ['Infinity', 'Infinity'],
    ['1e-10', '0.0000000001'],
]) equal(utils.sanitizeDecimalInput(input), expected);

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
equal(document.getElementById('edit_price').value, '1234567890.123456789');
equal(document.getElementById('edit_quantity').value, '0.0000000001');
equal(document.getElementById('edit_fees').value, '0.0123456789');
context.openEditDividendModal(1, '1234567890.1234567890', '2024-01-01', 'notes');
equal(document.getElementById('edit_amount').value, '1234567890.123456789');
context.openEditDividendModal(1, '1.234567890123456789e9', '2024-01-01', 'notes');
equal(document.getElementById('edit_amount').value, '1234567890.123456789');
console.log(`${checks} precision boundary assertions passed`);
