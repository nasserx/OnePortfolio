# OnePortfolio design system

OnePortfolio keeps its Flask/Jinja structure, financial workflows, and compact
ledger character. Its visual source of truth is the official shadcn preset
`b1YmpWHpo`: Nova style, neutral base and theme, blue charts, Tabler icons,
Geist typography, a `0.625rem` radius, subtle menu accent, and default menu
colour.

Phases 1–4 of the UI alignment have user approval, including final visual
acceptance of compact typography and the large Book Value. The
[coverage and ownership register](UI_ALIGNMENT.md) records the current source
inventory, verified contracts, historical baselines, and Phase 5 final audit.
Source/rendered-response and DOM-model checks are distinct from browser and
assistive-technology acceptance; final Phase 5 approval remains with the user.

This document separates four contracts. They must not be blended into a
second, application-specific brand palette.

## Reference provenance and semantic roles

Inspected on **2026-10-10**, using HTTP source retrieval without browser-based
visual verification:

- [Canonical preset](https://ui.shadcn.com/create?preset=b1YmpWHpo).
- [Exact preset initialization](https://ui.shadcn.com/init?preset=b1YmpWHpo):
  `base-nova`, neutral base/theme, `font-geist`, Tabler, subtle menu accent,
  default menu colour, blue chart roles, and `radius: 0.625rem`.
- Official Nova recipes: [Card](https://ui.shadcn.com/r/styles/base-nova/card.json),
  [Item](https://ui.shadcn.com/r/styles/base-nova/item.json),
  [Table](https://ui.shadcn.com/r/styles/base-nova/table.json),
  [Button](https://ui.shadcn.com/r/styles/base-nova/button.json),
  [Dropdown Menu](https://ui.shadcn.com/r/styles/base-nova/dropdown-menu.json),
  [Dialog](https://ui.shadcn.com/r/styles/base-nova/dialog.json),
  [Field](https://ui.shadcn.com/r/styles/base-nova/field.json),
  [Label](https://ui.shadcn.com/r/styles/base-nova/label.json),
  [Input](https://ui.shadcn.com/r/styles/base-nova/input.json),
  [Native Select](https://ui.shadcn.com/r/styles/base-nova/native-select.json),
  [Textarea](https://ui.shadcn.com/r/styles/base-nova/textarea.json),
  [Input Group](https://ui.shadcn.com/r/styles/base-nova/input-group.json),
  [Tabs](https://ui.shadcn.com/r/styles/base-nova/tabs.json),
  [Badge](https://ui.shadcn.com/r/styles/base-nova/badge.json),
  [Tooltip](https://ui.shadcn.com/r/styles/base-nova/tooltip.json),
  [Alert](https://ui.shadcn.com/r/styles/base-nova/alert.json),
  [Empty](https://ui.shadcn.com/r/styles/base-nova/empty.json),
  [Pagination](https://ui.shadcn.com/r/styles/base-nova/pagination.json),
  [Calendar](https://ui.shadcn.com/r/styles/base-nova/calendar.json),
  [Command](https://ui.shadcn.com/r/styles/base-nova/command.json), and
  [Sidebar](https://ui.shadcn.com/r/styles/base-nova/sidebar.json).

These live sources define the reference; local classes, comments, and tests
are implementation evidence, not independent proof of compliance. Reinspect
the corresponding recipe before a later phase materially changes it. If a
source becomes inaccessible, report the specific limitation and do not invent
replacement visual rules. No task-specific screenshot was supplied for this
audit; existing product composition is retained.

| Semantic role | Reference contract | Application mapping |
|---|---|---|
| Card title | Card foreground; 16px, medium; small Card variant uses 14px | Titles identify a card, not a muted annotation |
| Card description | 14px, muted foreground | Supporting descriptions below titles |
| Supporting metric label | Closest reference is descriptive Card/Item text; Item title itself is foreground | Financial label/value composition is an application adaptation: muted supporting label, foreground value, financial tone only where meaningful |
| Table header | Foreground, medium; Table inherits 14px text, header height 40px | Both native records tables and the Overview ledger; no blanket muted-header rule |
| Field label | 14px, medium, inherited foreground | Labels retain required semantics and control associations |
| Field description/error | 14px muted description; 14px destructive error with alert semantics | Help and validation have separate roles and timing |
| Readonly input | Input recipe has no separate readonly fill or opacity | Preserve focus, selection, copying, and submission behavior |
| Disabled control | Use the control's own recipe and native disabled semantics | Input/textarea and native select must not be assumed to have identical fills |
| Financial value | Existing number macro, formatting, signs, and approved financial roles | Never derive an accounting or precision change from typography |

Default `text-sm` in the inspected recipes means 14px. Phase 4's explicitly
requested compact font-size exception is documented under Typography below;
the reference sizes in this table remain the official baseline. Component
weights and foreground/muted roles continue to follow their own recipes.

## A. Official preset contract

The canonical CSS API is defined in `static/css/tokens.css`.

| Role | Light | Dark |
|---|---|---|
| `--background` | `oklch(1 0 0)` | `oklch(0.145 0 0)` |
| `--foreground` | `oklch(0.145 0 0)` | `oklch(0.985 0 0)` |
| `--card`, `--popover` | `oklch(1 0 0)` | `oklch(0.205 0 0)` |
| card/popover foreground | `oklch(0.145 0 0)` | `oklch(0.985 0 0)` |
| `--primary` | `oklch(0.205 0 0)` | `oklch(0.922 0 0)` |
| `--primary-foreground` | `oklch(0.985 0 0)` | `oklch(0.205 0 0)` |
| secondary/muted/accent | `oklch(0.97 0 0)` | `oklch(0.269 0 0)` |
| `--muted-foreground` | `oklch(0.556 0 0)` | `oklch(0.708 0 0)` |
| `--destructive` | `oklch(0.577 0.245 27.325)` | `oklch(0.704 0.191 22.216)` |
| `--border` | `oklch(0.922 0 0)` | `oklch(1 0 0 / 10%)` |
| `--input` | `oklch(0.922 0 0)` | `oklch(1 0 0 / 15%)` |
| `--ring` | `oklch(0.708 0 0)` | `oklch(0.556 0 0)` |

`--secondary-foreground` and `--accent-foreground` are the preset's primary
neutral ink for their surfaces. Sidebar roles are also canonical: sidebar
surface, foreground, primary, accent, border, and ring are not aliases to an
unrelated application palette.

Normal actions use `--primary`; destruction uses `--destructive`. Success,
warning, and information messages do not borrow financial colours. There is no
green `.btn-success` or amber `.btn-warning` contract. Nova's destructive
button is a restrained red treatment, while ordinary actions stay primary.

### Chart palette

The preset supplies exactly five visualization roles:

```css
--chart-1: oklch(0.809 0.105 251.813);
--chart-2: oklch(0.623 0.214 259.815);
--chart-3: oklch(0.546 0.245 262.881);
--chart-4: oklch(0.488 0.243 264.376);
--chart-5: oklch(0.424 0.199 265.638);
```

Phase 3 uses these roles directly in both Chart.js consumers and the shared
legend. The old categorical `--portfolio-chart-*` palette has no remaining
runtime consumers and was removed. Chart roles never style portfolio initials,
avatars, buttons, navigation, generic badges, or entity UI. There is no
`--chart-6`, `--chart-7`, or `--chart-other`; existing top-four-plus-Other
behavior uses five slots. Values, ordering, legend interaction, numeric
formatting, and theme redraw behavior are unchanged.

### Radius

The sole foundation is `--radius: 0.625rem`. The generated shadcn derivation is
translated exactly:

```css
--radius-sm: calc(var(--radius) * 0.6);
--radius-md: calc(var(--radius) * 0.8);
--radius-lg: var(--radius);
--radius-xl: calc(var(--radius) * 1.4);
--radius-2xl: calc(var(--radius) * 1.8);
--radius-3xl: calc(var(--radius) * 2.2);
--radius-4xl: calc(var(--radius) * 2.6);
```

Nova controls use `--radius-lg`; compact menu items and tab triggers use
`--radius-md`; cards and dialogs use `--radius-xl`; dropdown and tooltip panels
use the recipe-specific `--radius-lg` and `--radius-md`. A pill radius is
allowed only where the shape itself carries established meaning, such as a
badge or compact signed delta.

### Themes

Light is the base `:root`. Dark roles are repeated under system dark preference
and explicit `data-theme="dark"`; automated tests require those two blocks to
remain identical. The inline preference script applies the saved theme before
paint. Canvas content is redrawn on `op:themechange`, because canvas pixels do
not react to CSS custom properties.

## B. OnePortfolio financial extensions

The approved financial colour extensions are:

- `--financial-positive`
- `--financial-negative`
- `--financial-income`
- `--financial-flat`

They are permitted only when colour communicates real financial meaning:
signed returns, realized profit/loss, signed Dividend Income, financial delta
indicators, financial record-type text, and the currently selected Buy/Sell
transaction direction. Record types use the shared `record_type` Jinja macro:
Buy and Deposit are positive, Sell and Withdrawal are negative, Dividend Income uses
the income role, and Initial or unknown types remain neutral.
Explicit signs, values, and selector labels remain the primary cue; colour is
never the only cue.

They are forbidden on portfolio markers, ordinary buttons, navigation,
generic badges, chart categories, generic notifications, and decorative
surfaces. Selected transaction direction retains its approved financial
colour exception under the Phase 3 preservation requirement. `--destructive` remains distinct from `--financial-negative`, even
where their appearance is close.

## C. Compatibility boundary

OnePortfolio component and page styles consume the canonical preset roles
directly. Names such as `--bg-canvas`, `--fg-default`, `--line-default`, and
`--brand-solid` are not part of the current design-system API.

The `--bs-*` declarations at the bottom of `tokens.css` are the only controlled
compatibility bridge. They are vendor inputs, not OnePortfolio component API.
Bootstrap remains in the `vendor` layer for modal, dropdown, Popper, and utility
behavior; semantic CSS owns the final appearance. Application JavaScript and
server forms own validation.

## D. Structural application rules

### File and cascade layout

```text
static/css/
  tokens.css      layers, canonical tokens, extensions, Bootstrap bridge
  base.css        reset, elements, typography, focus and motion primitives
  components.css  reusable controls, cards, tables, menus, dialogs and states
  flatpickr-nova.css  unlayered adapter loaded after Flatpickr's vendor CSS
  app.css         authenticated shell and page layout
  landing.css     marketing-page layout
```

Templates load `tokens → base → components → app` (or `landing`). `tokens.css`
must remain first because it declares the cascade layer order and imports
Bootstrap into `vendor`:

```css
@layer vendor, tokens, base, components, pages, utilities;
```

Do not solve vendor conflicts with escalating specificity. Restyle stable
Bootstrap component contracts in `components.css`, map variables in the single
bridge, and keep Bootstrap's runtime attributes and lifecycle intact.

### Typography

The canonical API is `--font-sans`, `--font-heading`, and `--font-mono`.
The sans token names Geist followed by the system sans stack, and the heading
token inherits that same contract. The authenticated, authentication, and
public shells load the 400, 500, 600, and 700 weights from the existing Google
Fonts origins. Components and Chart.js consume the tokens rather than naming a
face independently. Component typography follows the inspected semantic roles
above. The user explicitly requested compact font sizes while restoring exact
preset component weights; this supersedes the earlier lightweight refinement.
Headings use the
heading token, and financial columns preserve tabular numbers through the
shared root feature settings.

Numeric typography is separate from display precision. Changing a font size or
weight must never alter financial rendering rules.

Phase 4's final correction re-inspected the exact preset initialization and
21 official Nova recipes over HTTP on **2026-10-13**: Button, Card, Item, Table,
Dialog, Label, Input, Textarea, Native Select, Tabs, Sidebar, Dropdown Menu,
Command, Badge, Calendar, Empty, Alert, Tooltip, Pagination, Avatar and Chart.
Recipes without an explicit weight inherit regular text; they must not inherit
a blanket control or heading weight. Custom page headings use the closest
Card/Item title role; financial display values use the emphasized value role.

| Application role | Final weight | Semantic mapping |
|---|---|---|
| Card/dialog/section/page/auth/empty titles, table headers, field labels | 500 (`--weight-medium`) | Title, TableHead and Label recipes; titles remain foreground |
| Buttons, tabs, badges, pagination, calendar captions, active navigation, menu/group headings | 500 | Corresponding control/title recipes; pagination composes Button |
| Body, descriptions, supporting metric labels, inputs/selects, table cells, normal navigation, menu items, initials, calendar days/weekdays, tooltip prose | 400 (`--weight-regular`) | Inherited regular text; supporting descriptions retain muted roles |
| Emphasized financial display values and chart tooltip title/numeric value | 500 | Emphasized value and Chart recipes; ordinary financial table cells stay 400 |
| Chart centre labels and legends | 400 | Descriptive labels |
| Native semantic `strong`/`b` | Native bolder | Removed the application-wide weight cap; 700 is available for native emphasis |
| Brand/logo | Existing 600 | Explicit user preservation exception; existing 18px, Geist, tracking, artwork and geometry unchanged |

No 300 token or blanket lighter override remains. Shared recipes consume their
weight directly; tokens retain their literal numeric meaning. Font sizes are
the intentional application exception, not weights or semantic colours.

| Size role / token | Desktop at 16px root | Narrow screens below 768px |
|---|---|---|
| Auxiliary labels, badges, tooltips (`text-2xs`, `text-xs`) | 11px | 12px |
| Controls, table text, navigation, descriptions (`text-sm`) | 12px | 13px |
| Reading/body (`text-md`) | 13px | 13px |
| Card/dialog titles (`text-lg`) | 14px | 14px |
| Intermediate title (`text-xl`) / page/auth title (`text-2xl`) | 16px / 18px | Same |
| Financial table/detail text (`num-sm`, `text-detail`) | 12px | 13px |
| Supporting metric value (`num-lg`) | 15px | 15px |
| Landing hero / section headings | Responsive 28–40px / 18–24px | Same fluid scale |
| Landing preview figure (`num-display`) | Responsive 22–28px | Same fluid scale |
| Primary Overview Book Value (`num-hero`) | **Original responsive 32–52px** | Original `clamp(2rem, 1.2rem + 2.6vw, 3.25rem)` |
| Chart labels / centre value | 11px / 14px | 12px / 15px |

The primary Book Value is explicitly exempt from compact sizing. Its 500 weight,
formatters, count-up source, full-value title and responsive clamp are preserved.
The brand has its own unchanged 18px token, decoupled from the compact title scale.
OTP text remains 16px; mobile input, textarea, native select, command input and
calendar month/year controls use 16px for practical readability and focus zoom.
Control heights, padding, spacing, row geometry and numerical precision are
unchanged. Chart font callbacks read shared tokens at draw time so responsive
sizes apply after resizing. User visual acceptance must assess actual text fit,
wrapping and readability; source checks do not establish those outcomes.

Settings' static account values are description lists, not imitation inputs;
the verified marker consumes the shared secondary Badge. Genuine readonly and
disabled input recipes and validation states are unchanged.

### Numbers in templates

All figures go through the existing macros in `templates/macros/ui.html`.
Authoritative behavior remains:

- money: fixed two decimals by default;
- quantity: variable precision with trailing zeros removed;
- percentage: two decimals by default;
- price: per-asset precision;
- Average Unit Cost: at least two decimals or price precision;
- fees: trailing zeros removed;
- realized profit/loss: explicit sign plus financial semantic role;
- Dividend Income: financial income role;
- undefined: em dash.

Internal Decimal precision and display precision remain separate. Do not
reproduce sign/format conditionals in individual templates.

### Layout and fixed geometry

Keep one hero number per screen and demote supporting figures. Comparative
numeric columns are right-aligned with tabular numbers. The application has one
geometry governed by the corresponding preset recipes: default controls are
two rem high, while tables, compact buttons, cards, and supporting text retain
their own recipe dimensions. The compact typography exception above changes
text sizes without reducing component geometry. There is one shared scale with
responsive readability floors, no density preference or `data-density` mode.

The application skeleton remains recognizable:

- authenticated sidebar/mobile navigation and in-content page header;
- Overview hero, allocation visualization, and portfolio ledger;
- Portfolios and Assets disclosure/table workflows;
- existing filters and search;
- modal-based CRUD;
- settings and authentication flows.

Presentation may change; destinations, form names/actions, modal lifecycle,
AJAX contracts, calculations, and financial meanings may not.

### Shared components

The authored shadcn Nova registry stylesheet is the component-recipe reference,
not only a source of theme variables. Its compact geometry is translated to
semantic Flask CSS: default controls are 2rem high, focus-visible uses the
component border plus a three-pixel 50%-opacity `--ring`, cards and popovers use
a 10%-foreground hairline ring, and disabled controls retain their native
meaning at 50% opacity. Forced-colors mode supplies a system outline instead of
changing the ordinary Nova appearance.

- Buttons: primary, secondary/outline, ghost/link, and destructive variants.
- Forms: canonical input, ring, muted disabled state, and destructive errors.
- Cards/tables: card roles, restrained border/ring, compact rows, and Nova's
  single `--border` separator with a `--muted` 50% body-row hover. Tables rest
  on the containing surface without Bootstrap contextual fills or inset
  accent shadows; selected rows use `--muted`, while headers remain neutral
  foreground text with medium weight rather than a filled band.
- Menus/popovers/dialogs: popover roles, recipe-specific radii, restrained
  foreground hairline ring, and overlay elevation.
- Tabs/segmented controls: muted track, neutral selected surface.
- Pagination: client-side lists retain page state and filtering locally while
  the shared `OnePortfolioPagination` renderer owns native button semantics,
  `aria-current`, disabled previous/next states, and Tabler chevrons.
- Alerts/toasts: neutral by default; destructive only for destructive/error
  meaning, never financial positive/income decoration.
- Empty states: card/muted roles and existing calls to action only.
- Entity initials: neutral muted surface, border, and foreground.

#### Surface ownership

Reusable outer edges live in `components.css`; page styles own internal layout
only. The contracts are:

- `.surface-card`: card background/foreground, `--radius-xl`, and one
  10%-foreground hairline ring. `.card` and `.panel` share this recipe.
- `.surface-interactive`: composes with a card and moves keyboard focus to the
  containing surface without changing its geometry. Its primary control uses
  `.surface-interactive__control` so an inner button does not draw a second
  ring. A disclosure header uses the same neutral hover affordance while its
  trigger is collapsed or expanded; only the header is tinted, never the
  revealed body.
- `.surface-table`: the same quiet outer frame for a table-like composition;
  table headers and rows own only their internal canonical `--border`
  separators.
- `.dropdown-menu`: popover roles, `--radius-lg`, menu shadow, and one hairline
  ring. Bootstrap supplies its runtime behavior; this shared recipe owns its
  presentation.
- `.surface-dialog`: popover roles, `--radius-xl`, no elevation shadow, and one
  hairline ring. Bootstrap modals and the command palette consume it.

Overview hero, allocation card, ledger, disclosure cards, authentication
forms, the Landing product preview, and empty states compose these contracts. Their page selectors must
not restate outer borders, radii, backgrounds, or elevation. A responsive table
may replace its frame with per-row cards when the semantic table is deliberately
restacked; that is a structural exception, not a second desktop surface recipe.

#### Standalone and compound inputs

`.form-control` and `.form-select` own their complete input edge and focus
recipe. Input/Textarea, Native Select and Command use 16px text below 768px
and compact 12px text above. Readonly inputs retain their fill, copying, focus and
submission semantics. Disabled input/textarea use input/50 (dark input/80)
and 50% opacity; disabled selects keep their normal fill with 50% opacity.
Invalid fields retain their normal fill and gain the destructive border and
three-pixel ring (20% light, 40% dark). CSS never uses native `:invalid` to
bypass the shared submit gate.

Command's `.command-input-group` uses the inspected input/30 fill and border,
32px height, and one focus-visible ring on the group. The inner input remains
edge-free. Icon and placeholder retain their own muted roles during focus.
There is no additional JavaScript focus handler. Forced-colors outlines live
in the final utility layer so component declarations cannot hide them.

#### Transaction direction

The current `.tx-type-tabs` and `.tx-type-tab` form the reusable neutral segmented contract
for transaction direction. Only `.tx-tab-buy.active` and
`.tx-tab-sell.active` extend it: the selected Buy uses the financial-positive
soft surface/line/foreground, and selected Sell uses the corresponding
financial-negative roles. Unselected choices, ordinary buttons, tabs,
navigation, and badges remain canonical neutral components. The hidden native
select stays authoritative; JavaScript only mirrors its value into `.active`
and `aria-pressed` states. The soft roles mix 6% positive or 12% negative into
`--popover` in Cartesian OKLab (line roles use 32%), preventing low-chroma hue rotation as the
semantic colour approaches the neutral surface. Selected hover and focus keep
the semantic surface; the shared focus-visible contract remains responsible
for keyboard indication.

Phase 3 aligns the selector geometry and focus/invalid treatment while retaining
the selected Buy/Sell colours under the latest explicit requirement to preserve
approved financial colours. This is an intentional financial exception to
neutral Tabs; ordinary view/settings tabs use the preset selected surface.
The positive/negative/income/flat palette, financial value/record colours,
selected transaction type and calculations remain intact.

#### Context labels and supporting items

`.badge--secondary` is the official Nova secondary Badge translation: compact
`--radius-4xl` geometry with `--secondary` and `--secondary-foreground`. It is
the shared low-emphasis contract for contextual labels such as an asset's
portfolio name; it never carries financial or chart meaning.

`.supporting-item` is the non-interactive Flask translation of Nova's outline
Item: transparent inherited surface, one `--border` edge, `--radius-lg`,
compact `px-3`/`py-2.5` spacing, and no shadow. It does not use Nova's separate
muted-fill variant. Labels use `--muted-foreground`, values use `--foreground`,
and only the nested formatted number may add a genuine financial semantic role.

The authenticated Overview uses unboxed `.fact` pairs within its single Book
Value card. Cumulative P&L sits immediately below the hero amount, alongside its
signed return pill; that percentage is not a ratio of Book Value. Net
Contributions and Cash share the first supporting row, with Dividends below.
The saved Book Value reference guides this composition; shared money/percentage
formatters and financial tokens remain unchanged. Marketing supporting items
retain their existing outline treatment.
Overview help is limited to three indicators: Book Value, Net Contributions,
and one shared Cumulative P&L/Return indicator after the return pill. The shared
tooltip contains exactly two consolidated formula lines, with no other scope's
formulas or explanatory notes. In every Overview formula tooltip, only the
metric name before the first equals sign is emphasized; the accessible label
retains the formulas as plain text, without extra headings. The trigger adapts
Nova's ghost `icon-xs` button with the preset's Tabler `IconInfoCircle`. The
Bootstrap-owned tooltip uses Nova's foreground/background roles, compact
`px-3`/`py-1.5` spacing, `--radius-md`, and rotated-square arrow; it deliberately
has no extra panel shadow.

Transfer creation fixes the source from the initiating portfolio menu and shows
it in a readonly From Portfolio input. The submitted source ID stays hidden;
the visible name is not submitted. Editing retains both endpoint selectors. Destination
options exclude the selected source; server ownership and cash validation remain
authoritative. Readonly inputs retain Nova's normal input appearance; only
disabled controls receive disabled treatment. AJAX and server-rendered general
errors use one shared form-level Alert treatment immediately below the dialog header, before
fields; inline field errors retain the separate FieldError treatment.

`.tx-preview` is the calculated form-output contract derived from Nova
FieldDescription rather than validation/help styling. It uses text-sm type and
shared field spacing; its label is muted while `.tx-preview__value` uses normal
foreground, medium weight, and tabular numerals. Buy Total Spent and Sell Total
Received share this presentation. The arithmetic result is neutral, never a
positive/negative financial state.

The sidebar search is a shell-owned trigger rather than a form field. It uses
the sidebar background/border/ring/accent roles, Nova input radius, and a single
wrapper focus ring while preserving its command shortcut behavior.

Public and authenticated shells use the same `.icon-button.theme-toggle`
contract, shared Tabler moon/sun symbols, CSS theme-state visibility, and
`shell.js` persistence/accessible-label behavior. Landing does not maintain a
separate decorative theme icon or button variant.

### UI copy

Short interface headings, labels, buttons, menu items, table headers, and
statuses use Title Case in their source strings. CSS capitalization is not part
of the contract. Sentences, explanatory copy, validation text, natural ARIA
descriptions, and user-entered content remain sentence case. Acronyms and
notation such as P&L, ETF and OTP retain their established spelling.

### Accessibility and motion

Focus uses the canonical `--ring` and a visible three-pixel soft ring. Do not
remove focus indication or rely on colour alone. Preserve semantic tables,
heading order, keyboard navigation, touch targets, and live regions.

Use the duration/easing tokens. The global reduced-motion rule owns motion
reduction; component-specific work should not bypass it. Popper-positioned
dropdowns must not animate `transform`.

### Text selection and caret

The generated `b1YmpWHpo` Nova stylesheet does not define a dedicated text
selection or caret recipe. OnePortfolio therefore adds no independent colour
palette: `--selection-background` aliases canonical `--primary`,
`--selection-foreground` aliases `--primary-foreground`, and `--caret-color`
aliases `--foreground`. The single global `::selection` rule covers page copy,
financial values, tables, and editable controls; inputs, textareas, and the
Command input share the same canonical caret. Financial and chart roles are
never valid selection colours. In forced-colours mode, system `Highlight`,
`HighlightText`, and the automatic caret remain authoritative.

### Overview allocation contract

The allocation ring retains current dataset values and switching behavior.
Chart.js reads `--chart-1` through `--chart-5` from computed styles, and the
HTML legend uses the same roles, preserving category mapping, values,
formatting, and theme redraw behavior. Portfolio ledger initials remain
neutral and are intentionally not tied to slice colours.

The current product behavior groups the allocation tail after the first four
portfolios. The grouped remainder uses the fifth allocation-visualization role.
Full portfolio detail remains in the ledger, so presentation grouping does not
change data.

The public Landing preview uses deterministic sample data and outline
`.supporting-item` blocks; authenticated Overview facts are unboxed. Both use
the shared `.allocation-legend`,
`.allocation-legend__row`, swatch, name, value, percentage, financial-number,
and visualization-token contracts. `static/js/display_formatters.js` is the
single browser-side contract for fixed-two-decimal money, signed display, and
percentage precision used by live transaction summaries and both charts. It
mirrors only the necessary display behavior; Python/Jinja filters remain
authoritative for server-rendered financial values. Landing must never query
authenticated data.

Landing-specific CSS owns composition and responsive layout only. It consumes
canonical preset roles directly and does not maintain a decorative colour
system or page-only component palette.

### Third-party widget adaptation

Third-party behavior remains vendor-owned, while appearance is mapped to the
canonical roles. Flatpickr uses popover, foreground, muted, accent, primary,
border, ring, radius, and shadow roles for explicit and system dark modes; its
adapter is deliberately unlayered and loaded after Flatpickr because unlayered
vendor declarations outrank normal declarations inside named cascade layers.
Its date format, values, limits, and lifecycle remain untouched. Month captions
use the preset's abbreviated month treatment. The adapter maps 28px day cells,
8px week gaps, today/selected/outside/disabled states, and sprite chevrons to
Flatpickr. The existing six-week grid and keyboard owner are retained.
Native selects set `color-scheme` per theme and use Canvas/CanvasText options as
the safest platform-compatible dark-popup contract. Native popup geometry
remains browser/OS-owned; a future custom select, if required, must be a shared
progressive enhancement that preserves the native control as authoritative.

### Iconography

The application uses official MIT-licensed Tabler Icons outline geometry from
`@tabler/icons` 3.48.0
(`github.com/tabler/tabler-icons/tree/v3.48.0/icons/outline`): a 24×24
viewport, two-pixel `currentColor`
stroke, and round caps and joins. Geometry lives once in
`templates/components/icon_sprite.html`; `templates/macros/icons.html` is the
only template rendering primitive, and `shell.js` exposes the same sprite-name
contract for dynamic UI. Decorative icons use `aria-hidden="true"` and
`focusable="false"`; a meaningful standalone icon must pass a label, which
adds `role="img"` and `aria-label`. Icons within already named controls
remain decorative. Bootstrap Icons and its font stylesheet are no longer part
of the application.

The OnePortfolio brand mark is a compact monochrome hollow quarter-pie. One
compound path combines the established outer quarter-circle with a smaller
matching interior opening through deterministic `evenodd` fill. The outer
shape retains its straight left and bottom edges, circular arc, and softened
corners; the opening repeats that geometry at a weight that remains legible at
favicon size. The mark has no stroke, letter, financial symbol, gradient,
shadow, or decorative colour. It is a brand asset, not a Tabler interface icon.

`static/icons/favicon.svg` is the sole geometric source of truth. It contains
one two-contour compound path in a 64-by-64 viewBox. The unchanged outer mark
occupies a 48-by-48-unit square; the final enlarged opening occupies 30 by 30
master units, leaving an 8-unit straight band at the left and bottom. The same
hollow geometry is used for the primary application mark and every small-icon
derivative. The generated light and dark SVG favicons are transparent bare-mark
variants, and every 16, 32, and 48px ICO frame is rasterized from the
transparent light favicon. Apple-touch and Android installed-app outputs retain
a separate neutral rounded-square composition because installed-platform icons
cannot promise a suitable runtime surface or theme.
`scripts/generate_app_icons.py` deterministically derives all of these outputs
from the same path without browser automation or a third-party image dependency.
Run the script after editing the master, then run it with
`--validate-only` to verify geometry, transparency, contrast, dimensions,
bounds, manifest references, cross-size consistency, and exact derivative
provenance.

`templates/components/logo_mark.html` remains the only visible-logo component,
and `templates/components/favicon_links.html` remains the only document-icon
link component. The generator derives the visible component's one inline path
from the master SVG and fills it with `currentColor`, so it follows the
canonical foreground in either theme without hand-maintained geometry in page
templates. Its 18px square uses a viewBox cropped to the master mark's bounds,
so the optical mark—not merely an invisible asset canvas—measures 18px. The
shared lockup pairs it with an 18px Geist semibold wordmark and the canonical
`--space-2` gap; Landing, Auth, error, and authenticated surfaces do not restate
those dimensions. The visible application mark is transparent: it has no tile,
background, border, shadow, or padding. SVG favicons and ICO frames follow the
same transparent bare-mark rule. Their light and dark marks use near-black and
near-white respectively, with at least 4.5:1 contrast against the canonical
light and dark surfaces on which they are intended to appear. Only Apple-touch and Android
installed-app compositions may use the neutral rounded-square surface.
Installed icons do not claim dynamic theme switching, and theme-colour metadata
continues to follow the canonical page backgrounds.

Brand artwork must remain monochrome. It must never consume chart colours,
financial semantic colours, or a separate brand hue. Future geometry changes
must edit the master SVG and regenerate all derivatives rather than hand-edit
the light, dark, raster, or ICO outputs.

### Modal and behavior ownership

Bootstrap 5.3.0 owns financial modal focus containment, backdrops, and dismissal,
and dropdown positioning and its existing keyboard behavior. It does not own
the application's validators, AJAX errors, custom command palette, or custom
mobile navigation. Modal trigger restoration also depends on how the modal was
opened; programmatic `.show()` calls do not inherit the data-API trigger's
restoration callback. See the verified ownership register before changing focus.

Phase 4 uses `OnePortfolioDialogs.show(element, optionalOpener)` for programmatic
financial dialogs. It reuses the Bootstrap instance and adds only a one-shot
hidden-event return path; data-API dialogs retain Bootstrap's own callback.
Menu actions return to the visible three-dot trigger. Hidden, disabled or removed
openers are skipped. No Bootstrap private API or trap override is used.

Flatpickr owns dates and selection. Modal calendars append to the owning `.modal`,
outside its scrolling form, with viewport-clamped positions translated to that
container. Page calendars still append to `document.body`. This adapts the
documented [appendTo option](https://flatpickr.js.org/options/) and the positioning
hook in [the installed 4.6.13 source](https://raw.githubusercontent.com/flatpickr/flatpickr/v4.6.13/src/index.ts).
Scrolling the form closes an open picker; scrolling the calendar itself does not.
Escape inside an open picker closes that picker first. The next Escape belongs
to Bootstrap. Modal dismissal still closes its pickers. No second focus loop.

`OnePortfolioOverlays` owns only the custom drawer and command palette. They
share one active slot, background inertness, scroll-lock restoration, Tab
containment, Escape and focus return. A Bootstrap modal's show event releases
that slot before Bootstrap locks scrolling/activates its trap; custom overlays
cannot open during its lifecycle. Mobile navigation resets its semantics and
focus at the same 62rem breakpoint as CSS. Settings tab orientation follows its
56rem composition breakpoint; Bootstrap remains its selection/keyboard owner.

Command uses a named combobox with a controlled listbox, stable option IDs,
active descendant, selected states and a polite result status. Empty feedback
is outside the listbox. Disabled/hidden actions are excluded and activation
ignores IME composition. Arrow selection and Enter remain Command's own handlers.

ActionMenuManager supplies menu/trigger/item associations and removes menu items
from the ordinary Tab sequence. It supplements Bootstrap with Enter/Space entry,
Home/End and typeahead only. Bootstrap retains ArrowUp/Down, Escape, Tab/outside
dismissal, expanded state and viewport-safe Popper positioning. Repeated mounting
does not register duplicate handlers.

Keep one focus owner per overlay and one submission owner per form. Global
tooltips are mounted only by `TooltipManager`; pages must not mount duplicates.

### Validation interaction contract (Phase 2)

- Before final submit, opening, prefilling, focusing, blurring, and changing a
  field must not reveal validation errors. After a failed final submit, supported
  client validation updates while correcting input.
- Server-only business validation stays authoritative. Changing a field may
  clear its stale server error; it does not establish server acceptance.
- Fresh dialog sessions reset validation state; failed server-rendered POSTs
  retain submitted values and errors. General errors appear at the top of the
  dialog body, below its header; field errors stay beside their fields.
- Use form-level native-validation suppression where needed. Retain meaningful
  `required`, labels, help associations, and required-field accessibility
  semantics; do not strip them globally. Associate errors with stable IDs and
  `aria-describedby`, and maintain `aria-invalid` with the actual error state.
- Verification-code auto-submit after six digits is the approved exception.
  CSRF, mutation tokens, authentication protections, and server validation remain
  unchanged. Auxiliary actions such as Max use action-level feedback without
  marking untouched fields invalid.
- Coordinate error focus with the existing overlay owner; no second focus trap.

`static/js/form_feedback.js` owns one controller per form, accessible field and
general feedback, submit gating, and session reset. It loads before `main.js`
and also loads in the authentication shell. `FormValidatorsInitializer` supplies
the existing financial input rules; `ModalAjaxHandler` alone sends financial
form POSTs and owns loading. Account forms retain normal server POSTs. The
feedback module does not send requests. Jinja's `macros/forms.html` renders the
same stable error IDs, alert roles, and associations used by the controller.

Programmatic record openers call `OnePortfolioForms.prepare(modalId)` before
prefilling, including when an already-open dialog changes records. The controller
resets on fresh show, hidden, and native form reset. Initial failed-POST feedback
is preserved through prefill and focused only after Bootstrap's `shown` event.
Existing help IDs survive error clearing. Visible proxy controls can declare
`data-feedback-for` for a hidden logical field; inaccessible or unknown server
errors go to the general summary. Validation alerts are not auto-dismissed.

Correction feedback runs after existing input normalization. Pending AJAX
submissions cannot be duplicated; failures from an earlier dialog session do
not paint errors or move focus. Successful mutations still reload authoritative
data even if their dialog has closed. Max errors use general feedback without
starting field validation. These changes preserve server rules, request tokens,
financial calculations, formatting, and overlay containment ownership.

Phase 2 re-inspected the canonical Nova Field and Alert source recipes on
**2026-10-12** for feedback semantics. The user approved Phase 2, including
visual acceptance. Phases 3 and 4 aligned component recipes and interactions
without changing feedback behavior; both have user visual acceptance.

### Phase 2 error classification and lifetime

Classify at the source of the failure, never by matching message text:

- Input validators attach required, format, range, and length failures to the
  responsible field. Only that field receives `aria-invalid` and its error ID.
- Service/account/history failures use `errors.__all__`. Cash shortages,
  overselling, fees exceeding proceeds, historical cash violations, unavailable
  records, duplicate names, stale submissions, conflicts, and unexpected save
  failures are form-level, even if changing an amount might resolve them.
- Authentication format failures are field-level. Opaque invalid/expired OTP
  results and email/account-state failures are general; do not split security
  messages to infer whether a code, account, or challenge exists.

`form_error_response` is the shared service-failure adapter. The old message-to-
field maps are removed. Preserve meaningful messages and existing safe generic
messages for unexpected exceptions. Do not change server acceptance, ownership,
CSRF, replay protection, or financial rules to simplify presentation.

General server errors persist while correcting fields, when local validation
blocks a retry, and while a request is pending. Only an authoritative response
or a session reset replaces them. Auxiliary-action and network feedback have
separate source entries in the same region, so Max cannot erase a financial
failure. Summaries deduplicate messages, and inaccessible field feedback is
moved to the summary rather than displayed twice. Repeated focus must not
duplicate its content. Field correction still follows the final-submit gate;
six-digit OTP auto-submit remains the sole approved exception.

## Avoid

- raw colour literals outside `tokens.css`, except documented encoded assets;
- invented chart roles or categorical portfolio colours;
- financial colours used as generic UI status or decoration;
- gradients, glows, and ornamental elevation;
- page-specific radii where a canonical radius role exists;
- compatibility aliases or component code that bypasses canonical roles;
- `!important` in application layers unless an existing vendor/runtime
  constraint is documented;
- inline styles except data-driven custom-property values;
- changes to formatting precision in presentation work.
