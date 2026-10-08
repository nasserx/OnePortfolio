// Execute transfer dialog population without browser/application/database startup.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const elements = new Map();
let click;
let shown;
const document = {
    getElementById(id) {
        if (!elements.has(id)) elements.set(id, {id, value: ''});
        return elements.get(id);
    },
    addEventListener(name, fn) { if (name === 'click') click = fn; },
};
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
equal(document.getElementById('transfer_source_portfolio_id').value, 7);
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
action('delete', {id: 42});
equal(document.getElementById('deleteTransferForm').action, '/portfolios/transfers/delete/42');
equal(shown, 'deleteTransferModal');
action('create', {source_portfolio_id: 8});
equal(document.getElementById('transfer_amount').value, '');
equal(document.getElementById('transfer_notes').value, '');
console.log(`${checks} transfer action assertions passed`);
