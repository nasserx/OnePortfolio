# UI alignment coverage and ownership register

## Status and execution boundaries

Phases 1–4 approved, including user visual acceptance of the final compact
typography and large Book Value exception. Phase 5 final verification and cleanup
on **2026-10-13** is recorded below; final user approval is pending.
The reference source inspection began on **2026-10-10**. Recipe links and
semantic contracts are in [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md).

| Phase | Deliverable | Status |
|---|---|---|
| 1 | Reference contracts, coverage, ownership, and test baseline | Approved |
| 2 | Submit-gated validation and accessible shared feedback | Approved; user visual acceptance complete |
| 3 | Shared component recipes and preset chart palette | Approved; user visual acceptance complete |
| 4 | Page integration, interaction corrections and final typography | Approved; user visual acceptance complete |
| 5 | Broader regression verification and acceptance handoff | Implemented; final approval pending |

After each phase, report changed components, actual checks, and material risks;
pause for user review before proceeding. The user owns all Git operations and
visual acceptance. Do not execute Git commands or perform browser-based visual
verification. Historical phase reports below retain their original results and
limitations; the current matrix and ownership register supersede baseline gaps.

Preserve calculations, numeric formatting, approved financial colours, user
isolation, persistence, routes, form/API contracts, CSRF, and mutation tokens.
Retain Flask/Jinja, Bootstrap, Flatpickr, and Chart.js. No dependencies or schema
changes are planned. Financial/brand exceptions remain. The earlier custom
chart palette was superseded by Phase 3; compact font sizes and the original
large Book Value are explicit, approved Phase 4 typography exceptions.
Field errors become visible after final submit and then update
while correcting. Six-digit verification-code auto-submit remains an exception.

## Page and component coverage

All entries below are **implemented and covered by source/rendered-response or
DOM-model checks**; Phases 2–4 received user visual acceptance. Paths are relative
to `portfolio_app/`. Evidence names refer to files in `tests/`. These checks do
not run a browser, real Bootstrap focus traps, or assistive technology.

| Surface / source | Components and reference families | Verified contracts / evidence |
|---|---|---|
| App shell: `templates/base.html`, `static/js/shell.js`, `static/js/overlays.js` | Sidebar, Dropdown Menu, Button, Command, notifications, brand/icons | Overlay exclusion, drawer breakpoint/Tab/return, command active descendant/disabled options, theme contracts: `overlay_contracts.js`, `test_phase4_page_contracts.py`, `test_preset_foundation.py` |
| Public Landing: `templates/landing.html`, `static/css/landing.css`, `static/js/landing.js` | Header controls, Card, Item, Button, chart/legend, brand/icons | Shared typography/theme/brand, layout and reduced-motion source contracts, preview formatting: `test_landing_final_contracts.py`, `test_landing.py`, `overview_chart_ranges.js` |
| Overview: `templates/index.html`, `static/js/overview_charts.js` | Card, metrics, Tooltip, Tabs, chart/legend, Table, Empty | Large Book Value/formatting, empty/undefined returns, chart palette/range/responsive text, ledger semantics: `test_overview_final_contracts.py`, `test_overview_transfer_ui.py`, `test_phase4_page_contracts.py`, `overview_chart_ranges.js` |
| Portfolios: `templates/portfolios.html` | Disclosure, Table, Dropdown Menu, Pagination, Empty | Shared records/paging/menu recipes, financial signs and transfer prefilling: `test_portfolios_final_contracts.py`, `test_action_menus.py`, `portfolio_transfers.js` |
| Assets: `templates/assets.html` | Search/Input, filter Menu, Badge, disclosure, Table, Pagination, Empty | Filter and empty-result contracts, records and single submit ownership: `test_assets_final_contracts.py`, `test_edit_dividend_single_submit.py`, `test_financial_record_semantics.py` |
| All 17 financial dialogs: two templates and `templates/partials/transfer_modals.html` | Dialog, Alert, Field, Input, Select, Textarea, Calendar, Button | Error placement/associations, required/CSRF/mutation metadata, classification, reset/stale responses, disabled/readonly states, programmatic return and calendar containment: `test_form_feedback.py`, `test_error_classification.py`, `test_modal_accessible_names.py`, `modal_form_errors.js`, `overlay_contracts.js` |
| Settings: `templates/auth/settings.html` | Tabs, Card, static values, Button, Alert | Responsive cascade/orientation, definition-list values, deletion code/error classification: `test_phase4_page_contracts.py`, `test_settings_auth_final_presentation.py`, `test_auth.py`, `test_error_classification.py` |
| Login/reauthentication: `templates/auth/login.html`, `templates/auth/reauthenticate.html` | Auth Card, Field/Input, Button, Alert | Shared feedback, failed POST retention, required semantics, server authentication: `test_form_feedback.py`, `test_settings_auth_final_presentation.py`, `test_auth.py` |
| Verification: `templates/auth/verify_code.html` | Field/Input, Alert, Button | Six-digit auto-submit retained, invalid/expired/challenge/general failures and resend protections: `test_form_feedback.py`, `test_error_classification.py`, `test_auth.py` |
| Email update: `templates/auth/update_email.html` | Card, Field/Input, Button, Alert | Shared size/feedback, retained email and verification/security workflow: `test_settings_auth_final_presentation.py`, `test_error_classification.py`, `test_auth.py` |
| Rate limit: `templates/errors/rate_limit.html` | Auth Card, text, Button, brand | Shared shell/typography and rate-limit response contract: source inspection, `test_rate_limit_storage_config.py`, `test_auth.py`; actual wrapping not browser-tested |
| Shared shells/macros: `templates/auth_base.html`, `templates/macros/`, `templates/components/` | Numbers, Empty, icons, logo/favicon | Exact weights/compact sizes, financial precision, semantic colours, named/decorative icons and preserved brand: `test_phase3_component_contracts.py`, `test_phase4_page_contracts.py`, `test_formatting.py`, `test_design_tokens_contrast.py`, `test_geist_tabler_contracts.py`, `test_brand_lockup.py`, `test_brand_assets.py` |

Global coverage for every applicable row: light, dark, system theme, narrow and
wide layouts, keyboard/focus, hover/active/expanded, disabled/readonly, reduced
motion, forced colours, long content, and empty/loading/error states. These are
acceptance scenarios. Source guards cover applicable CSS rules and themes, while
DOM-model tests cover application handlers. Real viewport wrapping, vendor
integration, screen-reader announcements and touch ergonomics were not exercised
by the agent; no new browser acceptance is claimed beyond the user's approval.

### Financial dialog inventory

Every dialog is registered with `ModalAjaxHandler` in `static/js/main.js`.
All use Bootstrap Modal; form values/opening are populated by page code or the
transfer module. Final rendered tests cover each identifier, not just one example.

| Template | Dialog IDs |
|---|---|
| `templates/portfolios.html` | `newPortfolioModal`, `renamePortfolioModal`, `depositFundsModal`, `withdrawFundsModal`, `editPortfolioEventModal`, `deletePortfolioEventModal`, `deletePortfolioModal` |
| `templates/assets.html` | `addSymbolModal`, `deleteSymbolModal`, `addTransactionModal`, `editTransactionModal`, `deleteTransactionModal`, `addDividendModal`, `editDividendModal`, `deleteDividendModal` |
| `templates/partials/transfer_modals.html` | `transferModal`, `deleteTransferModal` |

## Verified interaction ownership

The application loads Bootstrap **5.3.0**, verified in both shell templates.
The pinned upstream [Modal source](https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/js/src/modal.js),
[FocusTrap source](https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/js/src/util/focustrap.js),
and [Dropdown source](https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/js/src/dropdown.js)
were read over HTTP. Findings below distinguish code ownership from runtime
verification; no browser was used.

| Concern | Current owner and evidence | Constraint for subsequent work |
|---|---|---|
| Financial dialog containment/dismissal | Bootstrap Modal creates and activates FocusTrap, handles Escape/backdrop, deactivates on hide | Keep Bootstrap as sole trap; error focus happens within its lifecycle |
| Return to dialog opener | Bootstrap data-API restores declarative triggers; `OnePortfolioDialogs.show` adds a one-shot return path for programmatic callers | Restore the menu trigger for menu actions; skip unavailable openers; no duplicate trap or data-API callback |
| Menu opening/positioning | Bootstrap Dropdown/Popper; `ActionMenuManager` applies fixed strategy and viewport boundary to entity menus | Retain positioning owner; any added menu behavior must cooperate with it |
| Menu keyboard behavior | Bootstrap owns arrows, Escape and Tab dismissal; `ActionMenuManager` supplements Enter/Space entry, Home/End and typeahead | Association and enabled-item checks retained; repeated mounting is guarded |
| Command palette | `CommandPalette` owns combobox/listbox selection; `OnePortfolioOverlays` owns shared containment, inertness, Escape and focus return | One custom overlay slot; no custom containment while Bootstrap modal is active |
| Mobile navigation | `SideNav` supplies entry/expanded semantics and 62rem transitions; shared overlay coordinator owns containment/return/scroll state | No Bootstrap Offcanvas or second focus handler; transition releases custom ownership |
| Date picker | Flatpickr owns dates; `initDateField` mounts calendars inside their owning modal, otherwise in `document.body` | Bootstrap remains sole modal trap; picker Escape closes picker first; form scrolling and modal dismissal close it |
| Tooltips | Bootstrap Tooltip, initialized only through `TooltipManager.getOrCreateInstance` | Preserve hover/focus and avoid duplicate instances |
| Field validation and feedback | `form_feedback.js` singleton per form; existing rules registered by `FormValidatorsInitializer` in `main.js`; matching Jinja macros | Submit-gated feedback, required metadata, stable error/help associations, one validation owner |
| Financial submission/loading | `ModalAjaxHandler` alone owns POST transport; shared feedback controller owns reset and errors | No page-specific submission listeners; preserve failed POST reopening; pending/session guards prevent duplicate submissions and stale failures |
| Account forms | Shared `form_feedback.js`, server POST/render workflows, six-digit `requestSubmit()` in `verify_code.html`; auth shell does not load `main.js` | Shared feedback without financial controllers or authentication policy changes |
| Notifications | Server-rendered flash markup, `AlertManager`, and `shell.js` toast rendering | Keep ordinary statuses separate from financial colours; preserve accessible messages and dismissal |

Calendar containment and programmatic restoration gaps were resolved in Phase 4.
Application-side ownership and lifecycle behavior are covered by source and
DOM-model tests; actual Bootstrap/Flatpickr browser integration remains distinct
from those tests and was visually accepted by the user as part of Phase 4.

## Known gaps and scheduled corrections

The first five findings below are the Phase 1 baseline, resolved in Phase 2.
Shared recipe findings were resolved in Phase 3; page/overlay findings were
resolved in Phase 4. Phase 5 reconciles documentation and coverage. Source
evidence in this table describes the original baseline, not current defects.

| Phase 1 source evidence | Correction phase |
|---|---|
| `FormValidator.shouldShowError` uses `touched`; blur/change mark fields touched | 2: final-submit gate, then correction feedback |
| Modal clearing removes markup but does not reset validator submission/touched state | 2: shared session reset; preserve failed server-rendered state |
| Error setters lack field associations; `NativeValidationDisabler` removes required attributes | 2: accessible shared feedback and required semantics |
| AJAX banner and server-rendered `.alert-danger` differ; Withdraw Max calls `reportValidity()` | 2: shared top-of-body general errors and auxiliary action feedback |
| Transaction type changes instantiate extra validators to clear an error | 2: reuse the form's existing feedback owner |
| `--text-sm` is 13px; table headers are 11px; help text is 10px | 3: map typography by actual recipe role |
| Overview ledger headers are muted while native table headers use foreground | 3/4: consistent Table semantic role, preserving muted descriptive labels |
| Invalid fields use custom tinted fills; input/disabled/select recipes are conflated | 3: separate component state recipes |
| Settings static displays imitate differently styled readonly fields | 3/4: explicit static label/value presentation |
| Three-dot triggers use 28px/26px sizes, inherited icon dimensions, and generic active translation | 3/4: Button/Menu recipes and existing positioning owner |
| Dialog headers/footers, alerts, empty states, and CSS-mask close icons differ from inspected recipes | 3: shared recipe corrections; adapt to current technology |
| Allocation uses `--portfolio-chart-*`; command input uses a custom flat recipe | 3: preset palette and Command/Input Group presentation |
| Narrow `.settings-sidebar` grid rule is overridden by a later flex rule | 4: cascade correction |
| Palette/drawer focus and selection contracts have gaps described above | 4: complete through verified ownership |
| Existing CSS-string tests encode some superseded local choices | 3-5: revise against source-backed targets without weakening unrelated guards |

## Phase 1 baseline verification

Executed during Phase 1, before documentation completion. Tests use the
project virtual environment and disposable test databases; no application
server or browser was started.

**Python: 169 passed (4.32 seconds).** Exact selection:

```powershell
.\venv\Scripts\python.exe -m pytest -q tests/test_preset_foundation.py tests/test_nova_component_fidelity.py tests/test_shared_surface_contracts.py tests/test_design_tokens_contrast.py tests/test_geist_tabler_contracts.py tests/test_action_menus.py tests/test_modal_accessible_names.py tests/test_edit_dividend_single_submit.py tests/test_landing_final_contracts.py tests/test_overview_final_contracts.py tests/test_portfolios_final_contracts.py tests/test_assets_final_contracts.py tests/test_settings_auth_final_presentation.py tests/test_formatting.py
```

**Node: all five existing assertion scripts passed (78 reported assertions).**

| Command | Reported assertions passed |
|---|---:|
| `node tests/precision_boundaries.js` | 18 |
| `node tests/cash_account_max.js` | 9 |
| `node tests/portfolio_transfers.js` | 29 |
| `node tests/modal_form_errors.js` | 10 |
| `node tests/overview_chart_ranges.js` | 12 |

These checks establish existing regression baselines. They do not demonstrate
the new submit-only timing, correct actual overlay focus, complete accessibility,
or rendered preset fidelity. The full Python suite was not run in this
documentation-only phase. Later phases add focused behavioral regressions and
run broader relevant checks before acceptance handoff.

## Phase 1 review checkpoint

- Changed components: none at runtime; updated the design-system contracts and
  added this coverage/ownership register.
- Source coverage: all page families, shared components, and 17 registered
  financial dialogs; official recipes and pinned Bootstrap ownership inspected.
- Risk: live upstream recipes can change; recheck them before each material
  component change and record intentional adaptations. Known implementation
  gaps remain scheduled, not silently treated as compliant.
- No Git commands or browser-based visual verification were performed.
- Phase 1 was subsequently approved; Phase 2 proceeded under the user's explicit instruction.

## Phase 2 implementation and review checkpoint

Shared feedback now gates field errors on final submit, revalidates during
correction, preserves required semantics, and links messages to their controls.
Initial failed POSTs retain values and errors; dialogs reset on close, fresh
open, and record replacement. General errors have one persistent summary at the
top of each of the 17 financial dialog bodies. Hidden/unknown errors remain
visible in that summary. Buy/Sell errors associate with the visible buttons.
Max failures use the summary without marking untouched fields invalid.

Bootstrap remains the only modal focus trap. Shared feedback focuses the first
actionable invalid field, or the summary, after initial `shown` or failed submit.
The removed `ModalManager`, native-required stripping, page error clearing, and
extra transaction-type validator no longer compete with the controller. AJAX
transport remains exclusively in `ModalAjaxHandler`; OTP auto-submit is retained.
Dividend failed-POST dialogs now reopen; submitted dividend and funding-entry
values are restored without changing financial precision or server validation.

Changed runtime files (relative to `portfolio_app/`):

- `static/js/form_feedback.js` (new), `static/js/main.js`,
  `static/js/portfolio_transfers.js`.
- `templates/macros/forms.html` (new), `templates/base.html`,
  `templates/auth_base.html`, `templates/assets.html`, `templates/portfolios.html`,
  `templates/partials/transfer_modals.html`.
- `templates/auth/login.html`, `templates/auth/verify_code.html`,
  `templates/auth/update_email.html`, `templates/auth/settings.html`.
- `__init__.py`: asset-version bump only, so cached scripts migrate together.

Changed verification/docs files:

- `tests/test_form_feedback.py` (new), `tests/modal_form_errors.js`,
  `tests/cash_account_max.js`, `tests/precision_boundaries.js`,
  `tests/portfolio_transfers.js`, `tests/test_edit_dividend_single_submit.py`,
  `tests/test_geist_tabler_contracts.py`, `tests/test_overview_transfer_ui.py`.
- `docs/DESIGN_SYSTEM.md`, `docs/UI_ALIGNMENT.md`.

Verification:

- Focused Python regressions: **63 passed** (feedback, failed POST values,
  single transport owner, dialog names, transfers, and affected page contracts).
- Complete JavaScript suite: **all five scripts passed, 135 assertions**:
  precision 18, Max 10, transfer population 29, feedback/transport 66,
  Overview chart ranges 12.
- Syntax checks passed for `main.js`, `form_feedback.js`, and `portfolio_transfers.js`.
- Complete Python suite: **1,007 passed in 146.27 seconds**, using
  `.\venv\Scripts\python.exe -m pytest -q` and disposable test databases.
  The first run had 1,004 passes and two assertions tied to retired error
  markup; those tests now enforce the shared Alert contract while retaining
  their icon and ownership guards. The final run includes the additional
  funding-entry failed-POST regression.

Design reference: canonical preset and Nova Field/Alert source inspected;
adapted alert semantics and associations to Jinja/vanilla JavaScript. Existing
CSS treatment is intentionally retained pending Phase 3. No new framework,
dependencies, financial rules, security rules, or task-specific visual reference.

Remaining limits: DOM-model tests and rendered-response tests do not establish
browser or assistive-technology acceptance. The existing Flatpickr containment
and programmatic opener-restoration gaps remain scheduled under Phase 4; no
competing focus handler was added. No Git commands or browser-based visual
verification were performed. **Pause for review before Phase 3.**

## Phase 2 extension: financial error classification and placement

Included in Phase 2; no Phase 3 component alignment. Re-inspected the actual
`b1YmpWHpo` initialization and Nova Field/Alert JSON sources through HTTP.
Used FieldError's alert semantics and deduplication and the general Alert role
with the existing Jinja/JavaScript adapters; no browser or new framework.

### Error-path audit

| Path | Classification and presentation |
|---|---|
| Transaction add/edit, dividends, funding entries, portfolio names, symbols | Required, numeric/date syntax, positivity, length and malformed selection failures stay under the responsible input; form validators remain authoritative |
| Transaction Buy/Sell/edit/delete, dividends/edit/delete, withdrawals/funding edits/deletes | Cash, holdings, fees-versus-proceeds and chronological history failures are general service errors; removed all message-text-to-field maps |
| Portfolio create/rename/delete and symbol tracking/removal | Duplicate names, unavailable records and dependent-record failures are general; no unrelated financial field is marked invalid |
| Transfers add/edit/delete | Intrinsic fields stay local; unavailable endpoints and cross-input/account-state service failures are general; invalid non-AJAX POSTs now retain values, associations and dialog reopening instead of reducing field errors to a flash |
| Login, email update, login/recent-auth/email verification | Email/code format errors stay local; unavailable email, invalid-or-expired challenge results and submission failures use the shared general region |
| Account deletion request/verify/cancel | Code format errors associate with the code input; challenge, database, sending and rate-limit failures are general; no duplicate flash plus form error |
| Mutation guards, CSRF, global errors | Existing conflict/stale/replay and ownership enforcement preserved; JSON failures are general, with meaningful safe messages retained; ordinary redirects/navigation keep their existing general page feedback |
| Max and shared AJAX transport | Auxiliary errors do not trigger initial field validation or clear financial failures; network failures coexist with the prior unresolved server error; authoritative responses replace previous feedback |

All financial dialogs continue to use one shared general region below their
header. Account forms use the same feedback semantics within their forms.
Financial non-AJAX service-failure redirects remain general page notifications;
their redirect contracts are preserved. No field classification is inferred
from the words of a service exception. Matching identical displayed messages
is used only for deduplication, as in the inspected FieldError recipe.

Server-only financial errors now survive editing, client-valid retries, retries
blocked by client validation, and pending requests. Resetting/closing/changing
records clears them; a new authoritative result replaces them. Max and network
feedback cannot falsely establish financial success. Error focus retains
Bootstrap ownership, existing help associations and the OTP exception.

Extension files:

- `portfolio_app/utils/http.py`, `utils/__init__.py`; `routes/transactions.py`,
  `routes/portfolios.py`, `routes/auth.py`; `forms/portfolio_forms.py`,
  `forms/transaction_forms.py`, `forms/transfer_form.py`.
- `portfolio_app/static/js/form_feedback.js`, `main.js`, `portfolio_transfers.js`;
  `templates/macros/forms.html`, `templates/portfolios.html`,
  `templates/partials/transfer_modals.html`, `templates/auth/settings.html`,
  `templates/auth/reauthenticate.html`; `portfolio_app/__init__.py` (account
  rate-limit placement and asset cache version).
- `tests/test_error_classification.py` (new), `tests/modal_form_errors.js`,
  `tests/test_portfolio_rename.py`, `tests/test_portfolios_funding_entries.py`,
  `tests/test_walk_invariant.py`, `tests/test_cash_account_policy.py`;
  both design-system documents.

Verification of the extension:

- Focused classification/form/history/auth regressions: **150 passed**.
- Final classification/rendered-feedback/transfer selection: **126 passed**.
- Complete JavaScript suite: **155 assertions passed across all five scripts**
  (feedback/transport 86, Max 10, precision 18, transfers 29, charts 12).
- Syntax checks passed for all three affected JavaScript modules.
- Complete Python suite: **1,067 passed in 152.39 seconds**, using
  `.\venv\Scripts\python.exe -m pytest -q` with disposable test databases.

Remaining acceptance limits are unchanged: no browser/assistive-technology
acceptance was performed; broader overlay integration remains Phase 4. Financial
calculations, formatting, validation rules and security decisions are preserved.
No Git commands. Pause for user review before Phase 3.

## Phase 3: shared recipe alignment and review checkpoint

The user approved Phase 2, including visual acceptance, before authorizing
this phase. Re-inspected the actual `b1YmpWHpo` initialization and official
`base-nova` component JSON over HTTP on **2026-10-12**. No browser was used.
The source still specifies neutral surfaces, Geist, Tabler, radius 0.625rem,
subtle/default menus and the five blue chart roles. Sources and semantic
mappings are linked in [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md).

### Components aligned

| Family | Shared recipe changes |
|---|---|
| Typography and semantic text | 14px text-sm; 16px medium card/dialog titles; 14px foreground table headers and field labels; muted supporting metric labels and descriptions; preserved numeric formatters and brand |
| Button and icons | 32px default, 28px small and 36px large; 16px default/icon-button glyphs; small text-button 14px glyphs; proper secondary, outline, ghost, destructive, expanded and focus roles; removed custom press filtering and popup-trigger translation |
| Three-dot menus | 32px/28px named triggers, stable 16px dots; recipe item spacing, disabled state and neutral/destructive separation; retained Bootstrap/Popper placement and keyboard ownership |
| Input, Native Select, Textarea, Field | Readonly retains input recipe; disabled controls retain foreground with half opacity, with separate input/select fills; invalid destructive border/ring without tinted fill; 14px help/errors; mobile input/textarea text-base; OS-native option palette |
| Card and Table | Canonical ring/radii retained; header spacing and title weight corrected; 40px foreground headers and 8px cells; preserved financial colors, alignment, table composition and row-state behavior |
| Dialog and Alert | 384px reference dialog width, 16px spacing, unruled header, ring-only surface, muted/50 footer and reversed vertical actions below sm; Tabler close icons; scrollable form wrapper compatibility; card-background alerts with destructive text rather than tinted panels |
| Tabs and Command | Reference track/trigger geometry and theme-specific active surface; Settings tabs consume the same state tokens; Command InputGroup input/30 fill/border and one ring, 384px command surface and reference item spacing |
| Badge and Tooltip | Existing inspected 20px Badge and inverse 12px Tooltip recipes retained; fixed 12px badge icon sizing; Bootstrap tooltip lifecycle unchanged |
| Pagination and Empty | Foreground 32px controls, 2px gap and outline current-page state; Empty's 24px padding, 32px media/16px icon, 14px title and description; existing actions and information hierarchy retained |
| Calendar | Flatpickr adapter uses 28px cells, 8px padding/week gaps, 14px abbreviated month caption, Tabler chevrons, and distinct today/selected/outside/disabled states; date parsing, limits and ownership unchanged |
| Charts and legends | Both Overview and Landing read the actual five blue preset roles; removed the unused categorical palette; preserved category mapping, Other slot, data, formatting, toggles and theme redraw |

Phase 2 feedback, submit gating, server-error lifetime, correction, deduplication,
reset, associations, OTP auto-submit and transport ownership are unchanged.
The only JavaScript changes are chart token names and calendar presentation
options. No financial, authorization, database, validation-rule or API changes.

### Adaptations and exceptions

- The latest instruction explicitly preserves approved financial colours.
  Selected Buy/Sell therefore retains its financial soft surface and text;
  this is an intentional exception to neutral Tabs. Financial values, record
  types and branding are unchanged.
- Existing Flask/Jinja markup and Bootstrap, Flatpickr and Chart.js owners
  remain. Native select popup geometry belongs to the browser/OS. Flatpickr
  retains its six-week grid. Existing inline link actions, toast placement,
  financial table column widths and empty-state composition are preserved.
- Some component consumers reside in `app.css`; their recipe declarations
  were corrected in place rather than adding a later override stylesheet.
  Settings responsive-tab layout, static account-information composition,
  calendar overlay containment, palette/drawer interactions and opener focus
  restoration remain Phase 4 work. No Phase 4 handlers or page restructuring
  were introduced.
- Removed the old chart palette, masked close glyph, flat Command focus
  treatment, and now-unused text-3xs/shadow-raised tokens only after checking
  their consumers. Retained other compact tokens still used by page content.

### Changed files

Runtime (relative to `portfolio_app/`):

- `static/css/tokens.css`, `components.css`, `flatpickr-nova.css`, `app.css`.
- `static/js/main.js`, `overview_charts.js`, `landing.js`.
- `templates/assets.html`, `portfolios.html`, `partials/transfer_modals.html`,
  `auth/login.html`, `auth/reauthenticate.html`, `auth/verify_code.html`:
  decorative close icons and shared large auth button variant only.
- `templates/macros/forms.html`: comment updated; feedback markup unchanged.
- `__init__.py`: asset cache version only.

Verification and documentation:

- New `tests/test_phase3_component_contracts.py` covers semantic roles,
  light/dark invalid tokens, disabled versus readonly, menu geometry, dialog/
  alert/empty states, pagination focus, forced colours, calendar states and
  all 17 rendered modal close icons with their names and Bootstrap attributes.
- Updated source-backed expectations in `tests/test_preset_foundation.py`,
  `test_nova_component_fidelity.py`, `test_shared_surface_contracts.py`,
  `test_overview_final_contracts.py`, `test_landing_final_contracts.py`,
  `test_assets_final_contracts.py`, `test_final_polish_contracts.py`,
  `test_settings_auth_final_presentation.py`; updated the explanatory comment
  in `test_modal_accessible_names.py`.
- `tests/overview_chart_ranges.js`: verifies the five actual palette reads
  and category/Other mapping in addition to financial-range fallbacks.
- `docs/DESIGN_SYSTEM.md` and this report.

### Verification and acceptance

- Focused component, rendered accessibility, Phase 2 classification,
  security-feedback and contrast selection: **226 passed in 9.49 seconds**.
- Final button-focus/component/action-menu selection: **26 passed in 1.03 seconds**;
  hover and press cannot erase the keyboard focus ring or its border.
- Complete JavaScript suite: **159 assertions passed across five scripts**
  (feedback/transport 86, Max 10, precision 18, transfers 29, chart ranges/palette 16).
- `node --check` passed for all three changed JavaScript modules.
- Complete Python suite: **1,077 passed in 96.24 seconds** on **2026-10-13**,
  using `.\venv\Scripts\python.exe -m pytest -q` with disposable test databases.

The first full run passed 1,075 tests and encountered a Settings-tab assertion
loaded before the recipe/test update was finalized. The next full run passed
1,076 tests. A final button-focus cascade correction and regression were then
verified with focused tests and another full run. Earlier focused failures identified retired
palette, flat-Command and muted-header expectations; unrelated behavior and
security checks were retained.

User visual acceptance remains required for denser dialogs/calendar, larger
labels and headers, narrow layouts/long financial labels, light/dark states,
and the blue-only chart palette. Code/DOM-model checks do not establish browser
or assistive-technology acceptance. **No Git commands or browser-based visual
verification were performed. Pause before Phase 4 for review.**

## Phase 4: page integration, typography and interaction ownership

Authorized after Phase 3 user visual acceptance. Re-inspected the actual preset
initialization and official Nova Card, Item, Table, Label, Tabs, Command, Dialog,
Sheet, Sidebar and Dropdown Menu sources on **2026-10-13**, over HTTP only.
Also inspected the installed Bootstrap 5.3.0 Dropdown/Modal ownership and
Flatpickr 4.6.13 positioning source. No framework or dependency changes.

### Changes and decisions

- Typography: page, disclosure, Settings, auth and Landing headings; hero and
  preview figures; marker/avatar initials; tooltip emphasis and the allocation
  centre value now use 500. Ordinary text stays 400; inactive navigation is 400
  and its active destination remains 500. Card/dialog titles, table headers,
  field labels and buttons preserve their medium semantic roles and foreground
  colours. Semantic `strong`/`b` uses medium rather than synthesized bold.
  Calendar year/static-month text inherits the medium caption role instead of
  the inspected vendor's mixed 300/700 weights.
  The brand remains 600 with unchanged artwork and geometry. None of the
  inspected component roles requires an additional semibold/bold exception.
- Settings: moved the narrow composition after the base tab rule; its three
  columns now win the cascade and permit wrapping. Accessible tab orientation
  follows the same breakpoint. Static profile information uses description-list
  semantics; removed the obsolete imitation-readonly input recipe. Verified
  status consumes the shared secondary Badge, with only placement in page CSS.
  Genuine inputs, validation and account deletion flows remain unchanged.
- Three-dot menus: added labelled menu/menuitem associations, keyboard entry,
  Home/End and typeahead with disabled/hidden-item exclusion. Bootstrap retains
  arrows, Escape, Tab/outside dismissal, expanded state and Popper positioning.
  Repeated mounting is idempotent. Existing action dispatch/payloads are intact.
- Custom overlays: one coordinator owns drawer/palette background inertness,
  scroll restoration, Tab containment, Escape and opener return. The closed
  mobile sidebar cannot receive focus. A close button is inside the drawer;
  viewport transitions restore the appropriate navigation semantics and focus.
  Opening a palette from the drawer transfers ownership and its return target.
- Command: named combobox, listbox option IDs, active descendant, selected state,
  polite result count and separate empty feedback. Disabled/hidden commands
  are excluded, composition Enter is ignored, and existing navigation/actions
  are retained. The palette cannot steal focus from an active Bootstrap modal.
- Financial dialogs: all programmatic page/transfer openers use the shared
  Bootstrap-instance helper, adding only the missing return path. Menu actions
  return to their visible three-dot button; unavailable openers are skipped.
  Duplicate opens and cancelled show events do not accumulate return handlers.
  Bootstrap data-API dialogs retain their own return callback and focus trap.
- Calendars: portal inside the owning modal but outside the clipped form, with
  viewport-clamped positioning. Form scrolling closes the calendar; scrolling
  within it does not. Escape dismisses the active calendar first. Date parsing,
  format, input state, selection and modal-close cleanup remain with their owners.

Existing page composition, financial colours, calculations, numeric formatting,
server validation, Phase 2 feedback lifecycle, OTP exception, authentication,
security, routes and persistence are preserved. Shared surfaces and page-specific
layout are retained where they already satisfy the approved contracts. Removed
only superseded static-field/badge declarations and the undersized sidebar
collapse glyph override. Financial Buy/Sell colours and the brand remain the
documented exceptions; native select menus and Flatpickr's six-week grid retain
their existing technology adaptations.

### Changed files

Runtime, relative to `portfolio_app/`:

- `static/js/overlays.js` (new); `shell.js`, `main.js`,
  `portfolio_transfers.js`, `overview_charts.js`.
- `static/css/base.css`, `components.css`, `app.css`, `landing.css`,
  `flatpickr-nova.css`.
- `templates/base.html`, `auth/settings.html`, `assets.html`, `portfolios.html`.
- `__init__.py`: asset cache version only.

Tests: new `tests/overlay_contracts.js` and `test_phase4_page_contracts.py`;
updated shared-opener seams in `precision_boundaries.js`, `portfolio_transfers.js`
and `test_form_feedback.py`. Documentation: this report and `DESIGN_SYSTEM.md`.

### Verification and review checkpoint

- Focused component, rendered markup, feedback/classification and brand checks:
  **109 passed in 8.39 seconds**.
- Final calendar-caption/component/Phase 4 checks: **25 passed in 0.80 seconds**.
- Complete JavaScript suite: **269 assertions across six scripts**: feedback 86,
  Max 10, precision 18, transfers 29, chart roles/ranges 16, new overlay/menu/
  palette/drawer/calendar regressions 110. All five changed JS modules passed
  `node --check`.
- The first complete Python run passed 1,080 tests and found two obsolete
  assertions expecting direct Bootstrap calls. Only their opener expectation
  was updated; retained-value, error, required-field and association assertions
  are unchanged.
- Final complete Python suite: **1,082 passed in 142.78 seconds**, using
  `.\venv\Scripts\python.exe -m pytest -q` and disposable test databases on
  **2026-10-13**.

User visual acceptance is still required for lighter typography in both themes,
the Settings tab/label-value presentation, mobile drawer transitions, and
calendar placement in narrow or scrolled dialogs. DOM-model and source checks
do not establish browser/screen-reader acceptance. **No Git commands or
browser-based visual verification. Phase 5 has not begun; pause for review.**

### Earlier lightweight typography refinement (superseded)

Historical implementation record: the final correction below supersedes this
weight strategy after the user's visual review.

The user accepted Phase 4 functionality and testing, then requested noticeably
lighter typography before visual acceptance. This supersedes the initial
400/500 weight strategy above. Re-inspected the exact preset initialization and
13 relevant official Nova recipes over HTTP on **2026-10-13**. Their medium
component weights are intentionally adapted under the user's explicit direction;
semantic roles and all other component recipes remain intact.

- **300:** large page/auth headings, generic h1/h2, Landing hero/section headings,
  and large financial/product-preview display figures.
- **400:** compact card/dialog/section headings, table column headers, metric and
  field labels, buttons/actions, sidebar/other navigation, tabs, badges, menus,
  pagination, empty titles, calendar captions, initials and ordinary numeric data.
  Body/help/errors remain regular for reading clarity. Chart centre labels and
  values use the same token; both charts explicitly use regular tooltip text.
- **500 exceptions:** semantic inline `strong`/`b`, formula-name emphasis and
  the named record in destructive confirmation prose. These remain distinguishable
  within otherwise regular text. No navigation/control/heading requires 500.
- **Brand exception:** unchanged 600 wordmark and unchanged logo assets, geometry,
  colour and markup. The existing 500/600 tokens retain their numeric meanings.

All shells load actual Geist 300 in addition to 400/500/600. Hierarchy comes from
existing size, semantic colour contrast, placement and spacing, with 300 confined
to larger text. No font-size, line-height, spacing, component-dimension or colour
declarations were changed. A before/after fingerprint comparison of all six CSS
files, excluding comments and weight declarations, confirmed this boundary.
Removed redundant weight declarations for active navigation, current-page
pagination and tooltip emphasis. No new CSS override layer or page-level patch.

Changed files for this refinement (relative to repository root):

- `portfolio_app/static/css/tokens.css`, `base.css`, `components.css`, `app.css`,
  `landing.css`, `flatpickr-nova.css`.
- `portfolio_app/static/js/overview_charts.js`, `landing.js`: typography only.
- `portfolio_app/templates/base.html`, `auth_base.html`, `landing.html`: font URL only.
- `portfolio_app/__init__.py`: asset cache version only.
- `tests/test_phase4_page_contracts.py`, `test_phase3_component_contracts.py`,
  `test_geist_tabler_contracts.py`, `test_landing_final_contracts.py`,
  `test_nova_component_fidelity.py`, `test_shared_surface_contracts.py`,
  `overview_chart_ranges.js`.
- `docs/DESIGN_SYSTEM.md` and this report.

Verification:

- Focused typography/component/brand/contrast checks: **105 passed in 1.36 seconds**.
- Complete JavaScript suite: **275 assertions across six scripts** (110 overlay,
  86 form feedback, 10 Max, 29 transfers, 22 chart range/palette/typography,
  18 precision). Chart checks verify weights while retaining displayed values
  and semantic colours. Both changed JavaScript files passed syntax checks.
- Complete Python suite: **1,084 passed in 133.23 seconds**, using
  `.\venv\Scripts\python.exe -m pytest -q` with disposable test databases.

Phase 2 validation, Phase 3 recipes outside font weight, Phase 4 interactions,
financial calculations/formatting/colours, authentication and security are
unchanged. No Git commands, browser visual verification, or Phase 5 work.
User visual acceptance should assess 300-weight display text, compact 400-weight
headers/actions, and unchanged inline emphasis/brand in both themes and on the
user's normal screens. Font rendering and slightly different glyph widths can
affect perceived balance or wrapping even though layout dimensions are unchanged.

### Final typography correction: compact sizes, preset weights (Phase 4)

The user replaced the lightweight direction with extra-compact font sizes and
strict preset component weights. On **2026-10-13**, re-inspected the exact preset
initialization and 21 official Nova recipes over HTTP: Button, Card, Item, Table,
Dialog, Label, Input, Textarea, Native Select, Tabs, Sidebar, Dropdown Menu,
Command, Badge, Calendar, Empty, Alert, Tooltip, Pagination, Avatar and Chart.
These sources remain linked in the design system; no browser visual verification
was performed. No task-specific screenshot was used for this correction.

The shared typography contract in [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md#typography)
now records the final sizes, weight mapping and explicit exceptions:

- **500:** titles, table headers, field labels, buttons/actions, tabs, badges,
  pagination, calendar captions, active navigation and menu/group headings.
  Financial display values and chart tooltip title/numeric text also use 500.
- **400:** body/descriptions, supporting metric labels, fields, table cells,
  normal navigation, menu items, initials, calendar days/weekdays and chart labels.
  Native `strong`/`b` no longer has a lighter cap. No 300 token remains.
- **Compact sizes:** 11px auxiliary text, 12px controls/table text, 13px body,
  14px card/dialog titles, 15px supporting metrics and 18px page/auth titles.
  Landing headings retain a fluid 28–40px hero and 18–24px section hierarchy;
  its preview figure uses 22–28px. Mobile raises auxiliary text to 12px and
  ordinary controls/table text to 13px; editable controls use 16px.
- **Primary Book Value exception:** original responsive
  `clamp(2rem, 1.2rem + 2.6vw, 3.25rem)` (32–52px), 500 weight, unchanged
  display/full-value formatters and count-up source. The compact scale does not
  shrink this financial headline.
- **Brand exception:** unchanged 18px/600 Geist, tracking and artwork; a dedicated
  size token prevents the smaller shared title scale from changing the wordmark.

Coverage includes Landing, authentication/verification, Overview, Portfolios,
Assets, Settings, shell/navigation, financial dialogs, calendars, tables,
three-dot menus, command palette, feedback, pagination and empty states. The
existing Flask/CSS architecture adapts official semantic roles; custom page
headings use the closest Card/Item title role. Only font sizes intentionally
depart from component typography recipes, plus the explicitly preserved brand.
Existing control dimensions, spacing, colours, numeric precision and behaviour
remain unchanged. Mobile field sizing now follows the command-input declaration
so desktop specificity cannot override its readability exception.

Changed files for this correction (relative to repository root):

- `portfolio_app/static/css/tokens.css`, `base.css`, `components.css`, `app.css`,
  `landing.css`, `flatpickr-nova.css`.
- `portfolio_app/static/js/overview_charts.js`, `landing.js`: chart typography only;
  draw-time token resolution preserves responsive chart labels and tooltips.
- `portfolio_app/templates/base.html`, `auth_base.html`, `landing.html`: font URL
  now requests 400/500/600/700; 700 supports native semantic emphasis.
- `portfolio_app/__init__.py`: asset cache version only.
- `tests/test_phase4_page_contracts.py`, `test_phase3_component_contracts.py`,
  `test_brand_lockup.py`, `test_geist_tabler_contracts.py`,
  `test_landing_final_contracts.py`, `test_nova_component_fidelity.py`,
  `test_shared_surface_contracts.py`, `overview_chart_ranges.js`.
- `docs/DESIGN_SYSTEM.md` and this report.

Verification:

- Focused typography/component/brand/contrast/page/formatting checks, including
  the Book Value exception: **160 passed in 1.54 seconds**.
- Complete JavaScript suite: **289 assertions across six scripts** (110 overlay,
  86 form feedback, 10 Max, 29 transfers, 36 chart range/palette/typography,
  18 precision). Both changed JavaScript files passed syntax checks.
- Complete Python suite after the Book Value adjustment: **1,085 passed in
  121.99 seconds**, using `.\venv\Scripts\python.exe -m pytest -q` with disposable
  test databases.

Source checks cover semantic weight mapping, mobile size floors, unchanged
control heights, brand geometry, primary Book Value sizing and formatting,
chart text resizing and existing financial/interaction contracts. They do not
establish rendered wrapping or visual acceptance. User review should assess
11px desktop auxiliary text, narrow form/dialog/calendar text fit, table decimal
legibility, chart legends, both themes and the restored large Book Value.
No Git commands or browser-based visual verification. Phase 5 has not begun;
pause for user visual review.

## Phase 5: final audit, verification and cleanup

Completed **2026-10-13**, following full user approval and visual acceptance of
Phase 4. Final Phase 5 approval is pending. The updated coverage matrix and
ownership register above describe current implementation rather than Phase 1
intentions. Earlier phase sections are historical records, not open work items.

### Findings and corrections

- Re-inspected the live preset initialization and official Nova Button, Card,
  Table, Dialog, Field, Input, Sidebar, Dropdown Menu, Command, Calendar and Chart
  recipe source over HTTP. Retained the approved component weight mapping,
  compact size exception, original 32–52px Book Value, 18px/600 brand, financial
  colours and existing Flask/Bootstrap/Flatpickr/Chart.js adapters. No new design
  decisions or task-specific visual reference were introduced.
- Reviewed all six owned stylesheets, eight production JavaScript modules,
  template/page families, financial dialog registration, shared feedback and
  source-backed component tests. No unresolved migration from the initiative's
  original coverage inventory was identified. This is an implementation finding,
  not a claim of exhaustive browser or assistive-technology coverage.
- Removed `FormValidator`, a constructor-only forwarding wrapper introduced
  during shared-feedback migration. Its sole runtime caller now registers rules
  directly with `OnePortfolioForms`; singleton ownership, listener ordering and
  `ModalAjaxHandler` transport remain unchanged. No external/window export or
  other caller existed. Corrected the obsolete dividend comment that attributed
  hidden-event resets to the transport layer.
- Removed unused `form_error` imports from Login, Verify Code and Email Update;
  each uses `form_errors_summary`, whose internal shared Alert stays intact.
- Removed three ineffective font-size declarations on the login mail SVG,
  asset-filter chevron SVG and Landing limit-list SVGs. Verified their macro
  consumers are fixed-size Tabler SVGs with no text or em-based geometry; their
  visible size remains owned by `.icon` and component width/height rules.
- No duplicate property declarations were found within owned CSS rule blocks.
  Candidate unused classes were traced to dynamic flash categories, record-type
  roles, chart swatches, Bootstrap tooltip markup and Flatpickr markup and were
  retained. Shared variant recipes were not deleted merely for lacking a literal
  template occurrence. No broad CSS pruning or unrelated refactor was performed.
- Corrected stale documentation about unresolved calendar/opener focus, missing
  command containment, pending Phase 4 work, and separate AJAX/server Alert
  markup. Historical test counts and superseded typography remain explicitly
  historical. The current design-system contract reflects the approved result.

### Verification evidence

- **Focused Python: 262 passed in 6.11 seconds.** Covered feedback/classification,
  single dividend submission, Phase 3/4 component contracts, icons, Landing,
  menus, dialog names, preset/brand, contrast, shared surfaces, Overview,
  Portfolios, Assets, Settings/auth and numerical formatting.
- **Complete Python: 1,087 passed in 85.22 seconds**, using
  `.\venv\Scripts\python.exe -m pytest -q` and disposable test databases. This
  includes financial/accounting, exact decimal storage, migrations, ownership,
  authentication, CSRF/mutation and UI regressions.
- **Complete JavaScript: 289 assertions across all six scripts:**

  | Script | Assertions passed |
  |---|---:|
  | `tests/precision_boundaries.js` | 18 |
  | `tests/portfolio_transfers.js` | 29 |
  | `tests/overview_chart_ranges.js` | 36 |
  | `tests/overlay_contracts.js` | 110 |
  | `tests/modal_form_errors.js` | 86 |
  | `tests/cash_account_max.js` | 10 |

- `node --check` passed for all eight production JavaScript files.
- Strengthened rendered-response tests cover all **17 financial dialogs**:
  exactly one summary inside the form's modal body, after its header and before
  visible inputs; resolved ARIA references; labelled required fields; native
  validation suppression for editable forms; CSRF and mutation token fields.
  The two added cases supplement existing server-error/failed-POST tests.
- Existing behavioral tests execute application adapters in DOM models: no
  blur-triggered field errors, post-submit corrections, persistent general
  financial errors, session reset, stale responses, one request owner, custom
  overlay exclusion, keyboard handling and focus return. OTP auto-submit remains
  source-guarded and server authentication workflows retain their full coverage.

### Changed files

- `portfolio_app/static/js/main.js`
- `portfolio_app/static/css/components.css`, `portfolio_app/static/css/landing.css`
- `portfolio_app/templates/assets.html`
- `portfolio_app/templates/auth/login.html`, `verify_code.html`, `update_email.html`
- `portfolio_app/__init__.py` (asset cache version only)
- `tests/test_form_feedback.py`, `tests/test_edit_dividend_single_submit.py`
- `docs/DESIGN_SYSTEM.md`, `docs/UI_ALIGNMENT.md`

### Exceptions, verification limits and handoff

Approved exceptions remain intentional: compact text sizes with mobile
readability floors and 16px editable fields; original large Book Value;
unchanged brand; semantic financial colours; existing page composition and
technology adapters. They are not incomplete migrations. Financial table text
retains full formatting/precision and tabular alignment; cleanup changes no
font weights, effective text sizes, component dimensions, colours or layouts.

No financial/domain, persistence, security, route or API code changed. No new
dependency, framework, focus handler, validation rule or request owner was added.
No known unresolved regression was found in the audited contracts or executed
suites. Unit/source/rendered-response checks cannot establish actual text
wrapping, vendor focus behavior in a browser, screen-reader announcements, touch
ergonomics or all device/font combinations. The user's prior visual acceptance
is retained; the agent performed no browser-based visual verification.

**Phase 5 complete and paused for final user approval. No Git commands, commits,
merges or branch cleanup were performed.**
