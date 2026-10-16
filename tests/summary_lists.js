/* Behavioral checks; no browser or dependencies. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('portfolio_app/static/js/summary_lists.js', 'utf8');
let checks = 0;
function eq(actual, expected) { assert.deepEqual(actual, expected); checks++; }

class Region {
    constructor(width = 400, content = 1100) {
        this.clientWidth = width;
        this.scrollWidth = content;
        this.left = 0;
        this.writes = 0;
        this.listeners = [];
        this.firstElementChild = {};
    }
    get scrollLeft() { return this.left; }
    set scrollLeft(value) {
        this.left = Math.max(0, Math.min(value, this.scrollWidth - this.clientWidth));
        this.writes++;
    }
    addEventListener(type, fn, options) { this.listeners.push({type, fn, options}); }
    scroll(left, target = this) {
        this.scrollLeft = left;
        this.listeners.forEach(({fn}) => fn({target}));
    }
}
function fixture(withObserver = true) {
    const header = new Region();
    const body = new Region();
    const shellListeners = {};
    const root = {
        dataset: {},
        style: {setProperty(name, value) { this[name] = value; }},
        querySelector: selector => selector === '[data-summary-header]' ? header : body,
        closest: () => ({addEventListener: (type, fn) => { shellListeners[type] = fn; }}),
    };
    header.parentElement = {offsetHeight: 64};
    const observers = [];
    const windowListeners = {};
    const window = {addEventListener: (type, fn) => { windowListeners[type] = fn; }};
    if (withObserver) window.ResizeObserver = class {
        constructor(fn) { this.fn = fn; this.targets = []; observers.push(this); }
        observe(target) { this.targets.push(target); }
    };
    const context = vm.createContext({window, document: {querySelectorAll: () => [root]}});
    vm.runInContext(source, context);
    return {header, body, root, observers, windowListeners, shellListeners, context};
}

const f = fixture();
eq(f.header.tabIndex, 0);
eq(f.body.tabIndex, 0);
eq(f.observers[0].targets.length, 4);
eq(f.root.style['--summary-header-height'], '64px');
eq(f.header.listeners[0].options.passive, true);
eq(f.body.listeners[0].options.passive, true);
eq(Object.keys(f.windowListeners), []); // No vertical/window scrolling handler.

for (const left of [1, 135.5, 699, 700, 500, 0]) {
    f.header.scroll(left);
    eq(f.body.scrollLeft, left);
    const writes = f.header.writes;
    f.body.listeners[0].fn({target: f.body}); // Async counterpart scroll event.
    eq(f.header.writes, writes); // No feedback write.
}
for (const left of [400, 123.25, 650, 0]) {
    f.body.scroll(left);
    eq(f.header.scrollLeft, left);
}

// Nested ledger scrolling must not move the outer headings.
f.header.scroll(300);
f.body.listeners[0].fn({target: new Region()});
eq(f.header.scrollLeft, 300);
eq(f.body.scrollLeft, 300);

// Rapid native edits and queued events converge without timers.
for (let i = 0; i < 100; i++) f.body.scroll(i * 7);
eq(f.header.scrollLeft, 693);
f.header.listeners[0].fn({target: f.header});
eq(f.body.scrollLeft, 693);

// Widening/sidebar collapse clamps at the new end; no extra focus stop when fit.
f.header.clientWidth = f.body.clientWidth = 1000;
f.header.parentElement.offsetHeight = 48;
f.observers[0].fn();
eq(f.root.style['--summary-header-height'], '48px');
eq(f.body.scrollLeft, 100);
eq(f.header.scrollLeft, 100);
f.header.clientWidth = f.body.clientWidth = 1100;
f.observers[0].fn();
eq(f.body.scrollLeft, 0);
eq(f.header.scrollLeft, 0);
eq(f.header.tabIndex, -1);
eq(f.body.tabIndex, -1);
// Narrowing and track changes restore native keyboard access.
f.header.clientWidth = f.body.clientWidth = 320;
f.observers[0].fn();
eq(f.header.tabIndex, 0);
eq(f.body.tabIndex, 0);

vm.runInContext(source, f.context);
eq(f.header.listeners.length, 1);
eq(f.body.listeners.length, 1);
eq(f.observers.length, 1);

const fallback = fixture(false);
fallback.body.scroll(500);
fallback.header.clientWidth = fallback.body.clientWidth = 900;
fallback.windowListeners.resize();
eq(fallback.header.scrollLeft, 200);
fallback.header.clientWidth = fallback.body.clientWidth = 1100;
fallback.shellListeners.transitionend();
eq(fallback.body.tabIndex, -1);
eq(fallback.header.scrollLeft, 0);

// Empty page and incomplete roots are harmless; neither installs listeners.
vm.runInNewContext(source, {window: {}, document: {querySelectorAll: () => []}});
checks++;
vm.runInNewContext(source, {window: {}, document: {querySelectorAll: () => [{
    dataset: {}, querySelector: () => null,
}]}});
checks++;
// Exercise the actual Assets pagination renderer: uniform rows retain their
// visibility and classes through search resets and later pages.
const assets = fs.readFileSync('portfolio_app/templates/assets.html', 'utf8');
const paginationStart = assets.indexOf('(function setupOuterPagination()');
const paginationEnd = assets.indexOf('}());', paginationStart) + 5;
assert(paginationStart !== -1 && paginationEnd > paginationStart);
const cards = Array.from({length: 205}, () => {
    const classes = new Set();
    return {style: {}, classList: {
        contains: name => classes.has(name),
        remove: name => classes.delete(name),
        toggle(name, on) { if (on) classes.add(name); else classes.delete(name); },
    }};
});
let pagination;
const paginationWindow = {OnePortfolioPagination: {render: (_, config) => { pagination = config; }}};
vm.runInNewContext(assets.slice(paginationStart, paginationEnd), {
    window: paginationWindow,
    document: {
        querySelectorAll: () => cards,
        getElementById: () => ({dataset: {paginationLabel: 'Asset Pages'}}),
    },
});
function checkPage(expected) {
    const visible = cards.filter(card => card.style.display !== 'none');
    eq(visible, expected);
    eq(cards
        .some(card => card.classList.contains('summary-row--alternate')), false);
}
checkPage(cards.slice(0, 100));
pagination.onPageChange(2);
checkPage(cards.slice(100, 200));
pagination.onPageChange(3);
checkPage(cards.slice(200));
cards.forEach((card, index) => card.classList.toggle('sym-filter-hide', index % 3 === 0));
paginationWindow.refreshOuterPagination(true);
const matches = cards.filter(card => !card.classList.contains('sym-filter-hide'));
checkPage(matches.slice(0, 100));
pagination.onPageChange(2);
checkPage(matches.slice(100));
cards.forEach(card => card.classList.toggle('sym-filter-hide', true));
paginationWindow.refreshOuterPagination(true);
checkPage([]);
cards.forEach(card => card.classList.toggle('sym-filter-hide', false));
paginationWindow.refreshOuterPagination(true);
checkPage(cards.slice(0, 100));
// Portfolios pagination also works without a row-presentation controller.
const portfolios = fs.readFileSync('portfolio_app/templates/portfolios.html', 'utf8');
const portfoliosStart = portfolios.indexOf('(function setupPortfolioOuterPagination()');
const portfoliosEnd = portfolios.indexOf('}());', portfoliosStart) + 5;
assert(portfoliosStart !== -1 && portfoliosEnd > portfoliosStart);
vm.runInNewContext(portfolios.slice(portfoliosStart, portfoliosEnd), {
    window: paginationWindow,
    document: {
        querySelectorAll: () => cards,
        getElementById: () => ({dataset: {paginationLabel: 'Portfolio Pages'}}),
    },
});
checkPage(cards.slice(0, 100));
pagination.onPageChange(3);
checkPage(cards.slice(200));
pagination.onPageChange(2);
checkPage(cards.slice(100, 200));
console.log(`${checks} summary-list assertions passed`);
