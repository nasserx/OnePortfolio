// Run the production handler and decimal editor with controlled fetch ordering.
// No server, network, timers, or database is used.
const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const read = file => fs.readFileSync(path.join(__dirname, '..', file), 'utf8');
const html = read('portfolio_app/templates/assets.html');
const start = html.indexOf('(function setupAddSellMax()');
const end = html.indexOf('// Ensure header action buttons', start);
assert.ok(start >= 0 && end > start);
const flush = () => new Promise(resolve => setImmediate(resolve));

function deferred() {
    let resolve, reject;
    const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
    return {promise, resolve, reject};
}

function setup() {
    const document = new EventTarget();
    document.defaultView = {Event};
    const elements = new Map();
    document.getElementById = id => {
        if (!elements.has(id)) {
            const classes = new Set();
            const el = new EventTarget();
            Object.assign(el, {value: '', disabled: false, type: 'text', tagName: 'INPUT',
                dataset: {numeric: 'decimal'}, ownerDocument: document,
                selectionStart: 0, selectionEnd: 0, selectionDirection: 'none',
                setSelectionRange() {}, setAttribute() {},
                classList: {
                    toggle(name, enabled) { if (enabled) classes.add(name); else classes.delete(name); },
                    contains(name) { return classes.has(name); },
                }});
            elements.set(id, el);
        }
        return elements.get(id);
    };
    const el = id => document.getElementById(id);
    const emit = (id, event) => el(id).dispatchEvent(new Event(event));
    const requests = [];
    const context = vm.createContext({document, window: {}, Event, queueMicrotask,
        fetch(url) {
            const response = deferred();
            const body = deferred();
            requests.push({url, response, body,
                headers() { response.resolve({ok: true, json: () => body.promise}); },
                succeed(quantity) { this.headers(); body.resolve({held_quantity: quantity}); },
                fail() { response.reject(new Error('Network failure')); },
            });
            return response.promise;
        },
    });
    vm.runInContext(read('portfolio_app/static/js/numeric_inputs.js'), context);
    vm.runInContext(html.slice(start, end), context);
    const ui = {
        requests, el,
        button: el('add_sell_max_btn'), quantity: el('quantity'),
        open(symbol = 'A', portfolio = '1') {
            el('portfolio_id').value = portfolio;
            el('symbol').value = symbol;
            this.type('Sell'); // The production open function populates before show.
            emit('addTransactionModal', 'show.bs.modal');
            emit('addTransactionModal', 'shown.bs.modal');
        },
        hide() { emit('addTransactionModal', 'hide.bs.modal'); },
        hidden() { emit('addTransactionModal', 'hidden.bs.modal'); },
        symbol(value) { el('symbol').value = value; emit('symbol', 'input'); },
        portfolio(value) { el('portfolio_id').value = value; emit('portfolio_id', 'change'); },
        type(value) { el('transaction_type').value = value; emit('transaction_type', 'change'); },
        max() { emit('add_sell_max_btn', 'click'); },
        assertUnavailable() {
            assert.equal(this.button.disabled, true);
            const before = this.quantity.value;
            this.max(); // Guard even a queued/programmatic click on a disabled button.
            assert.equal(this.quantity.value, before);
        },
    };
    ui.open();
    assert.equal(requests.length, 1);
    return ui;
}

test('late quantity 5 cannot replace current asset quantity 100', async () => {
    const ui = setup();
    ui.symbol('B');
    ui.requests[1].succeed('100'); await flush();
    ui.requests[0].succeed('5'); await flush();
    assert.equal(ui.button.disabled, false);
    ui.max(); assert.equal(ui.quantity.value, '100');
});

test('same symbol in a different portfolio uses only the latest portfolio', async () => {
    const ui = setup();
    ui.portfolio('2');
    assert.match(ui.requests[1].url, /portfolio_id=2&symbol=A$/);
    ui.requests[1].succeed('100'); await flush();
    ui.requests[0].succeed('5'); await flush();
    ui.max(); assert.equal(ui.quantity.value, '100');
});

test('A to B to A does not revive the first request for A', async () => {
    const ui = setup();
    ui.symbol('B'); ui.symbol('A');
    ui.requests[2].succeed('100'); await flush();
    ui.requests[1].succeed('50'); await flush();
    ui.requests[0].succeed('5'); await flush();
    ui.max(); assert.equal(ui.quantity.value, '100');
});

for (const failure of ['network', 'http', 'json']) {
    test(`old ${failure} failure cannot clear a current successful result`, async () => {
        const ui = setup();
        if (failure === 'json') { ui.requests[0].headers(); await flush(); }
        ui.symbol('B');
        ui.requests[1].succeed('100'); await flush();
        if (failure === 'network') ui.requests[0].fail();
        if (failure === 'http') ui.requests[0].response.resolve({ok: false, status: 500});
        if (failure === 'json') ui.requests[0].body.reject(new Error('Invalid JSON'));
        await flush();
        assert.equal(ui.button.disabled, false);
        ui.max(); assert.equal(ui.quantity.value, '100');
    });
}

test('old completion during current loading cannot enable Max', async () => {
    const ui = setup();
    ui.symbol('B');
    ui.requests[0].succeed('5'); await flush();
    ui.assertUnavailable();
    ui.requests[1].succeed('100'); await flush();
    ui.max(); assert.equal(ui.quantity.value, '100');
});

test('selection changing while JSON is pending invalidates that body too', async () => {
    const ui = setup();
    ui.requests[0].headers(); await flush();
    ui.symbol('B');
    ui.requests[1].succeed('100'); await flush();
    ui.requests[0].body.resolve({held_quantity: '5'}); await flush();
    ui.max(); assert.equal(ui.quantity.value, '100');
});

for (const field of ['symbol', 'portfolio']) {
    test(`${field} changes immediately invalidate cached quantity, including on current failure`, async () => {
        const ui = setup();
        ui.requests[0].succeed('5'); await flush();
        ui.max(); assert.equal(ui.quantity.value, '5');
        ui[field](field === 'symbol' ? 'B' : '2');
        ui.assertUnavailable();
        ui.requests[1].fail(); await flush();
        ui.assertUnavailable();
        ui[field](field === 'symbol' ? 'C' : '3');
        ui.requests[2].succeed('100'); await flush();
        ui.max(); assert.equal(ui.quantity.value, '100');
    });
}

test('a stale success cannot recover Max after the current request fails', async () => {
    const ui = setup();
    ui.symbol('B');
    ui.requests[1].fail(); await flush();
    ui.requests[0].succeed('5'); await flush();
    ui.assertUnavailable();
});

test('closing invalidates cached quantity before the hide transition completes', async () => {
    const ui = setup();
    ui.requests[0].succeed('5'); await flush();
    ui.hide(); ui.assertUnavailable();
    ui.hidden(); ui.open(); ui.assertUnavailable();
    ui.requests[1].succeed('100'); await flush();
    ui.max(); assert.equal(ui.quantity.value, '100');
});

test('responses during closing cannot re-enable Max', async () => {
    const ui = setup();
    ui.hide();
    ui.requests[0].succeed('5'); await flush();
    ui.assertUnavailable();
    ui.hidden(); ui.assertUnavailable();
});

for (const outcome of ['success', 'failure']) {
    test(`reopening the same selection rejects the previous opening's ${outcome}`, async () => {
        const ui = setup();
        ui.hide(); ui.hidden(); ui.open();
        ui.requests[1].succeed('100'); await flush();
        if (outcome === 'success') ui.requests[0].succeed('5');
        else ui.requests[0].fail();
        await flush();
        assert.equal(ui.button.disabled, false);
        ui.max(); assert.equal(ui.quantity.value, '100');
    });
}

test('switching to Buy or clearing a selection cannot be undone by a response', async () => {
    for (const mutate of [ui => ui.type('Buy'), ui => ui.symbol(''), ui => ui.portfolio('')]) {
        const ui = setup(); mutate(ui);
        ui.requests[0].succeed('5'); await flush();
        ui.assertUnavailable();
        if (ui.el('transaction_type').value === 'Buy') {
            assert.equal(ui.el('add_sell_max_row').classList.contains('d-none'), true);
        }
    }
});

test('result and click also check the live selection without relying solely on events', async () => {
    for (const field of ['symbol', 'portfolio_id', 'transaction_type']) {
        const ui = setup();
        ui.el(field).value = field === 'portfolio_id' ? '2' : field === 'symbol' ? 'B' : 'Buy';
        ui.requests[0].succeed('5'); await flush();
        ui.assertUnavailable();
        const cached = setup();
        cached.requests[0].succeed('5'); await flush();
        cached.el(field).value = field === 'portfolio_id' ? '2' : field === 'symbol' ? 'B' : 'Buy';
        cached.max(); assert.equal(cached.quantity.value, '');
    }
});

test('normal Max preserves the complete decimal string and notifies previews once', async () => {
    const ui = setup();
    const exact = '1234567890.1234567890123456789012345';
    let inputs = 0;
    ui.quantity.addEventListener('input', () => inputs++);
    ui.assertUnavailable();
    assert.match(ui.requests[0].url, /portfolio_id=1&symbol=A$/);
    ui.requests[0].succeed(exact); await flush();
    assert.equal(ui.button.disabled, false);
    ui.max(); assert.equal(ui.quantity.value, exact); assert.equal(inputs, 1);
});

test('zero, negative and invalid quantities never enable or populate Max', async () => {
    for (const value of ['0', '-5', 'NaN', 'Infinity', 'invalid']) {
        const ui = setup();
        ui.requests[0].succeed(value); await flush();
        ui.assertUnavailable();
    }
});
