// Execute the production inline Max handler without starting the application.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../portfolio_app/templates/portfolios.html'), 'utf8');
const code = html.slice(html.indexOf('(function setupWithdrawMax()'), html.indexOf('function deletePortfolio('));
let checks = 0;

async function run() {
    const handlers = {};
    const button = {dataset: {portfolioId: '7'}, addEventListener: (name, fn) => handlers[name] = fn};
    const input = {value: '', setCustomValidity(value) { this.error = value; }, reportValidity() {},
        dispatchEvent() {}, addEventListener() {}};
    const date = {value: '2024-01-02'};
    let respond;
    let requested;
    const context = vm.createContext({
        document: {getElementById: id => ({withdraw_max_btn: button, withdraw_funds_amount: input, withdraw_date: date})[id]},
        URLSearchParams, Intl, Event: class {},
        fetch: (url) => { requested = url; return new Promise(resolve => { respond = resolve; }); },
    });
    vm.runInContext(code, context); // Also checks syntax of the changed production script.
    let pending = handlers.click();
    assert.match(requested, /withdrawal-max\/7\?date=2024-01-02/); checks++;
    assert.equal(button.disabled, true); checks++;
    respond({ok: true, json: async () => ({success: true, amount: '1234567890.12'})});
    await pending;
    assert.equal(input.value, '1234567890.12'); checks++;
    assert.equal(button.disabled, false); checks++;

    for (const mutate of [() => { date.value = '2024-01-03'; }, () => { button.dataset.portfolioId = '8'; }]) {
        pending = handlers.click();
        mutate();
        respond({ok: true, json: async () => ({success: true, amount: '999'})});
        await pending;
        assert.equal(input.value, '1234567890.12'); checks++;
    }
    pending = handlers.click();
    respond({ok: true, json: async () => ({success: true, amount: '0.00'})});
    await pending;
    assert.equal(input.value, '0.00'); checks++;
    pending = handlers.click();
    respond({ok: false, json: async () => ({success: false, errors: {withdraw_date: 'Invalid date'}})});
    await pending;
    assert.equal(input.error, 'Invalid date'); checks++;
    assert.equal(input.value, '0.00'); checks++;
    console.log(`${checks} cash-account Max assertions passed`);
}
run().catch(error => { console.error(error); process.exitCode = 1; });
