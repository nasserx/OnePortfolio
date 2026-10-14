/* Plain-decimal editing, independent of financial validation and submission.
   Registered only for explicitly marked financial fields; OTP is separate.
   All amounts remain strings. Numbers below represent selection offsets only. */
(function (global) {
    'use strict';

    const controllers = new WeakMap();
    const ignoredEvents = new WeakSet();
    const observedDocuments = new WeakSet();

    function inspect(value) {
        const editable = typeof value === 'string' && !/[^0-9.]/.test(value)
            && value.indexOf('.') === value.lastIndexOf('.');
        const complete = editable && /[0-9]/.test(value);
        return { editable, complete, zero: complete && !/[1-9]/.test(value) };
    }

    function candidate(value, start, end, inserted) {
        if (typeof value !== 'string' || typeof inserted !== 'string'
            || !Number.isInteger(start) || !Number.isInteger(end)
            || start < 0 || end < start || end > value.length) return null;
        return value.slice(0, start) + inserted + value.slice(end);
    }

    // Deletion is also allowed while recovering a verbatim legacy/failed-POST
    // value. Never strip characters automatically or reinterpret its meaning.
    function isDeletion(before, after) {
        if (after.length >= before.length) return false;
        let prefix = 0;
        while (prefix < after.length && before[prefix] === after[prefix]) prefix++;
        return before.slice(prefix + before.length - after.length) === after.slice(prefix);
    }

    function isLegacyHistory(original, value) {
        // Recovery edits only remove text. Native undo/redo may revisit those
        // intermediate states without us keeping or replaying an undo stack.
        let index = 0;
        for (let offset = 0; offset < original.length; offset++) {
            if (original[offset] === value[index]) index++;
        }
        return index === value.length;
    }

    function snapshot(field) {
        return {
            value: field.value,
            start: field.selectionStart,
            end: field.selectionEnd,
            direction: field.selectionDirection
        };
    }

    function requireText(value) {
        if (typeof value !== 'string') throw new TypeError('Numeric values must be exact strings.');
    }

    class Editor {
        constructor(field) {
            this.field = field;
            this.session = 0;
            this.revision = 0;
            this.epoch = 0;
            this.notifying = false;
            this.reset();
            const on = (type, listener) => field.addEventListener(type, listener, true);

            on('beforeinput', event => this.beforeInput(event));
            on('input', event => this.input(event));
            on('change', event => this.input(event));
            on('paste', event => this.paste(event));
            on('compositionstart', () => this.startComposition());
            on('compositionend', () => this.endComposition());
            on('dragstart', () => { this.drag = snapshot(field); });
            on('drop', event => this.drop(event));
            on('dragend', () => { this.drag = null; });
            for (const type of ['focus', 'select', 'keyup', 'pointerup']) {
                on(type, () => this.rememberSelection());
            }
            if (field.form) {
                field.form.addEventListener('reset', event => {
                    const epoch = this.epoch;
                    queueMicrotask(() => {
                        if (!event.defaultPrevented && epoch === this.epoch) this.reset();
                    });
                });
            }
        }

        reset() {
            this.epoch++;
            this.session++;
            this.revision++;
            this.current = snapshot(this.field);
            this.restored = this.current.value;
            this.clearTransient();
        }

        clearTransient() {
            if (this.composition) {
                this.discardComposition = {};
                if (this.ending) this.releaseDiscardedComposition();
            }
            this.before = null;
            this.composition = null;
            this.ending = false;
            this.drag = null;
        }

        releaseDiscardedComposition() {
            const discarded = this.discardComposition;
            queueMicrotask(() => {
                if (this.discardComposition === discarded) this.discardComposition = null;
            });
        }

        rememberSelection() {
            if (!this.composition && this.field.value === this.current.value) {
                this.current = snapshot(this.field);
            }
        }

        observeBefore() {
            const before = snapshot(this.field);
            // A silent external .value write cannot be intercepted by DOM
            // input events. Preserve it rather than substituting older data.
            if (before.value !== this.current.value) {
                this.revision++;
                this.restored = before.value;
            }
            this.current = before;
            this.before = before;
            queueMicrotask(() => {
                if (this.before === before) this.before = null;
            });
            return before;
        }

        accepts(value, before, type) {
            if (inspect(value).editable || value === before.value) return true;
            if (type.startsWith('delete') && isDeletion(before.value, value)) return true;
            // Native history can restore the original, explicitly supplied
            // legacy text. It is still subject to final server validation.
            return (type === 'historyUndo' || type === 'historyRedo')
                && !inspect(this.restored).editable && isLegacyHistory(this.restored, value);
        }

        beforeInput(event) {
            if (this.discardComposition) {
                if (event.cancelable) event.preventDefault();
                ignoredEvents.add(event);
                return;
            }
            if (this.field.disabled || this.field.readOnly || this.composition || event.isComposing) return;
            const before = this.observeBefore();
            if (!event.cancelable || event.defaultPrevented) return;
            // Replacement/autocorrect/drop ranges are not reliably exposed for
            // text inputs. History and deletion remain native and use fallback.
            if (!['insertText', 'insertFromPaste'].includes(event.inputType)) return;
            const next = candidate(before.value, before.start, before.end, event.data);
            if (next !== null && !this.accepts(next, before, event.inputType)) {
                event.preventDefault();
                ignoredEvents.add(event);
                this.before = null;
            }
        }

        paste(event) {
            if (this.field.disabled || this.field.readOnly || this.composition
                || this.discardComposition || event.defaultPrevented) return;
            const before = this.observeBefore();
            if (!event.clipboardData || !event.cancelable) return;
            const next = candidate(before.value, before.start, before.end,
                event.clipboardData.getData('text/plain'));
            if (next !== null && !inspect(next).editable) {
                event.preventDefault();
                ignoredEvents.add(event);
                this.before = null;
            }
        }

        drop(event) {
            if (this.field.disabled || this.field.readOnly || this.composition
                || this.discardComposition || event.defaultPrevented) return;
            this.observeBefore();
            // The actual insertion position is browser-owned. Reject clearly
            // foreign characters now; check the full resulting value on input.
            if (event.cancelable && event.dataTransfer
                && /[^0-9.]/.test(event.dataTransfer.getData('text/plain'))) {
                event.preventDefault();
                ignoredEvents.add(event);
                if (this.drag && this.rollback(this.drag)) this.notify();
                this.before = null;
            }
        }

        input(event) {
            if (this.notifying) return;
            if (this.discardComposition) {
                // The browser can finish the old IME transaction after a
                // programmatic record change. Its text belongs to that record.
                ignoredEvents.add(event);
                this.rollback(this.current);
                return;
            }
            if (this.field.disabled || this.field.readOnly) return;
            // Registration can happen after compositionstart. Keep the last
            // observed baseline instead of adopting provisional IME text.
            if (event.isComposing && !this.composition) this.composition = this.before || this.current;
            if (this.composition || event.isComposing) {
                ignoredEvents.add(event);
                // Some engines end composition before emitting the final input.
                if (this.ending && !event.isComposing) this.finishComposition(event);
                return;
            }
            const before = this.before || this.current;
            const type = event.inputType || '';
            if (!this.accepts(this.field.value, before, type)) {
                ignoredEvents.add(event);
                if (this.rollback(type === 'insertFromDrop' && this.drag ? this.drag : before)) this.notify();
            } else {
                this.commit(event);
            }
            this.before = null;
        }

        commit(event) {
            if (this.current.value !== this.field.value) this.revision++;
            else if (event) ignoredEvents.add(event);
            this.current = snapshot(this.field);
        }

        rollback(before) {
            const changed = this.current.value !== before.value;
            if (this.field.value !== before.value) this.field.value = before.value;
            if (before.start !== null && before.end !== null) {
                this.field.setSelectionRange(before.start, before.end, before.direction || 'none');
            }
            this.current = snapshot(this.field);
            if (changed) this.revision++;
            return changed;
        }

        startComposition() {
            if (this.field.disabled || this.field.readOnly) return;
            this.discardComposition = null;
            this.epoch++;
            this.observeBefore();
            this.composition = this.current;
            this.ending = false;
        }

        endComposition() {
            if (this.discardComposition) {
                this.releaseDiscardedComposition();
                return;
            }
            if (!this.composition) return;
            this.ending = true;
            const epoch = this.epoch;
            queueMicrotask(() => {
                if (epoch === this.epoch && this.ending) this.finishComposition();
            });
        }

        finishComposition(event) {
            const before = this.composition;
            if (!before) return;
            this.composition = null;
            this.ending = false;
            this.before = null;
            const changed = this.field.value !== before.value;
            if (!inspect(this.field.value).editable && changed) {
                this.rollback(before);
                if (event) ignoredEvents.add(event);
            } else {
                // Let a real final input through, or emit one if compositionend
                // was the last event. Later duplicate/no-op input is ignored.
                if (event) ignoredEvents.delete(event);
                this.commit(event);
                if (!event && changed) this.notify();
            }
        }

        notify() {
            this.notifying = true;
            try {
                const EventClass = this.field.ownerDocument.defaultView.Event;
                this.field.dispatchEvent(new EventClass('input', { bubbles: true }));
            } finally {
                this.notifying = false;
            }
        }

        assign(value, restore, notify) {
            requireText(value);
            if (!restore && !inspect(value).editable) return false;
            this.epoch++;
            this.clearTransient();
            const changed = value !== this.field.value;
            if (changed) this.field.value = value;
            if (restore) this.reset();
            else this.commit();
            if (notify && changed) this.notify();
            return true;
        }
    }

    function register(field) {
        if (!field || field.tagName !== 'INPUT' || field.type !== 'text'
            || field.dataset.numeric !== 'decimal') {
            throw new TypeError('Register only text inputs marked data-numeric="decimal".');
        }
        if (!controllers.has(field)) {
            controllers.set(field, new Editor(field));
            const doc = field.ownerDocument;
            if (!observedDocuments.has(doc)) {
                doc.addEventListener('selectionchange', () => {
                    controllers.get(doc.activeElement)?.rememberSelection();
                });
                observedDocuments.add(doc);
            }
        }
        return controllers.get(field);
    }

    global.OnePortfolioNumeric = Object.freeze({
        // Submission compatibility is broader than the interactive editor.
        // Classify legacy/server syntax without converting or rewriting it.
        classify(value) {
            const text = String(value ?? '').trim();
            const match = /^([+-]?)(?:(\d+(?:\.\d*)?|\.\d+)|(\d{1,3}(?:,\d{3})+(?:\.\d*)?))(?:[eE][+-]?\d+)?$/.exec(text);
            const zero = Boolean(match && !/[1-9]/.test(match[2] || match[3]));
            return { empty: !text, complete: Boolean(match), zero,
                negative: Boolean(match && match[1] === '-' && !zero) };
        },
        inspect,
        candidate,
        register(field) { register(field); },
        setValue(field, value, { notify = false } = {}) { return register(field).assign(value, false, notify); },
        restoreValue(field, value) { return register(field).assign(value, true, false); },
        reset(field) { register(field).reset(); },
        isComposing(field) {
            const editor = controllers.get(field);
            return Boolean(editor && (editor.composition || editor.discardComposition));
        },
        shouldIgnoreEvent(event) { return ignoredEvents.has(event); },
        state(field) {
            const editor = controllers.get(field);
            return editor ? Object.freeze({ session: editor.session, revision: editor.revision }) : null;
        }
    });
}(window));
