# OnePortfolio design system

OnePortfolio keeps its Flask/Jinja structure, financial workflows, and compact
ledger character. Its visual source of truth is the official shadcn preset
`b1YmpWHpo`: Nova style, neutral base and theme, blue charts, Tabler icons,
Geist typography, a `0.625rem` radius, subtle menu accent, and default menu
colour.

This document separates four contracts. They must not be blended into a
second, application-specific brand palette.

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

The official chart roles remain immutable preset truth. OnePortfolio adds a
separate visualization-only categorical contract for the allocation chart:

| Role | Light | Dark |
|---|---|---|
| `--portfolio-chart-1` | `var(--chart-3)` | `var(--chart-2)` |
| `--portfolio-chart-2` | `oklch(0.58 0.12 210)` | `oklch(0.72 0.12 210)` |
| `--portfolio-chart-3` | `oklch(0.55 0.16 300)` | `oklch(0.70 0.14 300)` |
| `--portfolio-chart-4` | `oklch(0.56 0.12 165)` | `oklch(0.70 0.12 165)` |
| `--portfolio-chart-5` | `oklch(0.64 0.14 70)` | `oklch(0.76 0.13 75)` |

This restrained blue, cyan, violet, teal, and single amber palette is a
OnePortfolio extension, not part of `b1YmpWHpo`. It is allowed only in Chart.js
datasets and their corresponding legend swatches. Neither official chart roles
nor the extension may style portfolio initials, avatars, buttons, navigation,
generic badges, or entity UI. There is no `--chart-6`, `--chart-7`, or
`--chart-other`; the existing top-four-plus-Other behavior uses five slots.

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

The only application colour extensions are:

- `--financial-positive`
- `--financial-negative`
- `--financial-income`
- `--financial-flat`

They are permitted only when colour communicates real financial meaning:
signed returns, realized profit/loss, signed income, financial delta
indicators, financial record-type text, and the currently selected Buy/Sell
transaction direction. Record types use the shared `record_type` Jinja macro:
Buy and Deposit are positive, Sell and Withdrawal are negative, Income uses
the income role, and Initial or unknown types remain neutral.
Explicit signs, values, and selector labels remain the primary cue; colour is
never the only cue.

They are forbidden on portfolio markers, ordinary buttons, navigation,
generic badges, chart categories, generic notifications, and decorative
surfaces. The selected transaction-direction control is the sole workflow
exception. `--destructive` remains distinct from `--financial-negative`, even
where their appearance is close.

## C. Compatibility boundary

OnePortfolio component and page styles consume the canonical preset roles
directly. Names such as `--bg-canvas`, `--fg-default`, `--line-default`, and
`--brand-solid` are not part of the current design-system API.

The `--bs-*` declarations at the bottom of `tokens.css` are the only controlled
compatibility bridge. They are vendor inputs, not OnePortfolio component API.
Bootstrap remains in the `vendor` layer for modal, dropdown, Popper, validation,
and utility behavior; semantic CSS owns the final appearance.

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
public shells load only the 400, 500, and 600 weights from the existing Google
Fonts origins. Components and Chart.js consume the tokens rather than naming a
face independently. Body text is compact and readable, headings use the heading
token, and financial columns preserve tabular numbers through the shared root
feature settings.

Numeric typography is separate from display precision. Changing a font size or
weight must never alter financial rendering rules.

### Numbers in templates

All figures go through the existing macros in `templates/macros/ui.html`.
Authoritative behavior remains:

- money: fixed two decimals by default;
- quantity: variable precision with trailing zeros removed;
- percentage: two decimals by default;
- price: per-asset precision;
- average cost: at least two decimals or price precision;
- fees: trailing zeros removed;
- realized profit/loss: explicit sign plus financial semantic role;
- income: financial income role;
- undefined: em dash.

Internal Decimal precision and display precision remain separate. Do not
reproduce sign/format conditionals in individual templates.

### Layout and fixed geometry

Keep one hero number per screen and demote supporting figures. Comparative
numeric columns are right-aligned with tabular numbers. The application has one
fixed compact/readable geometry: two-rem controls, 2.5rem financial rows,
0.5rem vertical cell padding, and the canonical card/page spacing tokens.
There is no density preference, alternate token scale, or `data-density`
rendering mode.

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
- `.surface-dialog`: popover roles, `--radius-xl`, dialog shadow, and one
  hairline ring. Bootstrap modals and the command palette consume it.

Overview hero, allocation card, ledger, disclosure cards, authentication
forms, the Landing product preview, and empty states compose these contracts. Their page selectors must
not restate outer borders, radii, backgrounds, or elevation. A responsive table
may replace its frame with per-row cards when the semantic table is deliberately
restacked; that is a structural exception, not a second desktop surface recipe.

#### Standalone and compound inputs

`.form-control` and `.form-select` are standalone fields and own their complete
input edge and focus recipe. The command palette instead uses the authoritative
`.command-input-group` / `.command-input-control` composition based on Nova
CommandInput geometry: it rests flat and transparent on the popover with no
border, outline, ring, or shadow. Focus uses only an `--accent` background plus
stronger icon, text, and placeholder emphasis; the native input remains
edge-free. Forced-colors mode may supply the operating system outline. This is
not a generic input variant and must not be applied to normal fields or the
sidebar Search trigger.

#### Transaction direction

`.tx-type-tabs` and `.tx-type-tab` form the reusable neutral segmented contract
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
notation such as P&L, ETF, OTP, and ROI retain their established spelling.

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
Chart.js reads `--portfolio-chart-1` through `--portfolio-chart-5` from computed
styles. The HTML legend uses the same roles. The official `--chart-*` values
remain unchanged as preset reference roles. Portfolio ledger initials remain
neutral and are intentionally not tied to slice colours.

The current product behavior groups the allocation tail after the first four
portfolios. The grouped remainder uses the fifth allocation-visualization role.
Full portfolio detail remains in the ledger, so presentation grouping does not
change data.

The public Landing preview uses deterministic sample data but shares the
authenticated Overview's `.supporting-item`, `.allocation-legend`,
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
Its locale, values, limits, and lifecycle remain untouched. Native selects set
`color-scheme` per theme and explicitly style option foreground/background as
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

Bootstrap continues to own modal focus lifecycle, backdrop behavior, reopening,
dropdown positioning, and validation hooks. Shared CSS changes surfaces and
spacing only. Global tooltip management and command-palette behavior remain in
their existing JavaScript owners; pages must not mount duplicates.

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
