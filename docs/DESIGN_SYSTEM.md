# Design System

OnePortfolio's interface is a **quiet ledger**: a dense record-keeping tool where
the numbers are the interface and everything else recedes. It supports light and
dark themes, and a compact density mode.

## Governing rules

Three rules decide most design questions. When in doubt, apply them in order.

1. **Colour means something.** Green, red, and blue are reserved for signed
   financial values (`positive` / `negative` / `income`). The brand violet
   appears in exactly two roles: the primary button, and the active navigation
   marker. Everything else is neutral.
2. **One hero number per screen.** A screen with five equally-weighted figures
   has no reading order. Promote one; demote the rest to supporting facts.
3. **Density is a preference, not a constant.** Never hard-code a compact size —
   scale it from `--density-scale` so the comfortable/compact switch works.

Three consequences worth stating outright, because they are easy to undo by
accident:

- **Entry types are coloured words, not chips.** Buy, Sell, Income, Deposit and
  Withdraw appear once per row; wrapping each in a tinted pill turns a ledger
  into a field of badges and out-shouts the figures. A chip is still right for a
  *category* tag that appears once per group (the portfolio name beside an asset
  symbol).
- **Row actions appear on engagement.** Edit/delete controls are `opacity: 0`
  until their own row is hovered or focused. They keep their layout space, stay
  in the tab order, and are permanently visible under `@media (hover: none)`.
- **The allocation ring shows four slices plus a grouped remainder.** Past four
  wedges the small ones become unlabelable slivers. Full per-portfolio detail
  lives in the summary table directly below, so nothing is hidden — only
  simplified. The cap is `ALLOCATION_TOP_N` in
  `calculators/allocation_charts.py`.

## File layout

```
static/css/
  tokens.css      layers + design tokens (loaded first, always)
  base.css        reset, element defaults, typography, focus, motion primitives
  components.css  reusable UI: buttons, forms, tables, modals, toasts, …
  app.css         the authenticated product: shell + per-page layout
  landing.css     the marketing page (loaded instead of app.css)
```

Templates load `tokens → base → components → app` (or `landing`). **`tokens.css`
must stay first**: it declares the cascade layer order and imports Bootstrap.

## Cascade layers

```css
@layer vendor, tokens, base, components, pages, utilities;
@import url("…bootstrap.min.css") layer(vendor);
```

Bootstrap is imported *into* the `vendor` layer, which places every rule we write
above it without a single `!important`. Write new rules inside the layer that
matches the file, and specificity stops being a fight.

**The one exception:** `!important` declarations reverse layer order, so
Bootstrap's utilities (`.text-muted`, `.d-none`, `.mb-3`, …) still win over our
layered rules. That is deliberate — utilities should win. When one of those
utilities needs to change colour, drive it through its `--bs-*` variable in the
bridge at the bottom of `tokens.css` rather than trying to out-cascade it.

## Tokens

Three layers, and components may only consume the middle one:

| Layer | Example | Use |
|---|---|---|
| Primitives | `--n-900`, `--brand-500`, `--green-dark` | never referenced by components |
| Roles | `--bg-surface`, `--fg-muted`, `--pos`, `--line-subtle` | **the only thing components use** |
| Bridge | `--bs-primary-rgb`, `--bs-card-bg` | maps roles onto Bootstrap |

Adding a colour means adding a *role*, not a one-off hex. If no existing role
fits, the design probably needs a new semantic — not a new shade.

### Themes

The light theme is built on a **warm cream** ramp, not neutral white. That is a
functional choice, not a stylistic one: against a warm ground the semantic green
and red hold their saturation, where on clinical white they wash out and start
reading as grey. The light-theme semantic hues are darkened to clear 4.5:1
against those cream surfaces; the dark-theme brand steps are pushed up in chroma
because a desaturated violet reads as grey on near-black.

Light is the base definition on `:root`. Dark is redefined twice: under
`@media (prefers-color-scheme: dark)` guarded by `:root:not([data-theme="light"])`,
and again under `:root[data-theme="dark"]` so an explicit choice wins in both
directions. A theme preference is applied by an inline script in `<head>` before
first paint, so the page never flashes the wrong palette.

**Canvas content does not follow CSS variables.** Anything drawn into a
`<canvas>` bakes in the palette it was created with. Chart owners listen for the
`op:themechange` event on `window` and redraw.

## Typography

`Inter`, with `font-variant-numeric: tabular-nums` set once on `body` — that
single declaration is why every figure in the product aligns in a column.

Numbers have their own scale (`--num-sm` … `--num-hero`) independent of the prose
scale (`--text-2xs` … `--text-3xl`), so figures can be tuned without dragging
body copy along.

Labels are **sentence case**. No `text-transform: uppercase`; at 11px with wide
tracking it reads worse and looks templated.

Maximum font weight is `600`.

## Elevation, radius, motion

- Two shadows only: `--shadow-raised` (cards) and `--shadow-overlay` (modals,
  dropdowns, toasts). Never decorative.
- Three radii with distinct jobs: `--radius-sm` controls, `--radius-md` cards,
  `--radius-lg` modals.
- Motion uses `--dur-1` … `--dur-4` and `--ease-out` / `--ease-spring`. Nothing
  animates on a hand-written duration.
- Every animation degrades through the single global
  `@media (prefers-reduced-motion: reduce)` block in `base.css`. Do not write
  per-component reduced-motion guards.

## Numbers in templates

Every figure goes through the macros in `templates/macros/ui.html`:

```jinja
{% from 'macros/ui.html' import money, percent, quantity, metric, fact %}

{{ money(item.realized_pnl, tone='sign', signed=true) }}
{{ percent(item.return_percent, item.return_display) }}
```

`tone` is `plain` (default), `sign` (green/red/muted), or `income` (blue). The
macros own the display/exact-value split (compact text, full value in `title`),
so a change to how money is rendered is a one-file change.

Do not hand-write the `{% if x > 0 %}profit{% elif … %}` conditional in a
template. That pattern is what the macros exist to delete.

## Page anatomy

`base.html` provides the shell and four blocks: `page_title`, `page_subtitle`,
`page_actions`, `content`. There is no top bar — the page header inside the
content column carries the title and its actions.

Two layout primitives cover the product:

- **`.ledger`** — a summary table of peers (the overview's portfolio list). It
  restacks below 60rem, re-attaching column names from each cell's `data-label`.
- **`.disclosure`** — a summary row that opens onto its records (portfolios and
  assets). The whole summary is one `<button aria-expanded>`, so it is
  keyboard-reachable and announces its own state; row actions sit *outside* that
  button or they would be unclickable.

Because the summary lives inside a `<button>`, its contents must be phrasing
content — which is why the `metric` macro emits spans rather than divs.

## Command palette

`Ctrl/Cmd+K`. It reads static navigation entries from a JSON script tag in
`base.html`, plus **any element on the page carrying `data-command="Label"`**
(optionally `data-command-group` and `data-command-icon`). A page extends the
palette by adding one attribute — there is no registration step.

## Avoid

- Decorative gradients, glows, and ornamental shadows. The single permitted
  gradient is the hero aura on the marketing page.
- New one-off surface colours, radii, or durations.
- `!important` in our own layers.
- Uppercase labels.
- Inline `style` attributes, except to pass a numeric custom property
  (`--enter-index`, `--metric-columns`) that is genuinely data-driven.
