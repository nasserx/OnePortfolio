// Execute production shell/menu/calendar adapters in a DOM model. No browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let checks = 0;
const eq = (actual, expected) => { assert.equal(actual, expected); checks++; };
class Element {
    constructor(tag = 'div', attrs = {}) {
        this.tag = tag; this.attrs = {...attrs}; this.children = []; this.listeners = {};
        this.dataset = new Proxy({}, {
            get: (_, name) => this.attrs['data-' + name.replace(/[A-Z]/g, letter => '-' + letter.toLowerCase())],
            set: (_, name, value) => { this.attrs['data-' + name.replace(/[A-Z]/g, letter => '-' + letter.toLowerCase())] = String(value); return true; },
        });
        this.style = {}; this.value = ''; this.textContent = '';
        this.disabled = false; this.rect = {top: 100, bottom: 132, left: 100};
        this.scrollTop = 0; this.scrollLeft = 0; this.offsetHeight = 250; this.offsetWidth = 212;
        this.classList = {
            contains: name => this.className.split(' ').includes(name),
            add: name => { if (!this.classList.contains(name)) this.className += ' ' + name; },
            remove: name => { this.className = this.className.split(' ').filter(n => n !== name).join(' '); },
        };
    }
    get id() { return this.attrs.id || ''; } set id(value) { this.attrs.id = value; }
    get className() { return this.attrs.class || ''; } set className(value) { this.attrs.class = value; }
    get hidden() { return 'hidden' in this.attrs; } set hidden(value) { if (value) this.attrs.hidden = ''; else delete this.attrs.hidden; }
    get inert() { return 'inert' in this.attrs; } set inert(value) { if (value) this.attrs.inert = ''; else delete this.attrs.inert; }
    get tabIndex() { return this.attrs.tabindex === undefined ? (this.matches('button, input, select, a[href]') ? 0 : -1) : Number(this.attrs.tabindex); }
    set tabIndex(value) { this.attrs.tabindex = String(value); }
    get isConnected() { return this === document || !!this.parentElement?.isConnected; }
    setAttribute(name, value) { this.attrs[name] = String(value); }
    getAttribute(name) { return this.attrs[name] ?? null; }
    removeAttribute(name) { delete this.attrs[name]; }
    matches(selector) {
        return selector.split(',').some(raw => {
            const s = raw.trim();
            const attribute = s.match(/\[([^=\]]+)(?:="([^"]*)")?\]/);
            if (attribute && (!(attribute[1] in this.attrs) || (attribute[2] !== undefined && this.attrs[attribute[1]] !== attribute[2]))) return false;
            const plain = s.replace(/\[[^\]]+\]/g, '');
            const id = plain.match(/#([\w-]+)/);
            if (id && this.id !== id[1]) return false;
            if ([...plain.matchAll(/\.([\w-]+)/g)].some(match => !this.classList.contains(match[1]))) return false;
            const tag = plain.match(/^[\w-]+/);
            return !tag || tag[0] === this.tag;
        });
    }
    closest(selector) { return this.matches(selector) ? this : this.parentElement?.closest(selector) || null; }
    contains(element) { return element === this || this.children.some(child => child.contains(element)); }
    querySelectorAll(selector) {
        // Shell's link query is the sole descendant selector in these adapters.
        if (selector === '.sidenav a[href]') return this.querySelectorAll('a[href]').filter(e => e.closest('.sidenav'));
        return this.children.flatMap(child => [...(child.matches(selector) ? [child] : []), ...child.querySelectorAll(selector)]);
    }
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
    appendChild(child) {
        if (child.tag === 'fragment') { child.children.slice().forEach(c => this.appendChild(c)); return child; }
        child.parentElement = this; this.children.push(child); return child;
    }
    append(...children) { children.forEach(c => this.appendChild(c)); }
    replaceChildren(...children) { this.children.forEach(c => { c.parentElement = null; }); this.children = []; this.append(...children); }
    getClientRects() { return this.closest('[hidden], .d-none') ||
        (this.matches('.sidenav__close') && !media.matches) ? [] : [this.rect]; }
    getBoundingClientRect() { return this.rect; }
    scrollIntoView() {}
    focus() { if (!this.closest('[inert]')) { document.activeElement = this; this.emit('focusin'); } }
    click() { this.emit('click'); }
    addEventListener(type, fn, options = {}) { (this.listeners[type] ||= []).push({fn, capture: options === true || options.capture, once: options.once}); }
    removeEventListener(type, fn) { this.listeners[type] = (this.listeners[type] || []).filter(l => l.fn !== fn); }
    emit(type, fields = {}) {
        const event = {type, target: this, defaultPrevented: false, stopped: false, ...fields,
            preventDefault() { this.defaultPrevented = true; }, stopPropagation() { this.stopped = true; }};
        const chain = []; for (let node = this; node; node = node.parentElement) chain.push(node);
        const call = (node, capture) => {
            for (const listener of [...(node.listeners[type] || [])]) if (!!listener.capture === capture) {
                listener.fn.call(node, event); if (listener.once) node.removeEventListener(type, listener.fn);
            }
        };
        for (const node of chain.slice().reverse()) { call(node, true); if (event.stopped) return event; }
        for (const node of chain) { call(node, false); if (event.stopped) break; }
        return event;
    }
}
const document = new Element('document');
const html = document.appendChild(new Element('html'));
document.documentElement = html; html.clientWidth = 1000;
document.body = html.appendChild(new Element('body')); document.body.style.overflow = 'auto';
document.activeElement = document.body; document.readyState = 'loading';
document.getElementById = id => document.querySelector('#' + id);
document.createElement = tag => new Element(tag);
document.createElementNS = (_, tag) => new Element(tag);
document.createDocumentFragment = () => new Element('fragment');
const add = (parent, tag, attrs) => parent.appendChild(new Element(tag, attrs));
const media = {matches: true, addEventListener(_, fn) { this.change = fn; }};
const modalInstances = new Map();
const dropdownInstances = new Map();
const microtasks = [];
const flush = () => { while (microtasks.length) microtasks.shift()(); };
const window = {innerHeight: 800, getComputedStyle: () => ({visibility: 'visible'}),
    matchMedia: () => media, localStorage: {setItem() {}}, location: {},
    bootstrap: {
        Modal: {getOrCreateInstance(element) {
            if (!modalInstances.has(element)) modalInstances.set(element, {show(target) {
                const e = element.emit('show.bs.modal', {relatedTarget: target});
                if (!e.defaultPrevented) { element.classList.add('show'); element.focus(); }
            }, hide() { element.classList.remove('show'); element.emit('hidden.bs.modal'); }});
            return modalInstances.get(element);
        }},
        Dropdown: {getOrCreateInstance(trigger, config) {
            if (!dropdownInstances.has(trigger)) dropdownInstances.set(trigger, {config, opens: 0,
                show() { this.opens++; trigger.setAttribute('aria-expanded', 'true'); }});
            return dropdownInstances.get(trigger);
        }},
    },
};
const context = vm.createContext({document, window, console, Date, queueMicrotask: fn => microtasks.push(fn)});
const read = name => fs.readFileSync('portfolio_app/static/js/' + name, 'utf8');
vm.runInContext(read('overlays.js'), context);
let shellSource = read('shell.js');
shellSource = shellSource.replace('  function mountAll() {', '  window.TestShell = {SideNav, CommandPalette};\n  function mountAll() {');
vm.runInContext(shellSource, context);
vm.runInContext(read('main.js') + '\nwindow.TestMain = {ActionMenuManager, initDateField, closeDatePickers};', context);
const overlays = window.OnePortfolioOverlays;
const shell = add(document.body, 'div', {class: 'shell', 'data-nav-open': 'false'});
const drawer = add(shell, 'aside', {id: 'sidenav', class: 'sidenav'});
const closeNav = add(drawer, 'button', {'data-nav-close': '', class: 'sidenav__close'});
const search = add(drawer, 'button', {'data-palette-open': ''});
const navLink = add(drawer, 'a', {href: '/assets'});
const backdrop = add(shell, 'button', {class: 'shell__backdrop'});
const content = add(shell, 'main');
const openNav = add(content, 'button', {'data-nav-open-toggle': ''});
const pageAction = add(content, 'button', {'data-command': 'Create Portfolio'});
const disabledAction = add(content, 'button', {'data-command': 'Disabled'}); disabledAction.disabled = true;
const hiddenAction = add(content, 'button', {'data-command': 'Hidden', hidden: ''});
const preserved = add(document.body, 'div', {inert: ''});
const paletteRoot = add(document.body, 'div', {id: 'commandPalette', hidden: ''});
const input = add(paletteRoot, 'input', {id: 'commandPaletteInput'});
const list = add(paletteRoot, 'ul', {id: 'commandPaletteList'});
const status = add(paletteRoot, 'span', {id: 'commandPaletteStatus'});
const empty = add(paletteRoot, 'p', {id: 'commandPaletteEmpty'});
const data = add(document.body, 'script', {id: 'commandPaletteData'});
data.textContent = JSON.stringify([{label: 'Overview', href: '/', group: 'Navigate'}]);
const nav = new window.TestShell.SideNav(); nav.mount();
const palette = new window.TestShell.CommandPalette(); palette.mount();
eq(drawer.inert, true);
openNav.click(); flush();
eq(drawer.inert, false); eq(drawer.getAttribute('role'), 'dialog');
eq(drawer.getAttribute('aria-modal'), 'true'); eq(document.activeElement, closeNav);
eq(content.inert, true); eq(document.body.style.overflow, 'hidden'); eq(openNav.getAttribute('aria-expanded'), 'true');
navLink.focus(); eq(navLink.emit('keydown', {key: 'Tab'}).defaultPrevented, true); eq(document.activeElement, closeNav);
eq(closeNav.emit('keydown', {key: 'Tab', shiftKey: true}).defaultPrevented, true); eq(document.activeElement, navLink);
search.click(); flush();
eq(shell.getAttribute('data-nav-open'), 'false'); eq(drawer.inert, true);
eq(paletteRoot.hidden, false); eq(document.activeElement, input); eq(shell.inert, true);
eq(palette.matches.length, 2); eq(input.getAttribute('aria-expanded'), 'true');
eq(input.getAttribute('aria-activedescendant'), 'command-option-0');
input.emit('keydown', {key: 'ArrowDown'});
eq(input.getAttribute('aria-activedescendant'), 'command-option-1');
eq(list.children[1].getAttribute('aria-selected'), 'true');
input.emit('keydown', {key: 'ArrowDown'}); eq(input.getAttribute('aria-activedescendant'), 'command-option-0');
input.emit('keydown', {key: 'ArrowUp'}); eq(input.getAttribute('aria-activedescendant'), 'command-option-1');
eq(input.emit('keydown', {key: 'Tab'}).defaultPrevented, true); eq(document.activeElement, input);
eq(input.emit('keydown', {key: 'Tab', shiftKey: true}).defaultPrevented, true);
input.value = 'missing'; input.emit('input');
eq(list.children.length, 0); eq(empty.hidden, false); eq(status.textContent, 'No matches');
eq(input.getAttribute('aria-activedescendant'), null);
input.emit('keydown', {key: 'Enter'}); eq(paletteRoot.hidden, false);
input.emit('keydown', {key: 'Escape'});
eq(paletteRoot.hidden, true); eq(document.activeElement, openNav); eq(shell.inert, false);
eq(preserved.inert, true); eq(document.body.style.overflow, 'auto');
openNav.click(); flush(); backdrop.click(); flush(); eq(document.activeElement, openNav); eq(drawer.inert, true);
openNav.click(); flush(); media.matches = false; media.change();
eq(drawer.inert, false); eq(drawer.getAttribute('role'), null); eq(drawer.getAttribute('aria-modal'), null);
eq(document.activeElement, search);
eq(document.body.style.overflow, 'auto'); eq(openNav.getAttribute('aria-expanded'), 'false');
media.matches = true; media.change(); eq(drawer.inert, true); eq(document.activeElement, openNav);

const modal = add(content, 'div', {class: 'modal', tabindex: '-1'});
const modalField = add(modal, 'input');
openNav.focus(); palette.open();
window.OnePortfolioDialogs.show(modal, pageAction); flush();
window.OnePortfolioDialogs.show(modal, pageAction); flush();
eq(modal.listeners['hidden.bs.modal'].length, 1);
eq(paletteRoot.hidden, true); eq(shell.inert, false); eq(overlays.blocked(), true);
modalField.focus(); eq(document.activeElement, modalField);
eq(modalField.emit('keydown', {key: 'Tab'}).defaultPrevented, false);
palette.open(); eq(paletteRoot.hidden, true);
eq(modalField.emit('keydown', {key: 'k', ctrlKey: true}).defaultPrevented, false);
nav.setOpen(true); eq(shell.getAttribute('data-nav-open'), 'false');
window.bootstrap.Modal.getOrCreateInstance(modal).hide(); flush();
eq(overlays.blocked(), false); eq(document.activeElement, pageAction);
// Data-API modal events do not acquire the programmatic return callback.
eq((modal.listeners['hidden.bs.modal'] || []).length, 0);
const cancelShow = event => event.preventDefault(); modal.addEventListener('show.bs.modal', cancelShow);
window.OnePortfolioDialogs.show(modal, pageAction); flush();
eq(overlays.blocked(), false); eq((modal.listeners['hidden.bs.modal'] || []).length, 0);
modal.removeEventListener('show.bs.modal', cancelShow);

let activations = 0; pageAction.addEventListener('click', () => { activations++; });
palette.open(openNav); input.value = 'create'; input.emit('input');
eq(input.emit('keydown', {key: 'Enter', isComposing: true}).defaultPrevented, false); eq(activations, 0);
input.emit('keydown', {key: 'Enter'}); flush(); eq(activations, 1); eq(document.activeElement, pageAction);
palette.open(openNav); input.value = 'overview'; input.emit('input'); input.emit('keydown', {key: 'Enter'});
eq(window.location.href, '/'); eq(paletteRoot.hidden, true);

const actionMenu = add(content, 'div', {class: 'action-menu'});
const trigger = add(actionMenu, 'button', {class: 'action-menu__trigger'});
const menu = add(actionMenu, 'ul', {class: 'action-menu__menu'});
const item = text => { const li = add(menu, 'li'); const button = add(li, 'button', {class: 'dropdown-item'}); button.textContent = text; return button; };
const rename = item('Rename'); const remove = item('Remove'); const deposit = item('Deposit');
const disabled = item('Disabled'); disabled.disabled = true;
const hidden = item('Hidden'); hidden.hidden = true;
new window.TestMain.ActionMenuManager(); new window.TestMain.ActionMenuManager();
eq(trigger.listeners.keydown.length, 1); eq(trigger.getAttribute('aria-haspopup'), 'menu');
eq(trigger.getAttribute('aria-controls'), menu.id); eq(menu.getAttribute('aria-labelledby'), trigger.id);
eq(menu.getAttribute('role'), 'menu'); eq(rename.getAttribute('role'), 'menuitem'); eq(rename.tabIndex, -1);
eq(dropdownInstances.get(trigger).config.boundary, 'viewport');
eq(dropdownInstances.get(trigger).config.popperConfig({}).strategy, 'fixed');
trigger.emit('keydown', {key: 'Enter'}); eq(document.activeElement, rename);
rename.emit('keydown', {key: 'End'}); eq(document.activeElement, deposit);
deposit.emit('keydown', {key: 'Home'}); eq(document.activeElement, rename);
rename.emit('keydown', {key: 'r'}); eq(document.activeElement, remove);
remove.emit('keydown', {key: 'r'}); eq(document.activeElement, rename);
trigger.emit('hidden.bs.dropdown'); rename.emit('keydown', {key: 'd'}); eq(document.activeElement, deposit);
for (const key of ['ArrowDown', 'ArrowUp', 'Escape', 'Tab']) eq(deposit.emit('keydown', {key}).defaultPrevented, false);
trigger.emit('keydown', {key: ' '}); eq(document.activeElement, rename);
remove.addEventListener('click', () => window.OnePortfolioDialogs.show(modal));
remove.click(); flush(); window.bootstrap.Modal.getOrCreateInstance(modal).hide(); flush();
eq(document.activeElement, trigger);
// Hidden/removed openers never receive focus on modal dismissal.
window.OnePortfolioDialogs.show(modal, pageAction); flush(); pageAction.hidden = true;
window.bootstrap.Modal.getOrCreateInstance(modal).hide(); flush(); eq(document.activeElement === pageAction, false); pageAction.hidden = false;

let calendarOptions;
window.flatpickr = (element, options) => {
    calendarOptions = options;
    const calendar = add(options.appendTo, 'div', {class: 'flatpickr-calendar'});
    const instance = {calendarContainer: calendar, isOpen: true, close() { this.isOpen = false; }};
    options.onReady([], '', instance); element._flatpickr = instance; return instance;
};
modalField.value = '2024-01-02'; modalField.setAttribute('data-datepicker', 'flatpickr');
const calendar = window.TestMain.initDateField(modalField);
eq(calendarOptions.appendTo, modal); eq(calendarOptions.dateFormat, 'Y-m-d'); eq(calendarOptions.allowInput, true);
eq(calendar.calendarContainer.classList.contains('op-flatpickr'), true); eq(modalField.value, '2024-01-02');
eq(window.TestMain.initDateField(modalField), null);
modal.rect = {top: 0, left: 0}; modal.scrollTop = 40;
calendarOptions.position(calendar); eq(calendar.calendarContainer.style.top, '174px'); eq(calendar.calendarContainer.style.left, '100px');
modalField.rect = {top: 650, bottom: 682, left: 950}; calendarOptions.position(calendar);
eq(calendar.calendarContainer.style.top, '438px'); eq(calendar.calendarContainer.style.left, '780px');
const day = add(calendar.calendarContainer, 'button'); day.focus();
const escape = day.emit('keydown', {key: 'Escape'});
eq(escape.defaultPrevented, true); eq(escape.stopped, true); eq(calendar.isOpen, false); eq(document.activeElement, modalField);
eq(modalField.emit('keydown', {key: 'Escape'}).stopped, false);
calendar.isOpen = true; calendar.calendarContainer.emit('scroll'); eq(calendar.isOpen, true);
modal.emit('scroll'); eq(calendar.isOpen, false);
calendar.isOpen = true; window.TestMain.closeDatePickers(modal); eq(calendar.isOpen, false);
const outsideDate = add(content, 'input'); outsideDate.readOnly = true;
window.TestMain.initDateField(outsideDate); eq(calendarOptions.appendTo, document.body); eq(calendarOptions.position, 'auto'); eq(calendarOptions.clickOpens, false);
console.log(`${checks} overlay, menu, palette, drawer and calendar assertions passed`);
