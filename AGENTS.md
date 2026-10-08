# OnePortfolio Agent Instructions

## Project purpose

OnePortfolio is a financial portfolio tracking application.

Treat the following as primary project priorities:

1. Financial correctness
2. Data integrity
3. User-data isolation
4. Predictable behavior
5. UI consistency
6. Maintainability
7. Minimal, well-scoped changes

Task-specific requirements belong in the task/ticket, not in this file.

---

# General working rules

- Inspect the relevant existing code before making changes.
- Understand the current behavior before modifying it.
- Follow existing project patterns unless the task explicitly requires changing them.
- Keep changes scoped to the requested task.
- Do not perform unrelated refactors, cleanup, renaming, or formatting.
- Prefer the smallest coherent change that fully solves the problem.
- Reuse existing helpers, services, repositories, validators, calculators, utilities, components, and UI patterns before creating new abstractions.
- Do not add dependencies unless there is a clear need that cannot reasonably be handled by the existing stack.
- Do not change public behavior, database semantics, accounting rules, or business rules merely to simplify implementation.
- Do not silently alter existing behavior that is outside the requested scope.
- When behavior is ambiguous, derive intent from the existing code, tests, documentation, and surrounding patterns rather than inventing new product behavior.
- If uncertainty materially affects correctness, explicitly identify it instead of hiding it behind an assumption.

If a task intentionally changes an existing invariant or architectural decision, update the relevant tests and documentation together with the implementation.

---

# Architecture

Preserve the existing OnePortfolio architecture and separation of responsibilities.

Follow the established flow where applicable:

    Routes → Services → Repositories → Models
              ↓
          Calculators

Do not bypass an existing layer merely because implementing the task directly elsewhere is easier.

## Routes

Routes should primarily handle:

- HTTP request and response concerns
- authentication and authorization entry points
- input/form handling
- validation orchestration
- invoking services
- redirects
- template rendering

Do not place substantial financial calculations or domain/business logic directly in routes.

## Services

Services contain application workflows and coordinate repositories, calculators, and other domain operations.

Business operations involving multiple records or components should normally live in the service layer.

Avoid duplicating business workflows across multiple routes.

## Repositories

Repositories are responsible for data access and persistence concerns.

- Keep database queries out of routes and calculators.
- Reuse existing repository methods where possible.
- Preserve ownership scoping and filtering.
- Do not bypass repository safeguards merely for convenience.

## Models

Models represent persisted application state.

Do not move derived portfolio calculations into persisted model fields merely for convenience.

Avoid duplicating data that can be reliably derived from the underlying source records unless there is a documented and justified reason.

## Calculators

Financial calculations should live in the existing calculator or financial utility layers where applicable.

Prefer calculation functions that are:

- deterministic;
- explicit;
- easy to test;
- independent of presentation concerns.

Do not duplicate calculation formulas in templates, routes, or JavaScript.

---

# Financial correctness

Financial correctness is a critical project invariant.

A financially plausible result is not sufficient. The calculation must preserve the intended accounting and economic meaning.

## Decimal arithmetic

- Never use binary floating-point arithmetic for money, prices, share quantities, fees, cost basis, proceeds, returns, percentages, or other financial calculations.
- Use Python `Decimal` and the project's existing decimal utilities.
- Do not introduce intermediate conversions through `float`.
- Be explicit about rounding when rounding is actually required.
- Do not round intermediate values merely because the UI eventually displays fewer decimal places.
- Preserve precision for calculations independently from presentation formatting.

Treat these as separate concerns:

    calculation precision
    storage precision
    display formatting

A display requirement must not silently change the underlying financial value.

## Rounding

- Do not introduce arbitrary rounding rules.
- Follow existing project conventions where a rounding rule already exists.
- Round only at the appropriate financial or presentation boundary.
- Avoid repeated rounding across intermediate calculation steps.
- Never use rounding to conceal a mismatch in totals.

If a rounding decision can change economic value, it is a domain decision and must not be invented during implementation.

## Preserve economic meaning

When changing transaction or portfolio calculations:

- preserve total economic value unless the business event itself changes it;
- preserve cost basis according to the project's accounting rules;
- do not silently discard value;
- do not silently manufacture value;
- do not silently round share quantities to whole units;
- do not manufacture cash, shares, profit, loss, contributions, withdrawals, or dividends through implementation shortcuts.

If an operation can legitimately produce a fractional quantity, do not silently remove the fractional portion.

Separate real economic events should remain separately representable where appropriate.

## Source of truth

Prefer deriving financial metrics from their underlying authoritative records instead of maintaining duplicate totals that can drift out of sync.

Existing transactions, dividends, transfers, deposits, withdrawals, and other portfolio events should remain the source of truth for derived portfolio values unless the design explicitly establishes otherwise.

Avoid introducing denormalized financial totals solely to simplify UI rendering.

## Accounting semantics

Respect the accounting method and financial definitions already used by OnePortfolio.

Do not replace, mix, or reinterpret accounting methods as an implementation shortcut.

Changes involving any of the following require extra care and focused tests:

- quantity
- average cost
- cost basis
- book value
- market value
- realized P&L
- unrealized P&L
- total return
- contributions
- withdrawals
- transfers
- cash
- fees
- dividends
- stock splits
- reverse stock splits
- fractional shares
- cash-in-lieu
- partial sales
- full liquidation

Do not infer new accounting semantics solely from how a value is visually presented.

---

# Financial event integrity and auditability

Financial history should remain understandable from its underlying records.

- Avoid rewriting historical records merely to make a current calculation easier.
- Prefer representing real financial events explicitly where the existing domain model supports them.
- Preserve transaction dates, amounts, fees, quantities, and metadata unless the requested operation intentionally changes them.
- Avoid hidden side effects that modify unrelated historical records.
- Do not silently alter previous transactions to reconcile a new result.
- Do not use destructive historical mutation when a separate financial event is the more accurate representation.

Any operation that changes historical transaction semantics should be treated as a financial-domain change and tested accordingly.

---

# User data isolation

OnePortfolio is a multi-user application.

User-data isolation is a security invariant.

- Every read or mutation of user-owned financial data must be scoped to the authenticated user's ownership.
- Preserve the project's existing ownership-filtering strategy.
- Never trust an object ID from a URL, form, request, or client-side value as proof of ownership.
- Do not weaken repository-level ownership scoping for convenience.
- A forged ID belonging to another user must not expose, modify, delete, transfer, or otherwise affect that user's data.
- New queries involving user-owned data must follow the same isolation rules as existing secure queries.
- Bulk operations must preserve the same ownership guarantees as single-record operations.

When adding or modifying data-access behavior, include cross-user isolation coverage where relevant.

---

# Validation

Reuse the project's existing validation infrastructure.

For user-controlled input:

- validate on the server;
- do not rely on client-side validation alone;
- preserve CSRF protections;
- preserve authorization checks;
- reject invalid financial values rather than coercing them into plausible values;
- validate ranges and relationships when individual field validation is insufficient.

Do not silently normalize invalid financial input into a different valid transaction.

Validation behavior should remain consistent between create and edit workflows where the same financial rules apply.

---

# Security

Security behavior must not be weakened as a side effect of unrelated work.

Do not:

- commit secrets or credentials;
- hard-code production secrets or environment-specific credentials;
- expose sensitive authentication information;
- weaken login protections;
- weaken password-reset protections;
- weaken OTP protections;
- weaken rate limiting;
- weaken session protections;
- weaken authorization or ownership checks;
- expose internal exception details to end users without an established reason.

Development-only behavior must remain clearly separated from production behavior.

---

# Database and migrations

Follow the project's existing database and migration conventions.

- Migrations must account for existing user databases.
- Do not assume a fresh database.
- Preserve migration idempotency where the current migration system expects it.
- Do not delete or recreate user data as a migration shortcut.
- Preserve foreign-key integrity.
- Do not change schema merely to avoid implementing domain logic correctly.
- Avoid introducing nullable or duplicate state without considering how existing records behave.
- Do not modify historical migration behavior casually.

When introducing a schema change:

1. inspect the existing schema and migration conventions;
2. consider existing installations;
3. implement the required migration;
4. verify fresh-database behavior where applicable;
5. verify upgrade behavior where practical;
6. update tests;
7. document any meaningful compatibility implications.

---

# Frontend and UI

UI consistency is a project invariant.

Do not invent a new visual language for OnePortfolio when an established project pattern or design-reference pattern already exists.

Preserve and reuse existing:

- layout conventions;
- spacing conventions;
- typography hierarchy;
- card patterns;
- forms;
- menus;
- dialogs;
- controls;
- badges;
- tables;
- tooltips;
- empty states;
- feedback states;
- icon conventions;
- responsive behavior;
- light/dark theme behavior.

Avoid isolated one-off UI patterns when an existing reusable pattern can solve the same problem.

Do not introduce a new frontend framework or component system merely to implement one feature.

UI implementation must not change financial semantics merely to make values easier to display.

---

# Canonical design reference

The canonical visual design reference for OnePortfolio is the following shadcn/ui preset:

    https://ui.shadcn.com/create?preset=b1YmpWHpo

Treat this preset as the project's primary design source of truth for UI work.
Existing OnePortfolio components are implementation assets, not design
authority. A component is not presumed correct merely because it is shared,
reusable, centralized, or already implemented.

This is a design reference, not automatically a requirement to adopt the shadcn/ui runtime, React, Tailwind, or any other technology used by the reference implementation.

## When the reference must be used

Before creating, modifying, or reusing a user-facing component or pattern,
inspect the corresponding component or closest applicable pattern in the
canonical design reference.

This includes work involving:

- pages;
- cards;
- navigation;
- action menus;
- dropdowns;
- dialogs;
- forms;
- inputs;
- buttons;
- tabs;
- tables;
- badges;
- tooltips;
- alerts;
- empty states;
- metric displays;
- dashboard sections;
- portfolio actions;
- interactive controls;
- new visual components.

Do not make material visual decisions from memory when the reference is available for inspection.

## Design decisions

Compare the reference and local implementation at the component level,
including structure, spacing, density, alignment, typography, states, icons,
radii, borders, separators, shadows, colors, and interaction behavior.

Do not invent a substantially different design when an applicable pattern exists in the reference.

Prefer adapting an established reference pattern over creating a custom one-off design.

## Adaptation to OnePortfolio

The reference defines visual direction and interaction quality.

The OnePortfolio codebase defines implementation technology.

Therefore:

- adapt relevant reference patterns to the project's existing frontend stack;
- reuse existing OnePortfolio components and styles only when inspection
  confirms that they reproduce the intended reference pattern;
- when a shared component differs, prefer aligning that shared component over
  adding page-specific or one-off styling;
- do not install or migrate to shadcn/ui, React, Tailwind, or another framework solely to reproduce a reference component;
- do not blindly copy code from the reference when its technology differs from the project;
- reproduce the intended visual hierarchy and interaction behavior using the existing architecture.

The goal is design consistency, not dependency consistency.

## Existing UI versus reference

Preserve consistency with existing OnePortfolio interfaces that already align with the canonical reference.

When an existing interface materially conflicts with the reference but fixing it is outside the current task:

- do not silently redesign unrelated UI;
- keep the requested change scoped;
- avoid propagating the inconsistent pattern into new UI where possible;
- mention the relevant inconsistency in the final report only when it materially affected the implementation.

Do not turn a focused feature request into a broad visual redesign.

## When no exact reference pattern exists

If the canonical reference does not contain an exact pattern for a required feature:

1. identify the closest applicable reference pattern;
2. preserve the reference's hierarchy, spacing, controls, and visual language;
3. reuse compatible existing OnePortfolio patterns;
4. extend conservatively;
5. avoid introducing a new visual language.

The absence of an exact component is not permission to design without reference to the established system.

## Reference accessibility

If the canonical design reference cannot be accessed during a UI task:

- do not falsely claim that it was inspected;
- do not infer compliance from existing local components or documentation;
- do not guess or make speculative reference-alignment changes;
- explicitly report which reference components or patterns could not be
  inspected.

Never claim design-reference compliance without inspecting the canonical
reference itself.

---

# UI clarity for financial information

Financial interfaces should prioritize comprehension over decoration.

- Use clear visual hierarchy between primary and secondary financial metrics.
- Avoid presenting different accounting concepts as if they were interchangeable.
- Labels should reflect the actual financial meaning of the value.
- Do not hide important financial state solely to make a card visually simpler.
- Do not use color as the only means of communicating gain, loss, warning, or status.
- Ensure important values remain understandable in both light and dark themes.

Small informational indicators or tooltips may be used when a financial metric materially benefits from clarification.

Tooltips should:

- clarify meaning rather than restate the label;
- be concise;
- be accessible by appropriate pointer and keyboard interaction;
- avoid unnecessary clutter;
- follow the canonical design reference where applicable.

Do not add informational icons indiscriminately to every metric.

---

# Icons and actions

Use semantically appropriate icons.

- Do not reuse an unrelated icon merely because it is visually similar.
- Follow the project's existing icon system.
- Use the canonical design reference to resolve visual-treatment questions where applicable.
- Normal, navigational, financial, and destructive actions should remain distinguishable.
- Destructive actions must not be visually grouped in a way that makes them appear equivalent to routine actions without intentional design justification.

Labels, icon meaning, and action behavior should agree.

---

# Responsive behavior

New or modified UI must remain usable across the screen sizes already supported by OnePortfolio.

Do not design only for the viewport visible during development.

Check relevant:

- narrow layouts;
- wide layouts;
- wrapping;
- truncation;
- tables;
- menus;
- dialogs;
- touch targets;
- card layouts;
- metric layouts.

Avoid arbitrary breakpoint-specific hacks when existing responsive patterns can be reused.

---

# Accessibility

Preserve or improve accessibility when modifying UI.

Interactive elements should:

- use appropriate semantic elements;
- remain keyboard accessible;
- have accessible labels where the visible content is insufficient;
- expose appropriate focus behavior;
- not rely exclusively on hover;
- not rely exclusively on color;
- preserve readable contrast;
- avoid inaccessible custom controls where native or existing accessible patterns exist.

Do not sacrifice accessibility merely to match a visual reference.

---

# JavaScript

Keep client-side behavior consistent with the project's existing JavaScript architecture.

- Reuse existing application/component patterns.
- Avoid global state when an existing scoped mechanism is available.
- Keep DOM behavior separate from backend financial rules.
- Do not duplicate authoritative server-side business logic in JavaScript.
- Treat client-calculated values as presentation helpers, not authoritative financial data.
- Do not rely on JavaScript as the sole enforcement mechanism for security or financial validation.

When JavaScript changes user-visible financial values, verify that those values originate from authoritative backend data or use exactly the intended presentation calculation.

---

# Tests

Tests are required for behavioral changes.

Use the smallest relevant test set during implementation, then run broader relevant tests before considering a meaningful change complete.

Typical command:

    pytest -v

For focused tests:

    pytest -v path_or_test_file.py::test_name

Use the project's actual available test commands if they differ.

## Bug fixes

When fixing a bug:

1. reproduce or identify the incorrect behavior;
2. add or identify a test that captures it where practical;
3. implement the fix;
4. verify the regression test;
5. verify relevant existing tests still pass.

Do not modify a correct test merely to make an incorrect implementation pass.

## Financial tests

Financial tests should use exact expected values where appropriate.

Avoid vague floating-point approximations for values that should be exact.

Test relevant edge cases such as:

- zero values;
- fractional quantities;
- precision boundaries;
- fees;
- multiple purchases;
- partial sales;
- full liquidation;
- deposits;
- withdrawals;
- transfers;
- dividends;
- stock splits;
- reverse stock splits;
- cash-in-lieu;
- rounding boundaries;
- historical transactions;
- cross-user access.

Do not add every edge case to every test file. Add the cases relevant to the behavior being changed.

## UI tests and verification

For meaningful UI changes, verify as applicable:

- intended component hierarchy;
- existing behavior;
- responsive behavior;
- light theme;
- dark theme;
- keyboard interaction;
- empty state;
- validation/error state;
- long or unusual content;
- financial-value formatting.

Do not consider a UI change complete solely because it renders without an exception.

Visual acceptance is performed by the user. Automated agents should verify
code, behavior, tests, and accessibility contracts, but must not treat their
own visual review as acceptance unless visual verification is explicitly
requested.

---

# Compatibility

Unless explicitly requested otherwise, preserve:

- existing user data;
- database compatibility;
- existing URLs;
- route behavior;
- form contracts;
- API contracts;
- accounting semantics;
- financial history;
- authentication behavior;
- authorization behavior;
- supported themes;
- existing workflows relied upon elsewhere in the application.

If compatibility must be broken to implement a requested change correctly, make the break explicit in the implementation summary.

Do not introduce compatibility breaks silently.

---

# Dependencies

Before adding a dependency:

1. determine whether the project already provides the required capability;
2. determine whether a small implementation using the existing stack is more appropriate;
3. consider maintenance and security implications;
4. add the dependency only when justified.

Do not add a package solely to avoid understanding existing project code.

For UI work, the existence of a component in the shadcn design reference is not by itself justification for adding shadcn/ui or its technology stack as a dependency.

---

# Documentation

Do not duplicate large amounts of implementation documentation in this file.

Use the existing README, source code, tests, and focused documentation for implementation details.

Update documentation when a task changes:

- user-visible behavior;
- setup;
- configuration;
- environment variables;
- architecture;
- financial semantics;
- migration requirements;
- deployment requirements.

Do not create documentation churn for internal changes that do not affect documented behavior.

---

# Task and ticket boundaries

`AGENTS.md` contains durable project rules.

Task-specific requirements belong in the task or ticket.

Do not add temporary feature requirements to this file.

Examples of task-specific information that belongs in a ticket rather than here:

- redesigning a specific card;
- moving a specific menu item;
- adding a specific metric;
- changing a particular transaction type;
- fixing one calculation bug;
- following a one-off screenshot;
- using a reference image for one component;
- implementing a particular feature.

A ticket may introduce additional constraints for that task.

Task-specific instructions may refine these project rules, but they should not silently weaken financial correctness, security, data isolation, or other critical invariants.

---

# Working with task-specific design references

A ticket may provide an additional screenshot, mockup, component example, or design reference for a specific feature.

When it does:

- treat the task-specific reference as authoritative for that feature's composition and intended result;
- use the canonical OnePortfolio shadcn preset for the broader design language;
- reconcile the two rather than ignoring either one;
- do not extrapolate a one-off task reference into an unrelated global redesign.

In general:

    task-specific reference
        → specific composition and requested feature

    canonical OnePortfolio design reference
        → overall visual language and interaction patterns

    existing OnePortfolio code
        → implementation architecture

If the references materially conflict, do not silently choose an unrelated third design.

---

# Completion criteria

Before considering a task complete:

- verify the requested behavior is implemented;
- verify the implementation matches the ticket;
- verify relevant tests;
- check for financial regressions when financial logic changed;
- check ownership and user isolation when data access changed;
- check both valid and invalid input paths when validation changed;
- verify persistence behavior when database state changed;
- verify relevant UI states when UI changed;
- keep the diff scoped to the task;
- remove temporary debugging code;
- remove accidental unrelated changes;
- do not leave silent fallbacks that conceal incorrect states;
- do not report checks as completed unless they were actually performed.

---

# Final implementation report

Every completed task should end with a concise implementation report.

Include:

## Changes

State what was changed.

Focus on behavior and important implementation decisions rather than listing every edited line.

## Verification

State what was actually verified.

Examples:

- tests executed;
- focused regression tests;
- broader test suite;
- manual verification;
- migration verification;
- UI states inspected.

Do not claim a test or check was performed if it was not.

## Important decisions

Mention important architectural, financial, compatibility, or security decisions when relevant.

Do not fill this section with trivial implementation details.

## Limitations or follow-up

Mention only limitations or unresolved issues that materially affect the requested behavior.

Do not invent follow-up work merely to make the report longer.

---

# UI design-reference reporting

For every task that adds, redesigns, or materially changes user-facing UI, the final implementation report must also contain:

## Design reference

State:

- whether the canonical OnePortfolio design reference was inspected;
- which relevant patterns or components were used as guidance;
- how the design was adapted to the existing OnePortfolio frontend architecture;
- whether a task-specific visual reference was also used;
- any intentional deviation from the reference and the reason for it.

Example:

    Design reference:
    - Inspected the canonical OnePortfolio shadcn preset.
    - Used its dropdown hierarchy, spacing, icon treatment, and action grouping
      as the reference for the updated menu.
    - Adapted the pattern to the existing OnePortfolio frontend implementation;
      no new UI framework was introduced.
    - No intentional visual deviations.

If there was an intentional deviation:

    Design reference:
    - Inspected the canonical OnePortfolio shadcn preset.
    - Used its card hierarchy, spacing, typography, and secondary-value treatment.
    - Preserved the existing chart controls because replacing them was outside
      this ticket's scope.
    - This is the only intentional deviation from the reference.

If the external reference could not be accessed:

    Design reference:
    - The canonical external design reference could not be accessed during this task.
    - Used existing OnePortfolio components consistent with the established design
      language and avoided introducing a new visual pattern.
    - Reference compliance was not claimed.

Never write that the implementation follows the canonical design reference unless it was actually inspected or an established local representation of it was used.

---

# Final principles

When multiple implementation options are valid, prefer the option that:

1. preserves financial correctness;
2. preserves user-data isolation;
3. preserves existing behavior outside the task;
4. fits the existing architecture;
5. matches the established OnePortfolio design language;
6. minimizes unnecessary complexity;
7. is straightforward to test;
8. leaves the codebase easier to reason about.

Do not optimize for cleverness.

Do not hide uncertainty.

Do not silently invent product behavior.

Do not silently invent financial behavior.

Do not silently invent UI design when an established reference exists.
