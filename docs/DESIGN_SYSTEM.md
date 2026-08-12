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

   **A button is not a value, so a button does not get a value's colour.**
   Every action in the product is `.btn-primary` — deposit, withdraw, buy,
   sell, record income, save, create. The single exception is destruction:
   `.btn-danger` and `.btn-outline-danger`, where red is a warning rather
   than a quantity. There is deliberately no `.btn-success` and no
   `.btn-warning` to reach for. A green *Record Deposit* button beside a red
   *Record Withdraw* button read as a gain and a loss, which is what neither
   of them is: both are entries the user chose to make, and the sign belongs
   to the figure they produce, not to the control that produced it.

   Violet is therefore what an action looks like, filled or not: the primary
   button, the active nav marker, and `.btn-icon` — the row actions, which
   take the brand colour on no surface at all. The tint is what makes a line
   of small glyphs read as controls rather than as decoration beside the
   figures, and `--brand` clears 4.5:1 on every surface, so it can carry
   that with no fill and no border behind it.

   **Hover is the one place a control may borrow a value's colour, because
   there it means something different.** A resting colour claims "this
   control is of that kind"; a hover colour says "this is what will happen
   if you press it" — and only the second is true of a deposit. So
   `.btn-icon--pos`, `--neg` and `--income` tint on hover only, in the exact
   roles the resulting figures will be printed in: a deposit adds, a
   withdrawal subtracts, income is income. Destruction keeps its warning on
   `.btn-outline-danger`, since it is previewing loss rather than an entry.
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
  In a row of them, **only the destructive one carries a colour** — the rest
  are neutral and say what they do with their icon and their tooltip. Note
  that `.btn-icon` sets its own colour at rest *and* on hover, so an outline
  variant on one shows through only where `components.css` restores it
  explicitly; there is one such rule, and it is for `.btn-outline-danger`.
- **A number must never sit next to a control.** Where a table ends in an
  action column, that column is a fixed track wider than its content, so the
  surplus becomes a gutter between the data and the things that act on it.
  Sized to `auto` it collapses onto the last figure, and a value one 12px gap
  from a button reads as belonging to it.
- **Two tables stacked in one card share their edges, not their columns.**
  A disclosure's summary row and the record table inside it hold different
  things and can never align column-for-column. What they can align is where
  their data stops and where their controls start: `--row-actions-w` is that
  right-hand zone, declared once on `.disclosure` and consumed by both. The
  panel is also inset by `--space-4 − --cell-pad-x`, because a row pads
  itself at the edges while a table pads inside each cell — miss that and
  both rows sit 16px out of true down their whole length.
- **The allocation ring shows four slices plus a grouped remainder.** Past four
  wedges the small ones become unlabelable slivers. Full per-portfolio detail
  lives in the summary table directly below, so nothing is hidden — only
  simplified. The cap is `ALLOCATION_TOP_N` in
  `calculators/allocation_charts.py`.
- **Figures are right-aligned wherever a column of them is meant to be
  compared.** That is the full ledger on the Overview: it reads vertically,
  row against row, so the decimal points must stack. Left-aligned numbers let
  them wander by tens of pixels.
  Where the unit being read is a label/value *pair* rather than a column, it
  centres instead — the disclosure summary strips — or stays left, as in the
  overview hero's supporting facts. The test is what the reader is comparing:
  a figure against the figure above it, or a figure against its own label.
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

`app.css` and `landing.css` are alternatives, never both — which makes
`components.css` the only file a class used on both sides may live in. A
component written into `app.css` and then used in the marketing page's product
card renders as *unstyled markup*: no error, no missing file, no failing test,
just an element quietly wearing none of its own rules. `.delta` did this for
several redesigns and read as plain dark text where the product shows a green
pill. **If a page outside the app shell uses a class, that class belongs in
`components.css`.**

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

**Which is exactly why a utility must never be stapled to an element a
component already styles.** It does not merge with the component's decision;
it silently outranks it, and nothing in the stylesheet shows that it
happened. If a component gets the wrong colour, change the component.

The tell that this has been happening is an `!important` in one of *our*
layers, because that is the only way to win the argument back. Three had
accumulated — `.table .text-muted`, `.records-table tbody td small.text-muted`,
and `.sell-max-btn`'s padding fighting `p-0` — and every one was removed by
taking the utility off the element rather than by escalating. What is left is three legitimate uses:
`.visually-hidden`, the reduced-motion block, and `.sym-filter-hide`, which
has to beat whatever `display` the element it lands on already has.

**Bootstrap's reboot is a source of behaviour, not just of looks.** It sets
`scroll-behavior: smooth` on the root, which on the root scroller animates
*every* programmatic scroll — `scrollTo(0, 0)` takes about a second, and the
browser's own scroll restoration after a reload (which this app does after
every modal action) becomes a page that sits still and then glides on its
own. `base.css` overrides it to `auto`; deleting our declaration is not
enough, because then the vendor layer simply wins. The marketing page opts
back in from `landing.css`, where it is wanted for jump links and where the
`pages` layer outranks `base`.

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

**An entrance may decide when content appears, never whether.** The scroll
reveal is the only place in the product where CSS hides real content and
JavaScript brings it back, and both halves of that arrangement have failed
here at least once:

- *The trigger was too strict.* `threshold: 0.12` with a negative bottom
  `rootMargin` meant an element had to push an eighth of itself past a line
  above the fold before it was allowed to exist. A block resting at the fold
  on load was visible space with nothing in it, and at some window heights a
  section never appeared at all. It is `threshold: 0` now: any pixel counts.
  A reveal is decoration and gets the loosest trigger there is.
- *The hiding rule was unconditional.* `[data-reveal] { opacity: 0 }` applies
  whether or not the script that removes it ever runs, so one thrown error or
  one blocked CDN blanked the whole page below the hero — invisibly, since
  the markup and the layout are both perfectly correct. The rule is now
  scoped to `:root[data-reveal-ready]`, set inline in the head before first
  paint and taken back off at `load` if `shell.js` never stamped
  `data-reveal-mounted`.

Scoping a hiding rule is a specificity trap, and it is worth knowing before
you repeat it: `:root[data-reveal-ready] [data-reveal]` is 0,3,0 and
`[data-reveal].is-revealed` is 0,2,0, so guarding only the hiding rule wins
the cascade and hides the page permanently — the observer still fires and the
class still lands. **Every rule in the block carries the guard, including the
ones that un-hide.**

**Charts are the one place a long duration is right.** The allocation ring
draws itself once, when a page of numbers first appears, and it takes 1150ms
on `easeInOutQuart` — slow enough to be watched, and eased at *both* ends so
the sweep reads as deliberate rather than as dragging to a halt. Ease-out
alone at that length looks sluggish; ease-in-out spends its speed in the
middle, where it is not perceived as waiting. Everything the reader triggers
afterwards answers on its own short transition (`legendToggle`, 300ms):
replaying an entrance on every legend click puts their input behind an
animation they have already seen.

Contrast is enforced by `tests/test_design_tokens_contrast.py`, which parses
`tokens.css` directly. A palette tweak that drops any text role below its floor
fails the suite rather than shipping.

**The quiet text step sits the same distance above the floor in both themes.**
`--fg-subtle` is what field help, character counters and column headings use,
and it is deliberately close to 4.5:1 — 4.65 light, 4.73 dark. It cannot go
lighter; that *is* the lightest readable step, and anything quieter belongs to
`--fg-faint`, which is for text nobody has to read.

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

**The shade is measured, not chosen.** The colour behind a word is whatever
the photograph happens to be doing there, so legibility over a hero is a
question about the *file*, not about a pair of tokens. That is exactly how it
is answered: `tests/test_hero_legibility.py` opens the shipped WebP, samples
every region a text column can land over, and solves for the lightest veil
under which `--fg-default` still holds 4.5:1 against the darkest and
brightest pixels it finds.

This is the decision the whole hero rests on. A scrim sized for a
*hypothetical* photograph has to assume pure black under dark-theme text and
pure white under light-theme text, and no real photograph is ever both —
sizing it against the actual picture takes roughly 0.3 off the required
alpha, which is the difference between a backdrop and a wash. The cost is
that the guarantee now belongs to this picture: swap it and the test
recomputes, and a darker one will demand more.

**One shade, one strength, everywhere.** No falloff in either direction, and
no band under the header. Uniformity is the second decision the hero rests
on, and it took three attempts to reach: every version that varied the veil
to buy clarity where nothing was written read as a *stain*. The eye has no
trouble seeing that one part of a photograph is hazier than the rest, and it
looks like a rendering fault rather than a design. A picture 12% less visible
everywhere reads as a picture.

Four rules follow, and the tests enforce all of them:

1. **Copy sits on `--hero-shade`** — 0.50 light, 0.625 dark, each just above
   its measured floor (0.487 and 0.611; the binding case in both is the auth
   showcase, where the crop exposes nearly the whole frame). What is left is
   for a re-encode of the picture. Never raise it "for safety": a second test
   fails if the shade drifts more than 0.10 above what the picture requires,
   because the image being visible is a requirement too.

   **And when someone asks for the photograph to read clearer, check whether
   the veil is what is in the way.** It is worth ~0.02 here and no more. The
   picture ships at 1600×900 and the hero box is about 1422×643 CSS px, which
   on a 2× display is 2844 device px across — a 1.8× upscale, and no
   stylesheet fixes that. Past this point clarity is a *file*, not a token.
2. **Chrome floating on a hero gets no veil of its own.** The sky at the top
   of the picture is shaded exactly as much as the mountains under the title,
   so the marketing header is already standing on the guarantee — which is
   why it can be genuinely invisible until it sticks. If that ever stops
   clearing the floor, the fix is a heavier `--hero-shade`, not a band: a
   band buys one strip of legibility by making the picture visibly patchy.
3. **Over a photograph, hierarchy is size and weight — never tint.** Greying
   text down is a trick that only works on flat ground. Every role below
   `--fg-default` needs about 0.79 against this picture where the default
   needs 0.49, so a muted lede would have cost the entire photograph to buy
   an effect the type scale already delivers. The hero lede, the proof list,
   the nav links at rest and the auth sub-paragraph all speak at full
   strength.
4. **Brand colour over a hero is a large-text privilege.** The title's
   gradient runs between `--brand-900` and `--brand-800` in light,
   `--brand-50` and `--brand-100` in dark — ramp steps that exist only for
   this. It works because WCAG's floor for 56px type is 3:1, and that
   headroom is the whole margin: a violet has to sit *further* from the
   picture than plain ink does to survive the same shade, so every working
   step of the ramp, `--brand` included, is already inside it.

**A backdrop ends where its box ends.** The hero's `padding-bottom` is clear
picture below the last line of copy, and then a straight edge. There is no
dissolve and no `--hero-mask`; see *Why there is no dissolve* below.

**Surfaces that float on a hero may be glass.** `--hero-card-fill` is how much
of the marketing card's own surface stays opaque — 85% light, 80% dark. The
constraint is never the card; it is the quietest ink printed on it.
`backdrop-filter: blur()` is what makes those percent look like anything, and
it is deliberately left out of the test: blurring moves pixels toward their
local mean, so it can only produce values inside the range already cleared.

**Transparency is bought from the type, not from the card.** With
`--fg-subtle` on the labels the light theme broke at **91.5%** — under a point
of room, and the honest answer to "make it a little more transparent" was *no*.
One step up to `--fg-muted` moves that floor to **54%**, because a step of
grey is worth far more against a photograph than against a solid surface. The
hierarchy survives it: those labels are 11px, medium, and tracked out, which is
the same argument the hero copy makes one layer up — over a photograph,
hierarchy comes from size and weight, never tint.

So the floor moves to whatever is *next* quietest, and on this card that turned
out to be a semantic hue: `--pos` in the delta pill, at **83.0% light** (dark
binds on `--income` at 55.5%). Which leads to the other half of the rule:

**A tinted wash under type of its own hue is a veil running backwards.**
`--pos-soft` behind `--pos` text moves the background *toward* the ink. On an
opaque page that is a cost the surface can absorb; on glass it is decisive —
measured, the full pill wants a **98%** fill to hold 4.5:1, more opaque than
the card has ever been, so it would have set the ceiling on every percent of
glass by itself. The marketing card's pill keeps its outline and drops its
fill.

The test's job is to name every ink the card actually prints, and to be
re-read whenever the card changes. A role listed that the card does not show
caps the glass for nothing; a role shown but not listed goes unmeasured.

**Why there is no dissolve.** A masked fade at the bottom of the hero went
through four rounds — linear, then curved, then weighted late, then
lengthened — each one asked for by the same complaint, that the gradient was
too strong. The last version was as good as the shape gets: 41px of picture
the mask never touched, a 19px washed stretch, a peak of 0.0567 alpha/px.

It still lost to a straight cut, and the arithmetic says why. Alpha has to
travel the whole way from 1 to 0, so a dissolve *must* spend a stretch of
photograph making itself invisible — that spent stretch is precisely what a
reader calls "a strong gradient". Shape decides where it lands and how fast
it goes; nothing removes it. An edge spends nothing, because it has no
boundary to hide: it *is* the boundary.

What made the edge affordable is that the backdrop is already leaving. The
scroll-driven lift takes the whole thing away within the first `68vh`, so the
cut is only on screen while the reader is at the very top of the page —
short of a dissolve's job and out of the way before it could become one.

Two things go with that decision. Keep them written down, because both were
found the hard way:

- If a dissolve ever comes back, mask, do not wash. Fading the picture out
  with a wedge of `--bg-canvas` *changes* colours to hide them — a milky
  band in light mode, a smear of black in dark — where a mask only removes,
  so the page shows through cleanly and one rule covers both themes. And put
  it on `.hero-media`, not the `<img>`, or the shade is stranded as a film
  over bare page colour.
- Judge any change to the bottom of the hero in the *light* theme, in crops
  anchored to the bottom of the hero rather than to a viewport coordinate.
  The light swing between shaded picture and canvas is ~84 levels against
  ~25 in dark, so that is where an edge or a seam shows first; and a change
  to the padding moves everything below it, which is enough to make an
  improvement look like a regression.

**The backdrop leaves with the page.** `.hero-media--lift` fades the whole
thing out across the first `--hero-lift-range` of scrolling, driven by
`animation-timeline: scroll(root)` — no scroll handler, no work on the main
thread. Contrast holds through every frame: both ends are colours the copy is
already guaranteed against, and a blend between two luminances stays between
them. Gated on `@supports` and on `prefers-reduced-motion`, with no JS
fallback on purpose — a handler writing opacity each frame is a jank
generator, and the static hero it would replace is already correct.

**The auth showcase takes the shade and nothing else** — no dissolve, no
lift. A bounded panel with its own border has no edge to hide, and a panel
that never scrolls has nothing to leave.

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
- While the header is transparent its links and its two secondary controls
  are too — only the primary call to action keeps a fill. Nothing pays for
  that but `--hero-shade` itself, which is the point: no band, no panel, no
  mark of any kind on the picture. It does force a colour change, since all
  of them normally sit at `--fg-muted` and that step needs about 0.79 against
  this photograph. They take `--fg-default` instead, and anything added to
  this row has to as well —
  `test_the_floating_header_needs_no_veil_of_its_own` is what keeps the shade
  and the header honest with each other.

**Below the hero the marketing page is one centred column.** Every section
announces itself with `.lp-head` on the page's centre line, on the same 44rem
measure, with the same step of air above and below — so the reader follows a
single vertical axis from the hero to the footer instead of re-finding where
each block starts. Two things were giving that up and both are now gone: the
"what it isn't" section faced its heading across a two-column gutter, and the
closing panel split the ask left-and-right, which sent the eye off the axis
at the exact moment it was being asked to act.

Centring is for announcements only. A centred paragraph makes the eye hunt a
moving left edge on every line, and the cost grows with the measure — which
is why heads are capped at 44rem inside an 82rem shell, and why everything
below a head (card copy, step copy, list rows) stays ragged-right. The rule
is the same one the tables follow: **centre what is being announced, left
what is being read.**

Section rhythm carries the rest. `--space-16` above and below each section
means a section boundary is always twice that and always the largest gap on
screen; nothing inside a section is allowed to open that wide. That single
constraint is what makes the sequence legible as a sequence.

## Command palette

`Ctrl/Cmd+K`. It reads static navigation entries from a JSON script tag in
`base.html`, plus **any element on the page carrying `data-command="Label"`**
(optionally `data-command-group` and `data-command-icon`). A page extends the
palette by adding one attribute — there is no registration step.

## Behaviour that lives in one place

Two widgets are mounted globally and must not be mounted again by a page.
Both failures are silent, which is what makes the rule worth writing down.

- **Tooltips.** `TooltipManager` in `main.js` mounts every
  `[data-bs-toggle="tooltip"]` on the page, with `getOrCreateInstance`.
  Constructing a second `bootstrap.Tooltip` over the same element does not
  replace the first: Bootstrap overwrites its own instance map, but the
  orphan keeps every listener it attached, so the element carries two live
  tooltips whose show/hide state can drift apart. The first construction also
  moves `title` into `data-bs-original-title`, so the second reads an empty
  title and which of the two renders is incidental. `index.html` and
  `portfolios.html` each mounted their own on top of the manager.
- **Pixel positions read once are wrong forever.** The allocation switcher's
  thumb is placed by measuring the selected option, and its `resize` handler
  closed over the option selected *at mount*. Resizing the window after
  switching slid the indicator back under the label the page opened with,
  while the chart kept showing the other. Anything that re-measures on resize
  must read current state at that moment, never a captured reference.

## Avoid

- Decorative gradients, glows, and ornamental shadows. The only gradients in
  the product are the hero scrims (see [Hero backdrops](#hero-backdrops)),
  and they are functional — they exist to make text readable, not to decorate.
- New one-off surface colours, radii, or durations.
- `!important` in our own layers.
- Uppercase labels.
- Inline `style` attributes, except to pass a numeric custom property
  (`--enter-index`, `--metric-columns`) that is genuinely data-driven.
