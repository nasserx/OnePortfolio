// Execute production feedback/transport without a browser or DOM dependency.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let checks = 0;
function eq(actual, expected) { assert.equal(actual, expected); checks++; }
class Element {
    constructor(tag = 'div', attrs = {}) {
        this.tag = tag; this.attrs = {...attrs}; this.children = []; this.listeners = {};
        this.value = ''; this.textContent = ''; this.dataset = {}; this.disabled = false;
        this.validity = {valid: true}; this.validationMessage = 'Invalid value.';
        this.classList = {
            contains: n => this.className.split(/\s+/).includes(n),
            add: (...ns) => { this.className = [...new Set([...this.className.split(/\s+/).filter(Boolean), ...ns])].join(' '); },
            remove: (...ns) => { this.className = this.className.split(/\s+/).filter(n => !ns.includes(n)).join(' '); },
            toggle: (n, on) => on ? this.classList.add(n) : this.classList.remove(n),
        };
    }
    get id() { return this.attrs.id || ''; } set id(v) { this.attrs.id = v; }
    get name() { return this.attrs.name || ''; }
    get type() { return this.attrs.type || ''; }
    get className() { return this.attrs.class || ''; } set className(v) { this.attrs.class = v; }
    get hidden() { return 'hidden' in this.attrs; } set hidden(v) { if (v) this.attrs.hidden = ''; else delete this.attrs.hidden; }
    get firstChild() { return this.children[0]; }
    get form() { return this.closest('form'); }
    setAttribute(n, v) { this.attrs[n] = v; }
    getAttribute(n) { return this.attrs[n] ?? null; }
    removeAttribute(n) { delete this.attrs[n]; }
    matches(selector) {
        return selector.split(',').some(raw => {
            const s = raw.trim();
            if (s.startsWith('#')) return this.id === s.slice(1);
            if (s.startsWith('.')) return this.classList.contains(s.slice(1));
            if (s.startsWith('[')) return s.slice(1, -1) in this.attrs;
            if (s === 'button[type="submit"]') return this.tag === 'button' && this.type === 'submit';
            return this.tag === s;
        });
    }
    closest(s) { return this.matches(s) ? this : this.parentElement?.closest(s) || null; }
    querySelectorAll(s) { return this.children.flatMap(c => [...(c.matches(s) ? [c] : []), ...c.querySelectorAll(s)]); }
    querySelector(s) { return this.querySelectorAll(s)[0] || null; }
    appendChild(c) { c.parentElement = this; this.children.push(c); return c; }
    insertBefore(c, b) { c.parentElement = this; this.children.splice(b ? this.children.indexOf(b) : 0, 0, c); }
    addEventListener(type, fn, capture = false) { (this.listeners[type] ||= []).push({fn, capture}); }
    async emit(type) {
        const e = {target: this, prevented: false, stopped: false,
            preventDefault() { this.prevented = true; }, stopImmediatePropagation() { this.stopped = true; }};
        const parents = []; for (let p = this.parentElement; p; p = p.parentElement) parents.unshift(p);
        for (const p of parents) for (const l of p.listeners[type] || []) if (l.capture) await l.fn(e);
        for (const l of this.listeners[type] || []) { if (e.stopped) break; await l.fn.call(this, e); }
        return e;
    }
    getClientRects() { return this.closest('[hidden], .d-none') ? [] : [{}]; }
    focus() { document.activeElement = this; }
}
const document = new Element('document');
document.getElementById = id => document.querySelector('#' + id);
document.createElement = tag => new Element(tag);
let respond, reject, requests = 0, reloads = 0;
const window = {location: {reload() { reloads++; }}};
const context = vm.createContext({document, window, queueMicrotask, console: {error() {}},
    FormData: class {}, sessionStorage: {setItem() {}},
    fetch() { requests++; return new Promise((resolve, fail) => { respond = resolve; reject = fail; }); },
});
vm.runInContext(fs.readFileSync('portfolio_app/static/js/form_feedback.js', 'utf8'), context);
const main = fs.readFileSync('portfolio_app/static/js/main.js', 'utf8');
vm.runInContext(main.slice(main.indexOf('class ModalAjaxHandler'), main.indexOf('class InvestmentPortfolioApp')) + '\nglobalThis.Transport = ModalAjaxHandler;', context);
const forms = window.OnePortfolioForms;
let index = 0;
function fixture({modal = true, server = false} = {}) {
    const overlay = modal ? document.appendChild(new Element('div', {class: 'modal', id: `modal-${++index}`})) : null;
    const form = (overlay || document).appendChild(new Element('form'));
    const body = form.appendChild(new Element('div', {class: modal ? 'modal-body' : 'field-group'}));
    const input = body.appendChild(new Element('input', {id: `amount-${++index}`, name: 'amount', required: '', 'aria-describedby': 'help'}));
    const error = body.appendChild(new Element('div', {id: `${input.id}-error`, 'data-field-error': input.id, role: 'alert'}));
    if (server) error.textContent = 'Server rejected this amount.';
    const button = form.appendChild(new Element('button', {type: 'submit'})); button.innerHTML = 'Save';
    const controller = forms.register(form, [{selector: '#' + input.id, validate: v => v === 'valid' ? {ok: true} : {ok: false, message: 'Enter a valid amount.'}}]);
    return {overlay, form, input, error, button, controller};
}
const tick = () => new Promise(resolve => setImmediate(resolve));
async function run() {
    const {form, input, error, controller, overlay} = fixture();
    eq(form.noValidate, true); eq(input.getAttribute('required'), '');
    eq(forms.register(form), controller); eq(form.listeners.submit.length, 1);
    await overlay.emit('show.bs.modal'); overlay.classList.add('show'); await overlay.emit('shown.bs.modal');
    for (const t of ['blur', 'change', 'input']) { await input.emit(t); eq(error.textContent, ''); }
    eq((await form.emit('submit')).prevented, true);
    eq(error.textContent, 'Enter a valid amount.'); eq(document.activeElement, input);
    eq(input.getAttribute('aria-describedby'), `help ${input.id}-error`); eq(input.getAttribute('aria-invalid'), 'true');
    input.value = 'valid'; await input.emit('input');
    eq(error.hidden, true); eq(input.getAttribute('aria-invalid'), null); eq(input.getAttribute('aria-describedby'), 'help');
    eq((await form.emit('submit')).prevented, false);
    controller.applyErrors({amount: 'Server rule', __all__: 'General error', unknown: '<script>literal</script>'});
    eq(controller.general().textContent, 'General error <script>literal</script>'); eq(controller.general().classList.contains('d-none'), false);
    await input.emit('change'); eq(error.textContent, 'Server rule');
    input.value = 'invalid'; await input.emit('input'); eq(error.textContent, 'Enter a valid amount.');
    forms.prepare(overlay.id); eq(controller.submitted, false); eq(error.hidden, true);
    await input.emit('change'); eq(error.textContent, '');
    controller.showGeneral('Max failed', true); eq(document.activeElement, controller.general()); eq(controller.submitted, false);
    overlay.classList.remove('show'); await overlay.emit('hidden.bs.modal');
    eq(controller.general().hidden, true); eq(input.getAttribute('required'), '');
    const focus = document.activeElement; controller.applyErrors({__all__: 'Late'}); eq(document.activeElement, focus);
    const server = fixture({server: true}); eq(server.controller.submitted, true);
    forms.prepare(server.overlay.id); await server.input.emit('input'); await server.overlay.emit('show.bs.modal');
    eq(server.error.textContent, 'Server rejected this amount.');
    server.overlay.classList.add('show'); await server.overlay.emit('shown.bs.modal'); eq(document.activeElement, server.input);
    await server.overlay.emit('hidden.bs.modal'); eq(server.error.hidden, true); eq(server.controller.submitted, false);
    const account = fixture({modal: false, server: true}); eq(document.activeElement, account.input);
    const proxy = form.appendChild(new Element('button', {'data-feedback-for': input.id})); proxy.dataset.feedbackFor = input.id;
    input.setAttribute('aria-hidden', 'true'); overlay.classList.add('show');
    controller.applyErrors({amount: 'Choose a type'}); eq(document.activeElement, proxy);
    eq(proxy.getAttribute('aria-invalid'), 'true'); eq(proxy.getAttribute('aria-describedby'), error.id);
    controller.reset(); eq(proxy.getAttribute('aria-invalid'), null);
    proxy.disabled = true; controller.applyErrors({amount: 'Hidden field error', __all__: 'Other error'});
    eq(controller.general().textContent, 'Hidden field error Other error'); eq(document.activeElement, controller.general());
    const native = fixture({modal: false}); forms.register(native.form, []); native.input.validity = {valid: false, valueMissing: true};
    eq((await native.form.emit('submit')).prevented, true); eq(native.error.textContent, 'This field is required.');
    native.input.disabled = true; eq((await native.form.emit('submit')).prevented, false);
    const duplicate = fixture({modal: false});
    const hidden = new Element('input', {type: 'hidden', name: 'amount'});
    duplicate.form.insertBefore(hidden, duplicate.form.firstChild);
    duplicate.controller.applyErrors({amount: 'Editable source error'});
    eq(duplicate.error.textContent, 'Editable source error'); eq(document.activeElement, duplicate.input);
    await duplicate.form.emit('reset'); eq(duplicate.controller.submitted, false); eq(duplicate.error.hidden, true);
    // Model synchronous DOM dispatch: capture queues validation, the existing
    // target listener normalizes text, then the microtask reads its result.
    duplicate.controller.submitted = true; duplicate.input.value = 'raw';
    duplicate.form.listeners.input[0].fn({target: duplicate.input});
    duplicate.input.value = 'valid'; await tick(); eq(duplicate.error.textContent, '');
    const business = fixture(); business.overlay.classList.add('show');
    business.controller.applyErrors({__all__: 'Insufficient cash'});
    eq(business.input.getAttribute('aria-invalid'), null);
    eq(document.activeElement, business.controller.general());
    eq(business.form.children[0].firstChild, business.controller.general());
    eq(business.controller.general().getAttribute('role'), 'alert');
    business.input.value = 'valid'; await business.input.emit('input');
    eq(business.controller.general().textContent, 'Insufficient cash');
    business.input.value = 'invalid'; eq((await business.form.emit('submit')).prevented, true);
    eq(business.controller.general().textContent, 'Insufficient cash');
    eq(business.error.textContent, 'Enter a valid amount.');
    business.input.value = 'valid'; await business.input.emit('input');
    eq(business.error.hidden, true); eq(business.controller.general().textContent, 'Insufficient cash');
    business.controller.showGeneral('Max unavailable', false, 'action');
    business.controller.clearGeneral('action'); eq(business.controller.general().textContent, 'Insufficient cash');
    business.controller.applyErrors({__all__: 'Insufficient cash', amount: 'Insufficient cash', unknown: 'Insufficient cash'});
    eq(business.controller.general().textContent, 'Insufficient cash'); eq(business.error.hidden, true);
    business.controller.applyErrors({amount: 'Invalid numeric value'});
    eq(business.controller.general().hidden, true); eq(business.input.getAttribute('aria-invalid'), 'true');
    // Promoting an inaccessible error must move it only once, even when the
    // summary already contains multiple general messages.
    business.input.setAttribute('aria-hidden', 'true');
    business.controller.showGeneral(['History conflict', 'Stale submission']);
    business.controller.focusErrors(); business.controller.focusErrors();
    eq(business.error.hidden, true);
    eq(business.controller.general().textContent, 'History conflict Stale submission Invalid numeric value');
    await business.overlay.emit('hidden.bs.modal'); eq(business.controller.general().hidden, true);
    eq(business.controller.submitted, false);
    const ajax = fixture(); ajax.overlay.classList.add('show'); context.Transport.prototype.handleForm.call({}, ajax.form, ajax.overlay);
    eq((await ajax.form.emit('submit')).prevented, true); eq(requests, 0);
    ajax.input.value = 'valid'; let pending = ajax.form.emit('submit'); await tick();
    eq(requests, 1); eq(ajax.button.disabled, true); eq((await ajax.form.emit('submit')).prevented, true); eq(requests, 1);
    respond({json: async () => ({success: false, errors: {amount: 'Rejected', __all__: 'Try again'}})}); await pending;
    eq(ajax.error.textContent, 'Rejected'); eq(ajax.button.innerHTML, 'Save'); eq(ajax.controller.pending, false);
    pending = ajax.form.emit('submit'); await tick();
    eq(ajax.controller.general().textContent, 'Try again');
    forms.prepare(ajax.overlay.id);
    respond({json: async () => ({success: false, errors: {amount: 'Old record'}})}); await pending;
    eq(ajax.error.textContent, ''); eq(ajax.controller.submitted, false);
    ajax.controller.applyErrors({__all__: 'Financial history conflict'});
    pending = ajax.form.emit('submit'); await tick(); reject(new Error('offline')); await pending;
    eq(ajax.controller.general().textContent, 'Financial history conflict Network error'); eq(ajax.button.disabled, false);
    pending = ajax.form.emit('submit'); await tick(); await ajax.overlay.emit('hidden.bs.modal');
    respond({json: async () => ({success: true})}); await pending; eq(reloads, 1);
    const otp = fixture({modal: false}); otp.input.id = 'code'; forms.register(otp.form, []);
    let submissions = 0; otp.form.requestSubmit = () => { submissions++; return otp.form.emit('submit'); };
    const html = fs.readFileSync('portfolio_app/templates/auth/verify_code.html', 'utf8');
    vm.runInContext(html.slice(html.indexOf("document.getElementById('code').addEventListener"), html.indexOf('</script>')), context);
    otp.input.value = '12a3'; await otp.input.emit('input'); eq(submissions, 0); eq(otp.input.value, '123');
    otp.input.value = '123456'; await otp.input.emit('input'); eq(submissions, 1); eq(otp.controller.submitted, true);
    console.log(`${checks} shared form lifecycle/transport assertions passed`);
}
run().catch(e => { console.error(e); process.exitCode = 1; });
