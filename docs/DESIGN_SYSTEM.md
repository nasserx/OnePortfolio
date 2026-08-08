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
   Those two roles need *different* violets in dark mode — see
   [`--brand` vs `--brand-solid`](#brand-vs-brand-solid).
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
- **Figures are right-aligned wherever a column repeats.** Tables and the
  disclosure metric strips both read vertically, card against card, so the
  decimal points must stack. Left-aligned numbers let them wander by tens of
  pixels. The overview hero's supporting facts are the exception and stay
  left-aligned: each is a label/value *pair*, not a column, and right-aligning
  a value across a half-card-wide cell would strand it away from its own label.
- **A column heading and its data must be the same column, structurally.**
  Alignment is not a `text-align` question. If a header row and its body rows
  are separate grid containers, each resolves its own track sizes and any
  content-sized column (an action link vs an empty "Actions" label) knocks
  every heading out of step with the figures beneath it. `.ledger` declares its
  tracks once and every row adopts them with `grid-template-columns: subgrid`.
  Real `<table>`s get this for free — which is why they are still the right
  tool for the record lists.
- **Validation changes colour and nothing else.** Bootstrap's invalid state
  also injects an icon and widens the right padding, which resizes the field
  and makes an error read as a different component. Both are reset.
- **Every field state is the same mechanism.** A 1px hairline at rest, which
  doubles to a crisp 2px edge when the field is focused or focused-and-wrong.
  The doubling is an `inset` shadow so it lands *on* the border rather than
  blooming outside it — no halo, no glow, and the field never changes size.
  An unfocused invalid field keeps the hairline weight and switches hue plus
  a faint wash: a fully saturated red line beside a 14%-alpha neutral one
  reads as a different weight class, which is what made errors look like a
  stray wire rather than the same control in another state.
- **One focus indicator, never two.** The crisp `outline` from `base.css` is
  it. Stacking a translucent ring behind an outline only produces the glow
  this system is trying not to have.

## File layout

```
static/img/
  hero.avif       hero backdrop, primary
  hero.webp       hero backdrop, fallback for engines without AVIF

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

### `--brand` vs `--brand-solid`

The brand has two roles because one violet cannot do both jobs in dark mode:

| Role | Used for | Constraint |
|---|---|---|
| `--brand` | brand-coloured **text**, icons, hairlines, the nav marker | ≥ 4.5:1 *as* text on a dark surface → must be light |
| `--brand-solid` | any **filled** block with a label on it: primary button, checked box, selected calendar day | must carry white text at ≥ 4.5:1 → must be dark |

In the light theme they coincide. In dark they are three ramp steps apart, and
the gap is not stylistic: the usable band for a white-labelled violet on this
palette is a relative luminance of roughly 0.14–0.18, and `--brand` sits well
above it. Reaching for `--brand` as a fill is the mistake this split exists to
prevent — `tests/test_design_tokens_contrast.py` fails the build if it happens.

**Hover must move away from the label, not toward it.** The semantic solid
buttons (success / danger / warning) hover by painting `--solid-hover-veil`
over their fill: black in light, where labels are white; white in dark, where
labels are near-black. A single white wash for both themes looked fine and
quietly dropped light-mode Success to 4.31:1 *on hover only* — the state where
the user is committing to the click. `.btn-primary` is excluded from that rule
because it has a real hover step of its own; stacking the two dropped it to
3.77:1. The test composites the veil, so it checks the shipped colour rather
than the resting one.

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

Two steps below the body scale carry specific jobs:

- `--text-detail` — record rows revealed inside a disclosure, and nothing
  else. A page's own primary table stays at `--text-sm`.
- `--text-2xs` — field help text (`.form-text`, the inline hints, the cost
  preview, the notes counter). Guidance *about* a control is the quietest
  thing in a form. Error messages are deliberately excluded: they are the one
  piece of small text a user is required to read.

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

**Never set the `transition` shorthand on an element that also has hover
choreography.** The marketing page's scroll reveal originally did, and silently
replaced each card's own `border-color` / `box-shadow` / `transform`
transitions with its own. Entrances use `animation` for exactly this reason —
and with `animation-fill-mode: backwards`, not `forwards`, so the final
keyframe does not outrank a later hover transform and leave the element inert.

Contrast is enforced by `tests/test_design_tokens_contrast.py`, which parses
`tokens.css` directly. A palette tweak that drops any text role below its floor
fails the suite rather than shipping.

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

The overview hero is stretched to the height of the chart panel beside it, so
it always has slack to place. That slack goes **into** the supporting facts —
they claim the leftover height and spread through it as a 2×2 grid — rather
than being pinned somewhere as empty space. Anchoring the facts to the bottom
instead just relocates the gap under the headline, and centring the whole group
puts a dead band above the card's own title.

The two halves of that row are **equal**, not a panel and a sidecar. Given
half the width the split chart puts its legend beside the ring instead of
under it, which converts width into ring diameter rather than into blank
space. The centre label is sized from `arc.innerRadius`, so it stays in
proportion when the ring grows.

Two spacing rules for the disclosure summary row, both about ownership of a
number: the identity column is fixed (so every card's metric strip starts at
the same x) but sized to the names rather than to the longest name
imaginable, and the strip stops short of the action cluster. Run it to the
full width and the last figure's right edge sits under the edit/delete
buttons, which makes the figures read as labels for the controls.

Because the summary lives inside a `<button>`, its contents must be phrasing
content — which is why the `metric` macro emits spans rather than divs.

## Hero backdrops

The marketing hero and the auth showcase share one photographic backdrop:
`components/hero_image.html` inside a `.hero-media` wrapper.

**Format negotiation.** AVIF is offered through a `<source>`; the `<img>`
`src` is the WebP. A browser that cannot decode AVIF skips the source and
uses the img — the one mechanism every engine implements, including ones too
old to understand `image-set()` type hints. Do not replace this with a CSS
`background-image` unless the fallback stops mattering.

**The scrim is not decoration.** The colour behind a word is whatever the
photograph happens to be doing there, and the photograph can be swapped. So
every hero pairs the picture with `--hero-scrim-*`, and three rules hold:

1. **Copy sits on `--hero-scrim-strong`, always.** That step is tuned to the
   loosest value that still clears 4.5:1 for `--fg-muted` against a *worst
   case* pixel — pure black in light, pure white in dark. Solving for it
   gives 0.812 light and 0.776 dark; the shipped values sit just above, with
   a small margin for antialiasing. There is no room below that without
   gambling on the particular photograph, so if a hero needs to be clearer,
   open up `soft` and `edge` or move the copy — do not lower `strong`.
   `tests/test_design_tokens_contrast.py` enforces it.
2. **`soft` and `edge` are for regions with no text in them.** They exist so
   the picture can actually be seen where nothing is written over it. If a
   layout change moves copy into one of those bands, the band moves, not the
   copy.
   The same idea vertically: `--hero-scrim-mask` fades the copy scrim off
   across the strip below the last line of text. That strip is where the
   photograph's foreground detail actually survives. Without a mask there is
   no way to open the picture up *underneath* a text column, because a
   gradient cannot vary on both axes at once.
3. **Chrome that floats on a hero uses `--hero-scrim-band`.** A short veil
   down the top, which stacks with whatever the copy scrim is doing there —
   near `edge` in the top corner, so the combination lands around 0.70.
   That is enough for `--fg-default` and nothing quieter, which is why the
   marketing header's bare controls switch to the default step while the
   header is transparent.
4. **Nothing below `--fg-muted` is a text colour over a hero.** Through the
   scrim `--fg-subtle` reaches only ~4.06:1 and `--fg-faint` misses even the
   non-text floor. Small print over imagery is where legibility quietly
   fails, so the marketing proof list and the auth sub-paragraph step up.

**Three bands, and one sum.** A full-bleed hero is read vertically as:

| band | extent | job |
| --- | --- | --- |
| copy | top → `100% − floor − fade` | scrim at full strength, protecting the words |
| floor | `--hero-floor` | scrim lifted, picture at full clarity |
| fade | `--hero-fade` | picture dissolving into the page |

The hero's `padding-bottom` is `calc(floor + fade)`, so the last line of copy
always lands exactly on the top of the floor. That single expression is the
guarantee: change any one of the three and the other two follow, and no
resize can slide a dissolve underneath a word. The two masks *meet* at the
floor/fade line rather than overlapping — a scrim still fading while the
picture beneath it fades too leaves a pale ghost of itself with nothing left
to protect.

**How a hero meets the page.** The picture dissolves; it is not painted over.
Fading it with a wedge of `--bg-canvas` lightens the image on its way out — a
milky band in light mode, a smear of black in dark — because a wash *changes*
a colour in order to hide it. A mask only removes, so the page shows through
cleanly and one rule covers both themes.

Two things make a dissolve stop reading as an edge, and both are needed:

- **Length.** The eye finds the start of a short fade as readily as the cut it
  replaced. The hero grows by exactly `--hero-fade` to pay for this; that
  height is the cost of ending without a seam, not padding to be reclaimed.
- **Curvature.** A linear ramp has a corner in its *rate of change* at each
  end, and a corner is visible as a line even when the change itself is
  gentle. `--hero-media-mask` traces a smoothstep in seven stops instead.

**Gradient or flat?** Use a directional scrim only where the copy's position
is fixed by the layout — the marketing hero keeps its copy in the left half,
so `strong` holds to 50% and eases off after. The auth showcase centres its
copy vertically, so its position within the panel moves with viewport
height; it takes a flat scrim, because a falloff there would only be correct
at the height it was eyeballed on.

**Loading.** The marketing hero is eager and high priority. The auth
showcase is `lazy`/`auto`, because that panel is hidden below 60rem and a
lazily loaded image inside a hidden container is never fetched — a phone
signing in does not pay ~200KB for a backdrop it cannot see.

**The marketing header floats on the picture.** `.lp-nav` is `fixed`, not
`sticky`: sticky keeps the header in flow, which pushes the hero down by the
header's own height and puts a band of flat page colour above the
photograph. At rest the header is nothing but its contents; the frosted
panel and hairline only appear once `landing.js` adds `.is-stuck`, when the
header is genuinely floating over content it needs separating from.

Two things follow from that, and both are easy to lose:

- The header is out of flow, so `:root { scroll-padding-top }` (set in
  `landing.css`, which only that page loads) is what keeps in-page anchors
  from scrolling their target underneath it.
- While the header is transparent its two secondary controls are too — only
  the primary call to action keeps a fill. What pays for that is
  `--hero-scrim-band`, not a panel. It also forces a colour change: those
  controls normally sit at `--fg-muted`, which needs 0.81 and would not
  survive out at the open edge of the scrim, so they take `--fg-default`
  instead. Anything else added to that end of the header needs the same
  treatment, and `test_hero_chrome_is_legible_where_the_scrim_is_most_open`
  is what stops the band and the edge drifting apart.

## Command palette

`Ctrl/Cmd+K`. It reads static navigation entries from a JSON script tag in
`base.html`, plus **any element on the page carrying `data-command="Label"`**
(optionally `data-command-group` and `data-command-icon`). A page extends the
palette by adding one attribute — there is no registration step.

## Avoid

- Decorative gradients, glows, and ornamental shadows. The only gradients in
  the product are the hero scrims (see [Hero backdrops](#hero-backdrops)),
  and they are functional — they exist to make text readable, not to decorate.
- New one-off surface colours, radii, or durations.
- `!important` in our own layers.
- Uppercase labels.
- Inline `style` attributes, except to pass a numeric custom property
  (`--enter-index`, `--metric-columns`) that is genuinely data-driven.
