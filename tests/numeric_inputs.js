// Behavioral event-model tests; native browser undo/IME acceptance is separate.
// Run with node tests/numeric_inputs.js. No browser, packages or database.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const tasks = [];
const context = vm.createContext({ window: {}, queueMicrotask: task => tasks.push(task) });
vm.runInContext(fs.readFileSync(path.join(__dirname, '../portfolio_app/static/js/numeric_inputs.js'), 'utf8'), context);
const numeric = context.window.OnePortfolioNumeric;
let checks = 0;
function equal(actual, expected) { assert.equal(actual, expected); checks++; }
function flush() { while (tasks.length) tasks.shift()(); }
function event(type, props = {}) {
    const result = new Event(type, { cancelable: true });
    for (const [name, value] of Object.entries(props)) Object.defineProperty(result, name, { value });
    return result;
}
function send(target, type, props) {
    const result = event(type, props);
    target.dispatchEvent(result);
    return result;
}

class Field extends EventTarget {
    constructor(value = '', doc = new EventTarget()) {
        super();
        this.tagName = 'INPUT';
        this.type = 'text';
        this.dataset = { numeric: 'decimal' };
        this.ownerDocument = doc;
        doc.defaultView = { Event };
        this.form = new EventTarget();
        this.disabled = false;
        this.readOnly = false;
        this.writes = 0;
        this.selectionWrites = 0;
        this.native(value);
    }
    get value() { return this._value; }
    set value(value) { this.writes++; this.native(String(value)); }
    native(value, start = value.length, end = start, direction = 'none') {
        this._value = value;
        this.selectionStart = start;
        this.selectionEnd = end;
        this.selectionDirection = direction;
    }
    setSelectionRange(start, end, direction) {
        this.selectionWrites++;
        this.selectionStart = start;
        this.selectionEnd = end;
        this.selectionDirection = direction;
    }
    select(start, end = start, direction = 'none') {
        this.selectionStart = start;
        this.selectionEnd = end;
        this.selectionDirection = direction;
        this.ownerDocument.activeElement = this;
        send(this.ownerDocument, 'selectionchange');
    }
}
function field(value = '') {
    const input = new Field(value);
    numeric.register(input);
    input.updates = [];
    input.addEventListener('input', e => {
        if (!numeric.isComposing(input) && !numeric.shouldIgnoreEvent(e)) input.updates.push(input.value);
    });
    return input;
}
// Model native default editing separately from JS .value assignments so tests
// can prove the controller does not manipulate successful browser edits.
function insert(input, text, type = 'insertText') {
    const before = send(input, 'beforeinput', { inputType: type, data: text });
    if (!before.defaultPrevented) {
        const start = input.selectionStart;
        const next = numeric.candidate(input.value, start, input.selectionEnd, text);
        input.native(next, start + text.length);
        send(input, 'input', { inputType: type, data: text });
    }
    flush();
    return before;
}
function fallback(input, value, type = 'insertReplacementText', props = {}) {
    input.native(value);
    const result = send(input, 'input', { inputType: type, ...props });
    flush();
    return result;
}

// String grammar: no binary-number parsing, digit limits, trimming or cleanup.
for (const value of ['', '.', '0.', '12.', '.25', '00012.0300', '9007199254740993',
                     '0.' + '0'.repeat(2000) + '1', '9'.repeat(12000) + '.001']) {
    equal(numeric.inspect(value).editable, true);
    equal(numeric.inspect(value).complete, value !== '' && value !== '.');
}
for (const value of ['-1', '+1', '1e3', '1,000', '1,5', ' 1', '1 ', '12\n', '1\t2',
                     '1.2.3', '1x2', 'NaN', 'Infinity', '١٢', '１２', '1٫2', '$12', '\u200e12']) {
    equal(numeric.inspect(value).editable, false);
}
for (const value of ['0', '00.000', '.000', '0.']) equal(numeric.inspect(value).zero, true);
for (const value of ['', '.', '.001', '1', '1x']) equal(numeric.inspect(value).zero, false);
equal(numeric.inspect(1).editable, false);
equal(numeric.candidate('12.34', 1, 4, '0.'), '10.4');
equal(numeric.candidate('12', null, null, '3'), null);
equal(numeric.candidate('12', 2, 1, '3'), null);
equal(numeric.candidate('12', 0, 3, '3'), null);

// Valid native insertions remain untouched; rejected insertion is atomic.
{
    const input = field();
    for (const character of ['.', '0', '0', '1']) equal(insert(input, character).defaultPrevented, false);
    equal(input.value, '.001');
    equal(input.writes, 0);
    equal(input.selectionWrites, 0);
    equal(insert(input, 'x').defaultPrevented, true);
    equal(insert(input, '.').defaultPrevented, true);
    equal(input.value, '.001');
    equal(input.selectionStart, 4);
    equal(input.updates.length, 4);
    input.select(0, 1, 'backward');
    equal(insert(input, '2.').defaultPrevented, false);
    equal(input.value, '2.001');
    equal(input.selectionStart, 2);
    equal(input.writes, 0);
    send(input, 'focus');
    equal(input.selectionStart, 2);
    equal(send(input, 'keydown', { key: 'ArrowUp' }).defaultPrevented, false);
    equal(send(input, 'wheel').defaultPrevented, false);
    equal(send(input, 'keydown', { key: 'z', ctrlKey: true }).defaultPrevented, false);
}

// Valid paste uses the browser insertion, including selection replacement.
{
    const input = field('12.34');
    input.select(0, 5, 'backward');
    const clipboard = text => ({ getData: () => text });
    equal(send(input, 'paste', { clipboardData: clipboard('1x2') }).defaultPrevented, true);
    equal(input.value, '12.34');
    equal(input.selectionStart, 0);
    equal(input.selectionEnd, 5);
    equal(input.selectionDirection, 'backward');
    const exact = '9007199254740993.00000000000000000001';
    equal(send(input, 'paste', { clipboardData: clipboard(exact) }).defaultPrevented, false);
    insert(input, exact, 'insertFromPaste');
    equal(input.value, exact);
    equal(input.writes, 0);
    equal(send(input, 'paste', { clipboardData: clipboard('1\n2') }).defaultPrevented, true);
}

// Missing data/non-cancellable beforeinput, replacement text and autofill.
for (const kind of ['insertText', 'insertReplacementText', 'insertFromPaste', 'insertFromDrop']) {
    const input = field('12.34');
    input.select(1, 4, 'backward');
    const before = send(input, 'beforeinput', { inputType: kind, data: null, cancelable: false });
    equal(before.defaultPrevented, false);
    const rejected = fallback(input, '1x4', kind);
    equal(numeric.shouldIgnoreEvent(rejected), true);
    equal(input.value, '12.34');
    equal(input.selectionStart, 1);
    equal(input.selectionEnd, 4);
    equal(input.selectionDirection, 'backward');
    equal(input.updates.length, 0);
}
{
    const input = field('4');
    fallback(input, '0.00000000000000000001');
    equal(input.value, '0.00000000000000000001');
    equal(input.writes, 0);
    fallback(input, 'garbage');
    equal(input.value, '0.00000000000000000001');
    input.native('bad autofill');
    const change = send(input, 'change');
    equal(numeric.shouldIgnoreEvent(change), true);
    equal(input.value, '0.00000000000000000001');
}

// Native deletion, cut, history and decimal intermediates need no rewriting.
{
    const input = field('12.34');
    for (const [type, result] of [
        ['deleteContentBackward', '12.3'], ['deleteContentForward', '12.'],
        ['deleteByCut', '.'], ['deleteWordBackward', ''],
        ['historyUndo', '.'], ['historyUndo', '12.'], ['historyRedo', '.']
    ]) {
        equal(send(input, 'beforeinput', { inputType: type, data: null }).defaultPrevented, false);
        fallback(input, result, type);
        equal(input.value, result);
    }
    equal(input.writes, 0);
    equal(input.selectionWrites, 0);
    fallback(input, '1x2', 'historyUndo');
    equal(input.value, '.');
}

// Drop position is browser-owned, including moves within the same input.
{
    const input = field('12.34');
    input.select(0, 2);
    send(input, 'dragstart');
    fallback(input, '.34', 'deleteByDrag');
    send(input, 'drop', { dataTransfer: { getData: () => '12' } });
    fallback(input, '.3412', 'insertFromDrop');
    send(input, 'dragend');
    equal(input.value, '.3412');
    equal(input.writes, 0);

    numeric.restoreValue(input, '12.34');
    input.select(2, 3, 'backward');
    send(input, 'dragstart');
    fallback(input, '1234', 'deleteByDrag');
    send(input, 'drop', { dataTransfer: { getData: () => '.' } });
    fallback(input, '12..34', 'insertFromDrop');
    equal(input.value, '12.34');
    equal(input.selectionStart, 2);
    equal(input.selectionEnd, 3);
    equal(input.selectionDirection, 'backward');
    equal(input.updates.at(-1), '12.34');
    send(input, 'dragend');

    equal(send(input, 'drop', { dataTransfer: { getData: () => '$1' } }).defaultPrevented, true);
    equal(input.value, '12.34');
}

// Composition commits once, regardless of final-input/compositionend order.
for (const order of ['input-first', 'end-first', 'no-final-input']) {
    const input = field('12');
    input.select(0, 2);
    send(input, 'compositionstart');
    input.native('候補');
    send(input, 'input', { inputType: 'insertCompositionText', isComposing: true });
    equal(input.value, '候補');
    equal(numeric.isComposing(input), true);
    equal(input.updates.length, 0);
    input.native('34.5');
    if (order === 'input-first') send(input, 'input', { inputType: 'insertCompositionText', isComposing: true });
    send(input, 'compositionend');
    if (order === 'end-first') send(input, 'input', { inputType: 'insertText', isComposing: false });
    flush();
    equal(input.value, '34.5');
    equal(numeric.isComposing(input), false);
    equal(input.updates.length, 1);
    equal(input.writes, 0);
    send(input, 'input', { inputType: 'insertText', isComposing: false });
    equal(input.updates.length, 1);
}
{
    const input = field('12.34');
    input.select(1, 4, 'backward');
    send(input, 'compositionstart');
    input.native('１２');
    send(input, 'input', { isComposing: true });
    send(input, 'compositionend');
    flush();
    equal(input.value, '12.34');
    equal(input.selectionStart, 1);
    equal(input.selectionEnd, 4);
    equal(input.selectionDirection, 'backward');
    equal(input.updates.length, 0);
    equal(numeric.isComposing(input), false);
}

// Registration can occur after an IME composition has already started.
{
    const input = field('4.00');
    input.native('候補');
    send(input, 'input', { isComposing: true });
    equal(numeric.isComposing(input), true);
    send(input, 'compositionend');
    flush();
    equal(input.value, '4.00');
    equal(input.updates.length, 0);
}

// Checked setters reject numbers and invalid text without touching the field.
{
    const input = field('123.4500');
    input.select(2, 4, 'backward');
    const revision = numeric.state(input).revision;
    equal(numeric.setValue(input, '1x2', { notify: true }), false);
    equal(input.value, '123.4500');
    equal(input.writes, 0);
    equal(input.selectionStart, 2);
    equal(numeric.state(input).revision, revision);
    assert.throws(() => numeric.setValue(input, 0.1), /exact strings/); checks++;
    assert.throws(() => numeric.restoreValue(input, 123), /exact strings/); checks++;
    equal(numeric.setValue(input, '123.4500'), true);
    equal(input.writes, 0);
    equal(input.selectionDirection, 'backward');
    numeric.setValue(input, '0.' + '0'.repeat(500) + '1', { notify: true });
    equal(input.updates.length, 1);
    equal(input.value, '0.' + '0'.repeat(500) + '1');
    equal(numeric.state(input).revision, revision + 1);
    numeric.setValue(input, '8');
    equal(input.updates.length, 1);
}

// Preserve all supplied legacy representations, then permit explicit recovery.
for (const original of [' +1,000.0100 ', '1e-400', '000.0100', '1x2', '١٢', '-0.00']) {
    const input = field();
    equal(numeric.restoreValue(input, original), true);
    equal(input.value, original);
    equal(input.updates.length, 0);
    const writes = input.writes;
    send(input, 'focus');
    send(input, 'blur');
    equal(input.value, original);
    equal(input.writes, writes);
    input.select(0, original.length);
    insert(input, '0.012300');
    equal(input.value, '0.012300');
}
{
    const input = field('x1y2');
    fallback(input, '1y2', 'deleteContentForward');
    equal(input.value, '1y2');
    fallback(input, '12', 'deleteContentForward');
    fallback(input, '1y2', 'historyUndo');
    equal(input.value, '1y2');
    fallback(input, 'x1y2', 'historyUndo');
    equal(input.value, 'x1y2');
    equal(input.writes, 0);
    input.select(4);
    equal(insert(input, '3').defaultPrevented, true);
    equal(input.value, 'x1y2');
    fallback(input, '', 'deleteByCut');
    equal(input.value, '');
}

// Even nonnumeric legacy text is preserved verbatim through recovery/history.
{
    const input = field('💵12');
    fallback(input, '12', 'deleteContentForward');
    fallback(input, '💵12', 'historyUndo');
    equal(input.value, '💵12');
    equal(input.writes, 0);
}

// A cancelled or unobserved edit must not leave a stale selection snapshot.
{
    const input = field('12.34');
    input.select(0, 2);
    send(input, 'beforeinput', { inputType: 'insertReplacementText', data: null });
    flush(); // No default edit occurred (another listener/browser cancelled it).
    input.select(3, 5, 'backward');
    fallback(input, '12.x');
    equal(input.value, '12.34');
    equal(input.selectionStart, 3);
    equal(input.selectionEnd, 5);
    equal(input.selectionDirection, 'backward');
}

// Invalid composition with a real final input is rejected, not announced.
{
    const input = field('7.00');
    send(input, 'compositionstart');
    input.native('۷');
    send(input, 'compositionend');
    const rejected = send(input, 'input', { inputType: 'insertText', isComposing: false });
    flush();
    equal(input.value, '7.00');
    equal(numeric.shouldIgnoreEvent(rejected), true);
    equal(input.updates.length, 0);
    send(input, 'compositionstart');
    send(input, 'compositionend');
    flush();
    equal(input.value, '7.00');
    equal(input.updates.length, 0);
}

// Session changes invalidate queued composition/reset callbacks.
{
    const input = field('1');
    const session = numeric.state(input).session;
    send(input, 'compositionstart');
    input.native('候補');
    send(input, 'compositionend');
    numeric.restoreValue(input, '9007199254740993.0000');
    flush();
    equal(input.value, '9007199254740993.0000');
    equal(numeric.isComposing(input), false);
    equal(numeric.state(input).session, session + 1);
    equal(input.updates.length, 0);

    send(input.form, 'reset');
    input.native(''); // Browser reset default action runs after the reset event.
    flush();
    equal(input.value, '');
    fallback(input, 'x');
    equal(input.value, '');
    const beforeCanceledReset = numeric.state(input).session;
    input.form.addEventListener('reset', e => e.preventDefault(), { once: true });
    send(input.form, 'reset');
    flush();
    equal(numeric.state(input).session, beforeCanceledReset);

    send(input.form, 'reset');
    numeric.restoreValue(input, '7.00');
    const restoredSession = numeric.state(input).session;
    flush();
    equal(input.value, '7.00');
    equal(numeric.state(input).session, restoredSession);
}

// A late commit from an active IME must not overwrite a newly populated record.
{
    const input = field('1.00');
    send(input, 'compositionstart');
    input.native('候補');
    send(input, 'input', { isComposing: true });
    numeric.restoreValue(input, '9.00');
    input.native('123');
    send(input, 'input', { inputType: 'insertCompositionText', isComposing: true });
    send(input, 'compositionend');
    input.native('123');
    send(input, 'input', { inputType: 'insertText', isComposing: false });
    flush();
    equal(input.value, '9.00');
    equal(input.updates.length, 0);
    equal(numeric.isComposing(input), false);
    insert(input, '1');
    equal(input.value, '9.001');
}

// No automatic registration, OTP interception, readonly edits or focus changes.
{
    const untouched = new Field('OTP');
    equal(numeric.state(untouched), null);
    untouched.dataset = {};
    assert.throws(() => numeric.register(untouched), /data-numeric/); checks++;
    const input = field('12');
    numeric.register(input);
    insert(input, '3');
    equal(input.updates.length, 1);
    input.readOnly = true;
    equal(send(input, 'beforeinput', { inputType: 'insertText', data: 'x' }).defaultPrevented, false);
    input.readOnly = false;
    input.disabled = true;
    equal(send(input, 'paste', { clipboardData: { getData: () => 'bad' } }).defaultPrevented, false);
    input.disabled = false;
    // A silent third-party assignment is not erased on the next observed edit.
    input.value = '8.00';
    insert(input, 'x');
    equal(input.value, '8.00');
}

flush();
console.log(`${checks} numeric editor assertions passed`);
