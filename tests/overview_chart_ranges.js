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
const paletteReads = [];
const typeTokens = {'--weight-regular': '400', '--weight-medium': '500', '--font-sans': 'Geist',
    '--chart-text-size': '11', '--chart-value-size': '14'};
const context = vm.createContext({
    window: {OnePortfolioDisplay: {}},
    document: {documentElement: {}, getElementById: id => elements[id],
        querySelector: selector => selector === '[data-alloc-empty]' ? empty : null},
    getComputedStyle: () => ({getPropertyValue: name => {
        paletteReads.push(name);
        return typeTokens[name] || name;
    }}),
});
vm.runInContext(source.replace('window.initPortfolioAllocationChart =',
    'window.TestCentreText = centreText; window.TestAllocationChart = AllocationChart; window.initPortfolioAllocationChart ='), context);
const chart = new context.window.TestAllocationChart({
    book_value_chart: {categories: [], allocations: [], values: [], total: null, unavailable: true},
    net_contributions_chart: {categories: ['Normal'], allocations: [100], values: [25], total: 25},
});
assert.deepEqual(paletteReads, ['--chart-1', '--chart-2', '--chart-3', '--chart-4', '--chart-5']);
assert.deepEqual(Array.from(chart.colors), paletteReads);
assert.equal(chart.colorFor('Normal'), '--chart-1');
assert.equal(chart.colorFor('Other Portfolios'), '--chart-5');
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
// Drawing calls verify weight and unchanged authoritative display strings,
// without rendering pixels or starting a browser.
const painted = [];
const drawing = {
    config: {options: {plugins: {centreText: {label: 'Book Value', value: '12.34K'}}}},
    getDatasetMeta: () => ({data: [{innerRadius: 60, x: 80, y: 80}]}),
    ctx: {save() {}, restore() {}, fillText(text) { painted.push({text, font: this.font, color: this.fillStyle}); }},
};
context.window.TestCentreText.afterDraw(drawing);
assert.equal(painted[0].font, '400 11px Geist');
assert.equal(painted[1].font, '500 14px Geist');
assert.equal(painted[0].text, 'Book Value');
assert.equal(painted[1].text, '12.34K');
assert.equal(painted[0].color, '--muted-foreground');
assert.equal(painted[1].color, '--foreground');
typeTokens['--chart-text-size'] = '12'; typeTokens['--chart-value-size'] = '15';
context.window.TestCentreText.afterDraw(drawing);
assert.equal(painted[2].font, '400 12px Geist');
assert.equal(painted[3].font, '500 15px Geist');
let tooltipChecks = 0;
for (const name of ['overview_charts.js', 'landing.js']) {
    const code = fs.readFileSync('portfolio_app/static/js/' + name, 'utf8');
    for (const role of ['titleFont', 'bodyFont']) {
        const fn = code.match(new RegExp(role + ': (function \\(\\) \\{ return \\{[^}]+\\}; \\})'))[1];
        const font = vm.runInNewContext('(' + fn + ')', {cssVar: name => typeTokens[name]});
        assert.equal(font().weight, '500');
        assert.equal(font().size, 12);
        typeTokens['--chart-text-size'] = '11';
        assert.equal(font().size, 11);
        typeTokens['--chart-text-size'] = '12';
        tooltipChecks += 3;
    }
}
console.log(`${24 + tooltipChecks} Overview chart range/palette/typography assertions passed`);
