// Code-only chart fallback checks; no browser/canvas rendering is performed.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('portfolio_app/static/js/overview_charts.js', 'utf8');
const element = () => ({hidden: false, textContent: '', setAttribute() {}, replaceChildren() {}});
const canvas = element();
const wrap = element();
canvas.closest = () => wrap;
const legend = element();
const empty = element();
const status = element();
const elements = {allocationChart: canvas, allocationLegend: legend, allocationChartStatus: status};
const context = vm.createContext({
    window: {OnePortfolioDisplay: {}},
    document: {documentElement: {}, getElementById: id => elements[id],
        querySelector: selector => selector === '[data-alloc-empty]' ? empty : null},
    getComputedStyle: () => ({getPropertyValue: () => '#000'}),
});
vm.runInContext(source.replace('window.initPortfolioAllocationChart =',
    'window.TestAllocationChart = AllocationChart; window.initPortfolioAllocationChart ='), context);
const chart = new context.window.TestAllocationChart({
    book_value_chart: {categories: [], allocations: [], values: [], total: null, unavailable: true},
    net_contributions_chart: {categories: ['Normal'], allocations: [100], values: [25], total: 25},
});
let renders = 0;
chart.renderChart = () => { renders++; };
chart.renderLegend = () => {};
chart.render();
assert.equal(canvas.hidden, true);
assert.equal(wrap.hidden, true);
assert.equal(legend.hidden, true);
assert.equal(empty.hidden, false);
assert.match(empty.textContent, /Chart unavailable for this numeric range/);
assert.match(status.textContent, /Chart unavailable for this numeric range/);
assert.equal(renders, 0);
chart.view = 'net_contributions_chart';
chart.render();
assert.equal(canvas.hidden, false);
assert.equal(empty.hidden, true);
assert.equal(renders, 1);
chart.data.net_contributions_chart = {categories: [], allocations: [], values: [], total: 0};
chart.render();
assert.equal(empty.textContent, 'No portfolio data available.');
assert.match(status.textContent, /No portfolio data available/);
console.log('12 Overview chart range assertions passed');
