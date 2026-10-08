// Execute transfer dialog population without browser/application/database startup.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const elements = new Map();
function option(value, textContent) {
    return {value, textContent, cloneNode() { return option(value, textContent); }};
}
function element(id) {
    return {id, _value: '', options: [], handlers: {},
        get value() { return this._value; },
        set value(value) { this._value = String(value); },
        get selectedOptions() { return this.options.filter(o => o.value === this.value); },
        addEventListener(name, fn) { this.handlers[name] = fn; },
        replaceChildren(...children) { this.options = children; },
    };
}
let click;
let shown;
const document = {
    getElementById(id) {
        if (!elements.has(id)) elements.set(id, element(id));
        return elements.get(id);
    },
    addEventListener(name, fn) { if (name === 'click') click = fn; },
};
const source = document.getElementById('transfer_source_portfolio_id');
source.options = [option('', 'Select Portfolio'), option('7', 'ETFs'), option('8', 'Crypto'), option('9', 'Stocks')];
const destination = document.getElementById('transfer_destination_portfolio_id');
const context = vm.createContext({document, Date, bootstrap: {Modal: {
    getOrCreateInstance(element) { return {show() { shown = element.id; }}; },
}}});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../portfolio_app/static/js/portfolio_transfers.js'), 'utf8'), context);
let checks = 0;
const equal = (actual, expected) => { assert.equal(actual, expected); checks++; };
function action(kind, data) {
    click({target: {closest() { return {dataset: {transferAction: kind, transfer: JSON.stringify(data)}}; }},
        preventDefault() {}, stopPropagation() {}});
}
action('create', {source_portfolio_id: 7});
equal(document.getElementById('transferForm').action, '/portfolios/transfers/add');
equal(source.value, '7');
equal(source.disabled, true);
equal(document.getElementById('transfer_source_picker').hidden, true);
equal(document.getElementById('transfer_source_context').hidden, false);
equal(document.getElementById('transfer_context_source').value, '7');
equal(document.getElementById('transfer_context_source').disabled, false);
equal(document.getElementById('transfer_source_name').value, 'ETFs');
equal(destination.options.map(o => o.value).join(','), ',8,9');
equal(document.getElementById('transfer_destination_portfolio_id').value, '');
equal(document.getElementById('transfer_amount').value, '');
equal(shown, 'transferModal');
const amount = '1234567890.1234567890123456789012345';
action('edit', {id: 42, source_portfolio_id: 7, destination_portfolio_id: 8, amount, date: '2024-01-02', notes: 'exact notes'});
equal(document.getElementById('transferForm').action, '/portfolios/transfers/edit/42');
equal(document.getElementById('transfer_amount').value, amount);
equal(document.getElementById('transfer_date').value, '2024-01-02');
equal(document.getElementById('transfer_notes').value, 'exact notes');
equal(document.getElementById('transferModalTitle').textContent, 'Edit Transfer');
equal(source.disabled, false);
equal(document.getElementById('transfer_context_source').disabled, true);
equal(document.getElementById('transfer_source_picker').hidden, false);
equal(document.getElementById('transfer_source_context').hidden, true);
equal(destination.value, '8');
source.value = '8';
source.handlers.change();
equal(destination.value, '');
equal(destination.options.map(o => o.value).join(','), ',7,9');
destination.value = '9';
source.value = '7';
source.handlers.change();
equal(destination.value, '9');
action('delete', {id: 42});
equal(document.getElementById('deleteTransferForm').action, '/portfolios/transfers/delete/42');
equal(shown, 'deleteTransferModal');
action('create', {source_portfolio_id: 8});
equal(document.getElementById('transfer_amount').value, '');
equal(document.getElementById('transfer_notes').value, '');
console.log(`${checks} transfer action assertions passed`);
