# Numeric input system

## Current status

The editor in `portfolio_app/static/js/numeric_inputs.js` is loaded before
feedback and registered for all 12 financial inputs. The previous sanitizer,
focus-select-all, exponential expansion and floating-point preview are removed.
Server validation, financial calculations, persistence, OTP and overlay focus
ownership remain unchanged. Phase B, including preview visual acceptance, is
approved. Phase C verifies the combined system and fixes native reset ordering;
final approval and remaining native-browser acceptance belong to the user.

| Page | Registered inputs |
|---|---|
| Assets | `price`, `quantity`, `fees`, `edit_price`, `edit_quantity`, `edit_fees`, `add_div_amount`, `edit_amount` |
| Portfolios | `add_funds_amount`, `withdraw_funds_amount`, `edit_cash_event_amount`, `transfer_amount` |

The user approved plain decimal interactive entry. Existing server/API numeric
syntax remains broader and will not be narrowed. The editor constrains syntax;
it does not validate financial amounts or approve transactions.

## Editing contract

- ASCII digits and at most one decimal point; no sign, grouping, exponent,
  whitespace, localized-digit conversion or automatic cleanup.
- Empty text, `.` and trailing decimal points are valid editing states. A
  complete number needs a digit. Zero is syntactically valid; requiredness,
  positivity, optional fees and account rules belong to final validation.
- Amounts remain strings. There is no rounding, scale cap or numeric conversion.
  Integer checks in candidate construction apply only to selection offsets.
- Cancellable `beforeinput` and paste events reject an invalid complete
  candidate. Accepted edits are left to the browser, including native deletion,
  history, focus, scrolling and keyboard shortcuts.
- Replacement/drop ranges, autofill and events with missing data use an `input`
  fallback; `change` also checks a value when no input event was observed. An
  invalid edit restores its whole preceding value and selection, not a cleaned
  substring. Same-field drag moves retain a pre-drag snapshot for rollback.
- IME provisional text is left alone. The final value is accepted or the
  pre-composition snapshot restored after composition ends. Consumers ignore
  provisional events; final commits are delivered once through an input update.
- Verbatim initial/restored values are never normalized on focus or blur.
  Recovery permits explicit deletions or replacement with valid decimal text.
  Native history may revisit original legacy text and its deletion-only recovery
  states, without a custom undo stack.

## API and integration

`window.OnePortfolioNumeric` exposes:

| Method | Contract |
|---|---|
| `inspect(text)` | Returns `editable`, `complete` and `zero`; never coerces a number into text |
| `classify(text)` | Submission-only string classification: `empty`, `complete`, `zero`, `negative`; accepts existing server grammar including legacy signs/grouping/exponents without rewriting or expanding text |
| `candidate(text, start, end, inserted)` | Exact selection replacement, or `null` when the range/data is unknown |
| `register(field)` | Idempotently registers only a text input explicitly marked `data-numeric="decimal"` |
| `setValue(field, text, {notify: false})` | Accepts an editable string; returns false for rejected syntax without changing the field; nonstrings throw |
| `restoreValue(field, text)` | Preserves supplied text exactly and starts a new field session; emits no input/validation notification |
| `reset(field)` | Rebases the current value/selection and invalidates deferred composition state without altering field contents |
| `isComposing(field)` | Includes the ending interval and discarded old-record composition until its end is processed |
| `shouldIgnoreEvent(event)` | Identifies provisional, rejected and duplicate/no-op input events |
| `state(field)` | Immutable session/revision snapshot, or null for an unregistered field |

An explicit `notify: true` assignment emits one input event if the value changes.
Unchanged assignments preserve selection and emit nothing. Native form resets
rebase state after the default action, unless cancelled or superseded by a new
record. Shared feedback also waits for that default action, so it cannot cancel
the editor's reset while the previous amount is still in the field. Explicit
dialog preparation/close continues to reset feedback synchronously.
Late input from an active composition discarded during population is
ignored through its compositionend turn, preserving the new record's value.
Registration neither queries the page nor attaches to OTP fields.

Prefills, record changes and failed-POST restoration use `restoreValue`; Max
uses `setValue` with notification to update post-submit correction and previews.
Feedback checks both `isComposing(field)` and `shouldIgnoreEvent(event)` after
target listeners run. Previews read settled values even after rejected/no-op
edits, and show a placeholder during composition. Submission during active
composition waits for a subsequent final submit without publishing field errors.
The module owns no error messages,
invalid attributes, form submission, HTTP requests or focus management.

Silent external `.value = ...` writes do not emit DOM input events. Application
writers must use the API. If an external value is first observed at the next
beforeinput event, it is preserved as the current baseline rather than replaced
with older data. Final validation must always inspect the actual submitted text.

## Exact advisory previews

`transaction_previews.js` owns both existing Buy/Sell preview regions. A label
and neutral `—` placeholder exist in the HTML and remain present during resets,
incomplete entry and composition. Complete values update in a microtask after
the numeric editor settles the input, without timers or per-edit HTTP requests.
Rejected/no-op edits retain the settled value's result instead of blanking it.

The local calculation uses signed BigInt coefficients and decimal exponents.
Multiplication and fee addition/subtraction are exact; only display rounds to
two decimals using Python's existing `ROUND_HALF_UP` convention. Thousands
separators, negative totals and negative rounded zero match `fmt_money`. Neither
`Number` nor `parseFloat` converts financial operands. This deliberately mirrors
only the small arithmetic presentation operation, with executable Python/JS
parity tests; no financial acceptance, history or cash rules are duplicated.

Blank creation fees mean zero. For editing, one authenticated, CSRF-protected
`POST /transactions/preview` with mode `retained` reads current fees from the
owned transaction when the dialog opens or changes record. The response never
overwrites inputs and refreshes using the latest values. Blank edit fees use
that stored amount; explicit zero replaces it. Blank price/quantity remain
incomplete in the UI. Final partial-edit semantics and requiredness are unchanged.

The lookup is aborted on close/reset or record replacement; revision, record
action and abort-state guards reject late responses. A lookup failure affects
only previews that need unknown stored fees: they display `Stored fees
unavailable`, never an assumed zero. Explicit-fee calculations remain usable
offline. Reopening retries the lookup. Once loaded, retained fees are a snapshot
for that dialog session; final server submission still checks current records
and mutation revisions. No preview result approves a financial operation.

The endpoint's existing create/edit calculation modes are retained for
compatibility and use `transaction_cash_effect` plus `fmt_money`. Preview-only
positivity checks and the negative-result rejection were removed. Syntax and
resource budgets remain enforced; final transaction validation is unchanged.

Only this read-only POST is excluded from the financial mutation wrapper. It
does not take a writer reservation, consume an intent, advance a revision or
create a receipt. Tests compare all database tables before and after previews.

Preview-only resource budgets: 4096 characters per operand and 8192 decimal
positions for expansion/product/fee alignment, on both sides. The HTTP endpoint
retains its 16 KiB body limit and 120 requests/minute per authenticated identity;
typing no longer consumes that allowance. Values outside preview work budgets
remain editable with existing submission/storage contracts and show `—`.

## Verification boundaries

Run `node tests/numeric_inputs.js`; CI also discovers it through `tests/*.js`.
`tests/transaction_previews.js` covers immediate updates, persistent placeholders,
signed results, aborts, stale fee responses, verbatim values, composition, record
switches and failures. Shared feedback and
precision scripts execute the numeric module alongside production consumers.
`tests/test_transaction_previews.py` covers exact arithmetic, stored-fee
semantics, database non-mutation, ownership, CSRF and request budgets, plus
330 production BigInt results compared directly with Python exact arithmetic
and formatting. This parity test requires Node (also configured in Python CI).
The tests model input events, selection, native edits and deferred composition/
reset ordering; they execute the production module. They do not run a browser
or demonstrate native undo-stack, autofill, IME or mobile-keyboard behavior.

The implementation deliberately avoids rewriting valid native edits. Fallback
rollback necessarily writes the value and may interact with native undo history;
that behavior, cross-field drag moves, actual composition ordering, and platform
selection handling need user acceptance on desktop Chrome/Edge, Firefox, Safari,
iOS Safari and Android Chrome before production integration is accepted.

Source guidance: [Input Events](https://w3c.github.io/input-events/) and
[beforeinput behavior](https://developer.mozilla.org/en-US/docs/Web/API/Element/beforeinput_event).
The official preset initialization and Nova Input/Field JSON recipes were
re-inspected over HTTP on 2026-10-14. Existing input styling, required metadata,
error associations and preview semantic classes are retained in the current
Jinja/JavaScript architecture; no visual redesign or new UI framework.

## Initial Phase B implementation record (before UX correction)

Verification on 2026-10-13:

- 459 focused Python tests passed across preview integration, precision, exact
  storage/arithmetic, cash-account policy, mutation integrity, authentication,
  form feedback/error classification and affected component contracts.
- The 33 preview tests passed again after the final database-ID boundary check.
- All eight JavaScript scripts passed: 667 assertions in total.
- Syntax checks passed for all 18 application/test JavaScript files.
- No Git commands or browser verification. The complete Python-suite run and
  remaining Phase C acceptance work have not begun.

Files changed in Phase B (paths relative to repository root):

| Area | Files |
|---|---|
| Backend | `portfolio_app/__init__.py`, `portfolio_app/routes/transactions.py`, `portfolio_app/services/transaction_service.py`, `portfolio_app/services/transaction_preview.py` (new), `portfolio_app/utils/mutation_requests.py` |
| JavaScript | `portfolio_app/static/js/numeric_inputs.js`, `portfolio_app/static/js/main.js`, `portfolio_app/static/js/form_feedback.js`, `portfolio_app/static/js/portfolio_transfers.js`, `portfolio_app/static/js/transaction_previews.js` (new) |
| Templates | `portfolio_app/templates/base.html`, `portfolio_app/templates/assets.html`, `portfolio_app/templates/portfolios.html`, `portfolio_app/templates/partials/transfer_modals.html` |
| Python tests | `tests/test_transaction_previews.py` (new), `tests/test_assets_final_contracts.py`, `tests/test_portfolios_final_contracts.py`, `tests/test_final_polish_contracts.py` |
| JavaScript tests | `tests/transaction_previews.js` (new), `tests/precision_boundaries.js`, `tests/modal_form_errors.js`, `tests/portfolio_transfers.js`, `tests/cash_account_max.js` |
| Documentation | `docs/NUMERIC_INPUTS.md`, `docs/DEVELOPMENT.md` |

## Phase B preview UX correction — 2026-10-14

Root causes verified in the replaced implementation:

- Trailing 250 ms debounce plus an HTTP round trip on each settled edit.
- An explicit negative-total rejection in the server preview renderer, coupled
  with transaction positivity validation in an arithmetic-only preview.
- Empty initial markup and destructive resets that cleared all preview content.
  A duplicate/rejected event could clear content and cancel work without a refresh.
- A generic error path combined negative-result rejection, network/HTTP failures,
  invalid JSON and rate limiting. The 120/minute limit was shared by per-edit
  requests; the particular network response from user testing was not recorded.

Corrections: immediate BigInt arithmetic; persistent labeled placeholders;
signed results and existing financial rounding; one protected stored-fee lookup
per edit session/record; no per-keystroke requests. Final business validation,
numeric editing, OTP, form-feedback timing and persistence were not changed.

Verification:

- 464 focused Python tests passed (financial precision/storage/arithmetic,
  cash policy, mutation integrity, authentication/security, form feedback and UI).
- 45 preview/component tests passed again after final refinements, including
  330 direct production-JavaScript/Python Decimal parity comparisons.
- All eight JavaScript scripts passed: 674 assertions. Syntax checks passed for
  all 18 application/test scripts. CI now explicitly configures its existing
  Node 22 toolchain for the Python parity test as well.
- Official preset Input/Field recipes inspected over HTTP; existing classes,
  semantic colors, dimensions, typography and live region retained. No CSS,
  framework or dependency changes. No browser visual verification or Git use.

Correction files: `portfolio_app/static/js/transaction_previews.js`,
`portfolio_app/services/transaction_preview.py`,
`portfolio_app/services/transaction_service.py`,
`portfolio_app/templates/assets.html`, `portfolio_app/__init__.py`,
`tests/transaction_previews.js`, `tests/test_transaction_previews.py`,
`tests/test_final_polish_contracts.py`, `.github/workflows/ci.yml`,
`docs/DEVELOPMENT.md`, and this document.

Remaining acceptance: real browser/native editing and visual review belong to
the user. A failed stored-fee lookup cannot safely calculate a blank-fee edit;
reopening retries it. Preview resource budgets do not limit editing or final
financial precision. Phase C and the complete Python suite were deferred at
the conclusion of Phase B; see the final verification record below.

## Phase C final verification — 2026-10-14

The audit found one production integration bug: with the production registration
order (numeric editor before feedback), synchronous feedback handling of native
`reset` invalidated the editor's deferred reset before the browser applied default
values. A subsequent invalid edit could restore the previous amount. Feedback
now rebases after the default action, respects cancellation, and ignores an old
reset if another record has been prepared. The regression failed before this
fix and passes afterward. Asset version: `20261014-numeric-c`.

The initial complete Python run reported 1123 passes and four failures, all
superseded source assumptions: floating-point preview code in `main.js`, empty
preview markup, the old location of terminology, and direct Withdrawal Max
assignment. Those contracts now target the current preview module and initial
accessible placeholder markup. Arithmetic remains covered by executable parity
tests, and Max behavior by its existing JavaScript script. No obsolete numeric
production handler or duplicate arithmetic listener remained to remove.

Additional regressions verify verbatim final transport (including silent external
writes, legacy syntax, values beyond preview budgets, blank fees and nonnumeric
notes), rejection of malformed final values, retained-fee response failures, and
late failures after close. A real route/persistence test checks blank creation
fees as zero and blank editing fees as retained, with exact high-precision cash
effects and no reliance on a submitted preview amount. Rendered authentication
and account-deletion codes remain outside decimal registration.

### Coverage reconciliation

| Contract | Automated evidence | Remaining acceptance |
|---|---|---|
| All 12 financial fields | Rendered Assets/Portfolios inventory; explicit registration; inspected all prefills, failed-POST writers and Max actions | Exercise every dialog in the browser |
| Plain decimal editing, arbitrary supported precision | `numeric_inputs.js`: candidate validation, paste, cut/delete, selection, history, drop, IME event orders, autofill/change fallback, programmatic assignments | Native undo stacks, caret/selection and platform event delivery |
| Final entered values and legacy compatibility | `modal_form_errors.js`, `precision_boundaries.js`, Python parser/forms and persistence tests | Autofill/extensions that silently assign values require a subsequent event to refresh previews; submission still reads actual values |
| Immediate exact previews and fee semantics | `transaction_previews.js`; 330 direct BigInt/Python Decimal comparisons; final route fee persistence | Retained fees are a dialog-session snapshot; the server rechecks current financial state |
| Placeholder, signs, rounding and stale work | Initial markup; positive/zero/negative and negative rounded zero; rapid edits; close/reset/record switching; aborted/late/malformed fee responses | User confirms live announcements and native interaction timing |
| Validation, focus and accessibility | Shared feedback/overlay tests: submit gating, correction, server-only errors, associations, composition and reset; Bootstrap focus ownership retained | Screen-reader and keyboard experience |
| Security and financial integrity | Ownership/authentication, CSRF, per-user limits, request bounds, all-table read-only snapshots; mutation, precision/storage, replay and cash-policy suites | No new exception to server validation or mutation protections |
| OTP and other fields | Existing OTP filtering/auto-submit behavior; rendered code-field isolation; deletion security workflow; nonnumeric transport | Email-code autofill and manual account-deletion submission |

Phase C changes are limited to `portfolio_app/static/js/form_feedback.js`,
`portfolio_app/__init__.py`, `tests/modal_form_errors.js`,
`tests/transaction_previews.js`, `tests/test_transaction_previews.py`,
`tests/test_financial_record_semantics.py`, `tests/test_portfolios_funding_entries.py`,
`tests/test_auth.py`, and this document. No styles, financial arithmetic, database
schema, dependencies, routes or authorization rules changed.

### Executed verification

- Complete Python suite: **1128 passed** in 159.45 seconds, using
  `python -m pytest -q --tb=short` in the project environment.
- Focused preview, financial terminology/funding, precision and feedback/error
  suite: **169 passed**. After adding final-submission and rendered code-isolation
  checks, the preview module plus two authentication regressions: **41 passed**.
  These overlap the complete suite; they are not additional unique test counts.
- Exact parity: **330** production JavaScript BigInt results matched authoritative
  Python Decimal amounts and financial formatting (included in Python runs).
- All eight JavaScript scripts: **734 assertions passed** — cash Max 10,
  form lifecycle/transport 151, numeric editor 258, overlays 110, chart ranges 36,
  transfers 29, precision boundaries 63, exact previews 77.
- `node --check`: **18 scripts passed**, covering all production and test `.js`
  files. Tests used local Python 3.13 and Node 24.18.0; CI's Python matrix and
  Node 22 configuration were inspected, not executed locally.
- No browser or Git commands were executed. The approved component styling and
  previously inspected official Input/Field recipes required no visual changes.

### Manual browser acceptance checklist

Use disposable test data. The following remains user-owned; automated event
models are not native browser or visual verification.

- Exercise the eight Assets and four Portfolios fields listed above, including
  new/edit dialogs and switching records. Verify prefills keep all digits.
- Type `.`, `0.`, fractions and long decimals; paste valid/invalid text over a
  selection; cut, backspace/delete, drag/drop, undo and redo. Verify valid edits
  keep natural caret/selection/history behavior and invalid edits are atomic.
- Check desktop Chrome/Edge, Firefox and Safari, plus iOS Safari/Android Chrome
  where supported: decimal keyboards, IME commit/cancel and native autofill.
  Pay particular attention to undo after fallback rollback and cross-field drag.
- Check visible initial placeholders, immediate Buy/Sell changes, Sell
  `1 × 1 − 3 = −2.00`, zero, rounding ties and long fractional values. For editing,
  clear fees to retain them; enter explicit zero to replace them. Close/reopen
  and switch records while a stored-fee request is pending.
- Simulate offline/failed retained-fee lookup: unknown blank fees must not become
  zero; explicit fees must still calculate locally. Reopening retries the lookup.
- Verify no blur-time errors, correction after failed submit, persistent financial
  errors, reset/close behavior, focus containment and meaningful screen-reader
  announcements. Check both themes without expecting a styling change.
- Verify login/email OTP autofill and auto-submit, manual account-deletion code
  submission, and normal editing of names, symbols and notes.

Preview-only work budgets still yield a placeholder rather than a guessed value.
Fallback rollback can affect native undo history, and browser/platform behavior
cannot be certified by these event-model tests. Phase C introduces no browser
automation or visual acceptance claim and performs no Git operations.
