# Design System

OnePortfolio uses a dark-only interface. The design system is token-driven, restrained, and optimized for dense record-keeping screens.

## Token Source

`portfolio_app/static/css/tokens.css` is the primary design-token source. Page CSS and templates should consume tokens rather than hard-coding new colors, radii, spacing, or font weights.

`style.css` contains component and page-level rules that build on those tokens.

## Visual Direction

- Dark-only UI.
- Near-black surfaces.
- Subtle borders instead of heavy shadows.
- Monochrome normal icons.
- No decorative gradients, glows, bokeh, or ornamental shadows.
- Maximum font weight: `600`.
- Compact layouts suitable for repeated financial review.

## Color Semantics

Use semantic colors only when the value or state is meaningful:

- positive/profit: green
- negative/loss: red
- income: blue
- warning: only for meaningful warnings or destructive-risk messaging

Neutral text, icons, borders, and surfaces should use the standard text/surface/border tokens.

## Radius, Borders, and Surfaces

Cards, controls, modals, and tables should use the shared radius and border tokens. Avoid adding new large-radius card styles or decorative nested cards.

Prefer:

- near-black card and page surfaces
- one subtle border or outline
- consistent control heights
- compact spacing

Avoid:

- decorative drop shadows
- glowing focus treatments unrelated to accessibility
- gradients as decoration
- one-off surface colors

## Controls and Spacing

Controls should align with existing button, input, table, modal, and card sizing. Use established Bootstrap and local classes before adding new CSS.

Interactive icon buttons should use Bootstrap Icons already present in the project. Text buttons are appropriate for clear commands; compact row actions generally use icons.

## Core Tokens and Compatibility Aliases

Core tokens define the current design language, such as text, surface, border, radius, and semantic state colors.

Compatibility aliases exist so older CSS selectors and Bootstrap-oriented components can keep working while the visual language remains centralized. New code should prefer core semantic tokens when practical and avoid expanding aliases unless it protects existing behavior.

## Bootstrap Token Bridging

The app uses Bootstrap components, but local tokens bridge Bootstrap variables into the OnePortfolio theme. When Bootstrap components need visual adjustment, prefer token overrides and local utility classes over one-off inline styles.

Do not copy large sections of CSS into documentation. Treat `tokens.css` as the authoritative source.
