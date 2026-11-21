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
function fixture(withObserver = true, list = 'assets', storage = new Map(), rowCount = 21, navigation = {}) {
    const header = new Region();
    const body = new Region();
    const shellListeners = {};
    const rows = Array.from({length: rowCount}, () => ({}));
    const panel = {
        hidden: true,
        querySelectorAll: selector => selector === 'tbody tr' ? rows : [],
    };
    const toggle = {
        dataset: {disclosure: '1'},
        attrs: {'aria-controls': 'panel-1', 'aria-expanded': 'false'},
        closest: selector => selector === '[data-disclosure]' ? toggle : null,
        getAttribute(name) { return this.attrs[name]; },
        setAttribute(name, value) { this.attrs[name] = value; },
    };
    const root = {
        dataset: {summaryList: list},
        style: {setProperty(name, value) { this[name] = value; }},
        addEventListener(type, handler) { this[type] = handler; },
        querySelectorAll: () => [toggle],
        querySelector: selector => selector === '[data-summary-header]' ? header : body,
        closest: () => ({addEventListener: (type, fn) => { shellListeners[type] = fn; }}),
    };
    header.parentElement = {offsetHeight: 64};
    const observers = [];
    const windowListeners = {};
    const url = 'https://example.test/' + list;
    const window = {
        location: {href: navigation.href || url},
        performance: {getEntriesByType: () => [{type: navigation.type || 'navigate'}]},
        addEventListener: (type, fn) => { windowListeners[type] = fn; },
    };
    if (withObserver) window.ResizeObserver = class {
        constructor(fn) { this.fn = fn; this.targets = []; observers.push(this); }
        observe(target) { this.targets.push(target); }
    };
    const context = vm.createContext({
        window,
        document: {referrer: navigation.referrer ?? url, querySelectorAll: () => [root], getElementById: id => id === 'panel-1' ? panel : null},
        sessionStorage: {
            getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value),
            removeItem: key => storage.delete(key),
        },
    });
    vm.runInContext(source, context);
    return {header, body, root, observers, windowListeners, shellListeners, context, toggle, panel, rows};
}

for (const [list, key] of [['assets', 'txOpen'], ['portfolios', 'portfoliosOpen']]) {
    const storage = new Map([[key, '["1"]'], [key + 'Ref', 'https://example.test/' + list]]);
    const restored = fixture(true, list, storage);
    eq(restored.panel.hidden, false);
    eq(restored.toggle.getAttribute('aria-expanded'), 'true');
    eq(restored.rows.filter(row => !row.hidden), restored.rows);
    eq(fixture(true, list, new Map(storage), 21, {type: 'reload', referrer: ''}).panel.hidden, false);
    eq(fixture(true, list, new Map(storage), 21, {href: restored.context.window.location.href + '?portfolio=Other'}).panel.hidden, true);
    restored.root.click({target: restored.toggle});
    eq(restored.panel.hidden, true);
    eq(storage.get(key), '[]');

    const denied = new Proxy({}, {get() { throw new Error('Storage is blocked'); }});
    const {root, panel, toggle, rows} = fixture(true, list, denied, 1001);
    root.click({target: {closest: () => null}}); // Sibling actions do not expand the summary.
    eq(panel.hidden, true);
    root.click({target: toggle});
    eq(panel.hidden, false);
    eq(toggle.getAttribute('aria-expanded'), 'true');
    eq(rows.filter(row => !row.hidden), rows);
    root.click({target: toggle});
    eq(toggle.getAttribute('aria-expanded'), 'false');
    root.click({target: toggle});
    eq(rows.filter(row => !row.hidden), rows);

    const empty = fixture(true, list, new Map(), 0);
    empty.root.click({target: empty.toggle});
    eq(empty.panel.hidden, false);
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
// Search applies to every match, including those beyond the old 100-card cap.
const assets = fs.readFileSync('portfolio_app/templates/assets.html', 'utf8');
function setupScript(template, name) {
    const start = template.indexOf('(function ' + name + '()');
    const end = template.indexOf('}());', start);
    assert(start !== -1 && end > start);
    return template.slice(start, end + 5);
}
const searchSource = setupScript(assets, 'setupAssetSearch');
const cards = Array.from({length: 505}, (_, i) => ({
    dataset: {symbol: (i % 3 ? 'ABC' : 'DEF') + i},
}));
const search = {
    value: '',
    addEventListener(type, handler) { assert.equal(type, 'input'); this.input = handler; },
};
vm.runInNewContext(searchSource, {
    document: {querySelectorAll: () => cards, getElementById: () => search},
});
function visible(expected) { eq(cards.filter(card => !card.hidden), expected); }
visible(cards);
search.value = ' bc ';
search.input();
eq(search.value, ' BC ');
visible(cards.filter((_, i) => i % 3 !== 0));
search.value = 'absent';
search.input();
visible([]);
search.value = '';
search.input();
visible(cards);
// Empty lists and absent search controls remain safe.
vm.runInNewContext(searchSource, {
    document: {querySelectorAll: () => [], getElementById: () => search},
});
search.input();
checks++;
vm.runInNewContext(searchSource, {document: {getElementById: () => null}});
checks++;
console.log(`${checks} summary-list assertions passed`);
