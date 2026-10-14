// Production numeric editor + preview controller, deterministic network/events.
// Native browser event/undo acceptance remains a separate user check.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let checks = 0;
const eq = (a, b) => { assert.equal(a, b); checks++; };
const tasks = [];
const requests = [];
class Node {
    constructor(id = '') { this.id = id; this.value = ''; this.listeners = {}; this.children = []; this.textContent = ''; }
    addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
    emit(type, props = {}) {
        const event = {target: this, type, ...props};
        if (this.form) for (const fn of this.form.listeners[type] || []) fn(event);
        for (const fn of this.listeners[type] || []) fn(event);
        return event;
    }
    dispatchEvent(event) { this.emit(event.type, {inputType: event.inputType}); }
    querySelector(selector) { return this.elements?.[selector] || null; }
    closest(selector) { return selector === 'form' ? this.form : this.modal; }
    replaceChildren(...children) { this.children = children; this.textContent = children.map(c => c.textContent).join(''); }
    setSelectionRange(start, end) { this.selectionStart = start; this.selectionEnd = end; }
}
const document = new Node();
document.defaultView = {Event};
document.createElement = () => new Node();
document.elements = {};
document.getElementById = id => document.elements[id];
function fixture(edit) {
    const form = new Node(); form.elements = {};
    const modal = new Node(); form.modal = modal;
    const fields = ['price', 'quantity', 'fees'].map(name => {
        const field = new Node((edit ? 'edit_' : '') + name);
        Object.assign(field, {form, ownerDocument: document, tagName: 'INPUT', type: 'text',
            dataset: {numeric: 'decimal'}, selectionStart: 0, selectionEnd: 0});
        form.elements['#' + field.id] = field;
        return field;
    });
    const type = new Node(); type.value = 'Buy'; type.form = form;
    form.elements[edit ? '#edit_transaction_type_display' : '#transaction_type'] = type;
    form.elements['[name="csrf_token"]'] = {value: 'csrf-value'};
    form.action = edit ? 'https://example.test/transactions/edit/7' : '/transactions/add';
    const output = new Node(); output.form = form;
    document.elements[(edit ? 'edit_' : '') + 'transaction_amount_preview'] = output;
    return {form, modal, fields, type, output};
}
const add = fixture(false), edit = fixture(true);
const window = {};
const context = vm.createContext({window, document, AbortController,
    queueMicrotask: task => tasks.push(task),
    setTimeout() { throw new Error('Preview must not debounce'); },
    fetch(url, options) {
        return new Promise((resolve, reject) => requests.push({url, options, resolve, reject}));
    }
});
for (const script of ['numeric_inputs', 'transaction_previews']) {
    vm.runInContext(fs.readFileSync(`portfolio_app/static/js/${script}.js`, 'utf8'), context);
}
const numeric = window.OnePortfolioNumeric;
for (const field of [...add.fields, ...edit.fields]) numeric.register(field);
window.OnePortfolioPreviews.initialize();
window.OnePortfolioPreviews.initialize(); // Idempotent registration.
const flush = () => { while (tasks.length) tasks.shift()(); };
const wait = () => new Promise(resolve => setImmediate(resolve));
function input(field, value) { field.value = value; field.setSelectionRange(value.length, value.length); field.emit('input'); flush(); }
function restore(record, values) { record.fields.forEach((field, i) => numeric.restoreValue(field, values[i])); }
async function run() {
    eq(add.output.textContent, 'Purchase Cost:—');
    eq(edit.output.textContent, 'Purchase Cost:—');
    add.modal.emit('shown.bs.modal'); eq(requests.length, 0);
    input(add.fields[0], '1'); eq(add.output.textContent, 'Purchase Cost:—');
    input(add.fields[1], '1'); eq(add.output.textContent, 'Purchase Cost:1.00');
    input(add.fields[2], '3'); eq(add.output.textContent, 'Purchase Cost:4.00');
    add.type.value = 'Sell'; add.type.emit('change'); flush();
    eq(add.output.textContent, 'Net Proceeds:-2.00');
    input(add.fields[2], '1'); eq(add.output.textContent, 'Net Proceeds:0.00');
    input(add.fields[2], '0'); eq(add.output.textContent, 'Net Proceeds:1.00');
    add.fields[2].emit('change'); flush(); eq(add.output.textContent, 'Net Proceeds:1.00');
    input(add.fields[0], '0'); eq(add.output.textContent, 'Net Proceeds:0.00');
    input(add.fields[0], '.'); eq(add.output.textContent, 'Net Proceeds:—');
    input(add.fields[0], ''); eq(add.output.textContent, 'Net Proceeds:—');
    input(add.fields[0], '1.'); eq(add.output.textContent, 'Net Proceeds:1.00');
    input(add.fields[2], '1.005'); eq(add.output.textContent, 'Net Proceeds:-0.01');
    input(add.fields[2], '1.004999999999999999999'); eq(add.output.textContent, 'Net Proceeds:-0.00');
    input(add.fields[0], '0.' + '0'.repeat(1000) + '1');
    input(add.fields[2], ''); eq(add.output.textContent, 'Net Proceeds:0.00');
    const raw = add.fields[0].value;
    eq(window.OnePortfolioPreviews.calculate('Buy', raw, '1', '0').amount, raw);
    for (let i = 1; i <= 250; i++) input(add.fields[0], String(i));
    eq(add.output.textContent, 'Net Proceeds:250.00'); eq(requests.length, 0);
    // Invalid edits are rolled back and retain the previous calculated amount.
    input(add.fields[0], '250x'); eq(add.fields[0].value, '250'); eq(add.output.textContent, 'Net Proceeds:250.00');
    add.fields[0].emit('compositionstart'); input(add.fields[0], '漢');
    eq(add.output.textContent, 'Net Proceeds:—');
    add.fields[0].emit('compositionend'); flush();
    eq(add.output.textContent, 'Net Proceeds:250.00');
    add.fields[0].emit('compositionstart'); input(add.fields[0], '3');
    add.fields[0].emit('compositionend'); flush(); eq(add.output.textContent, 'Net Proceeds:3.00');
    // A queued edit cannot render after close or reset.
    add.fields[0].value = '8'; add.fields[0].emit('input');
    add.modal.emit('hide.bs.modal'); flush(); eq(add.output.textContent, 'Net Proceeds:—');
    add.modal.emit('shown.bs.modal'); eq(add.output.textContent, 'Net Proceeds:8.00');

    restore(edit, ['1', '1', '']); edit.type.value = 'Sell';
    edit.modal.emit('shown.bs.modal'); eq(edit.output.textContent, 'Net Proceeds:—');
    eq(requests.length, 1);
    let request = requests.at(-1);
    eq(request.url, '/transactions/preview'); eq(request.options.method, 'POST');
    eq(request.options.credentials, 'same-origin'); eq(request.options.cache, 'no-store');
    eq(request.options.headers['X-CSRFToken'], 'csrf-value');
    eq(JSON.parse(request.options.body).mode, 'retained');
    eq(JSON.parse(request.options.body).transaction_id, '7');
    input(edit.fields[0], '2');
    request.resolve({ok: true, json: async () => ({success: true, fees: '3'})}); await wait();
    eq(edit.output.textContent, 'Net Proceeds:-1.00'); // Latest price, retained fees.
    input(edit.fields[2], '0'); eq(edit.output.textContent, 'Net Proceeds:2.00');
    input(edit.fields[2], ''); eq(edit.output.textContent, 'Net Proceeds:-1.00');
    for (let i = 1; i <= 200; i++) input(edit.fields[0], String(i));
    eq(edit.output.textContent, 'Net Proceeds:197.00'); eq(requests.length, 1);
    edit.type.value = 'Buy'; edit.type.emit('change'); flush(); eq(edit.output.textContent, 'Purchase Cost:203.00');
    edit.modal.emit('hide.bs.modal'); edit.modal.emit('shown.bs.modal'); request = requests.at(-1);
    window.OnePortfolioPreviews.reset(edit.form); edit.form.action = '/transactions/edit/8';
    restore(edit, ['1', '1', '']); edit.modal.emit('shown.bs.modal');
    eq(request.options.signal.aborted, true);
    request.resolve({ok: true, json: async () => ({success: true, fees: '999'})}); await wait();
    eq(edit.output.textContent, 'Purchase Cost:—');
    requests.at(-1).resolve({ok: true, json: async () => ({success: true, fees: '2.005'})}); await wait();
    eq(edit.output.textContent, 'Purchase Cost:3.01');
    // Switch a record in an already-open modal; no shown event is required.
    window.OnePortfolioPreviews.reset(edit.form); edit.form.action = '/transactions/edit/9';
    restore(edit, ['2', '1', '']); edit.fields[0].emit('input'); flush();
    eq(JSON.parse(requests.at(-1).options.body).transaction_id, '9');
    eq(edit.output.textContent, 'Purchase Cost:—');
    requests.at(-1).resolve({ok: true, json: async () => ({success: true, fees: '4'})}); await wait();
    eq(edit.output.textContent, 'Purchase Cost:6.00');
    // Network failure affects only an unknown retained fee, never ordinary typing.
    edit.modal.emit('hide.bs.modal'); restore(edit, ['1', '1', '3']); edit.modal.emit('shown.bs.modal');
    eq(edit.output.textContent, 'Purchase Cost:4.00');
    requests.at(-1).reject(new Error('offline')); await wait(); eq(edit.output.textContent, 'Purchase Cost:4.00');
    input(edit.fields[2], ''); eq(edit.output.textContent, 'Purchase Cost:Stored fees unavailable');
    input(edit.fields[0], ''); eq(edit.output.textContent, 'Purchase Cost:—');
    input(edit.fields[0], '1'); eq(edit.output.textContent, 'Purchase Cost:Stored fees unavailable');
    input(edit.fields[2], '0'); eq(edit.output.textContent, 'Purchase Cost:1.00');
    // Close/reopen retries and cannot reuse another record's fee or error state.
    edit.modal.emit('hide.bs.modal'); edit.modal.emit('shown.bs.modal'); request = requests.at(-1);
    input(edit.fields[2], ''); eq(edit.output.textContent, 'Purchase Cost:—');
    request.resolve({ok: false, json: async () => ({success: false})}); await wait();
    eq(edit.output.textContent, 'Purchase Cost:Stored fees unavailable');
    edit.modal.emit('hide.bs.modal'); edit.modal.emit('shown.bs.modal'); request = requests.at(-1);
    request.resolve({ok: true, json: async () => { throw new Error('login HTML'); }}); await wait();
    eq(edit.output.textContent, 'Purchase Cost:Stored fees unavailable');
    for (const fees of [null, 3, '', 'NaN', '1x2', '1e999999']) {
        edit.modal.emit('hide.bs.modal'); edit.modal.emit('shown.bs.modal');
        requests.at(-1).resolve({ok: true, json: async () => ({success: true, fees})}); await wait();
        eq(edit.output.textContent, 'Purchase Cost:Stored fees unavailable');
        eq(edit.fields[2].value, ''); // Never substitute zero or rewrite inputs on failure.
    }
    edit.modal.emit('hide.bs.modal'); edit.modal.emit('shown.bs.modal'); request = requests.at(-1);
    edit.modal.emit('hide.bs.modal'); request.reject(new Error('late failure')); await wait();
    eq(request.options.signal.aborted, true); eq(edit.output.textContent, 'Purchase Cost:—');
    input(add.fields[0], '9'.repeat(5000)); eq(add.fields[0].value.length, 5000); eq(add.output.textContent, 'Net Proceeds:—');
    eq(window.OnePortfolioPreviews.calculate('Buy', '1e999999', '1', '0'), null);
    eq(window.OnePortfolioPreviews.calculate('Buy', '1x2', '1', '0'), null);
    eq(window.OnePortfolioPreviews.calculate('Buy', ' +1,000.001 ', '1e-1', '0').formatted_amount, '100.00');
    edit.form.emit('reset'); eq(edit.output.textContent, 'Purchase Cost:—');
    console.log(`${checks} exact preview integration assertions passed`);
}
if (process.argv.includes('--calculate')) {
    // Python supplies vectors and compares these actual production results with
    // its authoritative calculator/formatter, including signed rounding ties.
    const vectors = JSON.parse(fs.readFileSync(0, 'utf8'));
    process.stdout.write(JSON.stringify(vectors.map(v => window.OnePortfolioPreviews.calculate(...v))));
} else run().catch(error => { console.error(error); process.exitCode = 1; });
