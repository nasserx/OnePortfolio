# Development

Use a branch per change and keep application behavior changes separate from documentation, styling, and cleanup changes.

## Setup

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

### Linux/macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

Fill `.env` with local values. Do not commit `.env`. `SECRET_KEY` must be set — a copied `.env.example` leaves it blank and startup fails with `SECRET_KEY environment variable must be set`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Running the App

```bash
python app.py
```

Open `http://127.0.0.1:5000`.

`app.py` is the local entry point and selects the debug development configuration; production serves the base configuration through `wsgi.py`. The database is created and migrated by the application factory at startup, so there is no separate initialization script to run.

For local development only, `DEV_AUTO_LOGIN=1` can auto-login as the first user.
The application rejects this setting outside debug/test mode. Production has no
demo, password, or OAuth authentication bypass.

Normal authentication is email plus a six-digit one-time code delivered through
the configured mail provider. Login codes expire after 10 minutes, allow five
failed attempts, and are replaced on resend. Sessions have a rolling seven-day
idle lifetime and a 30-day absolute lifetime; sensitive account changes require
authentication within 15 minutes.

## Validation Commands

Run the full test suite:

```bash
python -m pytest -v
```

Compile Python files:

```bash
python -m compileall portfolio_app
```

Check whitespace errors in the diff:

```bash
git diff --check
```

Check changed files:

```bash
git status --short
```

## Manual QA

For behavior changes, manually exercise the affected page or route. For financial behavior, verify:

- Realized Trading P&L remains limited to completed sales.
- Dividend Income records represent investment dividends/distributions and remain separate from trading P&L.
- Cash Balance includes Dividend Income.
- Internal transfers add signed portfolio cash without changing external Net
  Contributions. Validate both endpoints through the shared daily ledger; never
  simulate a transfer with independent funding rows. Run
  `node tests/portfolio_transfers.js` for exact edit-payload checks.
- Cash-account service acceptance validates every recorded day's closing cash.
  Seed raw legacy fixtures explicitly when testing negative-history reads;
  new Buy/Withdrawal service tests must record funding on or before the spend.
  Run `node tests/cash_account_max.js` for date-aware Max and stale-response checks.
- Book Value is Cash Balance plus the recorded cost basis of current positions.
- Position Cost Basis does not change because of Dividend Income.
- Realized Trading Return is trading P&L / released cost basis × 100 at every scope.
- Aggregate P&L and released basis first; never average percentages.
- Funding, open positions and Dividend Income do not dilute or increase trading return.
- Total Realized Earnings includes trading P&L plus Dividend Income as a money amount only.
- No sales means undefined return (dash), not zero return. A break-even sale gives genuine 0%.

For UI changes, check desktop and narrow viewports and confirm text does not overlap or overflow.

## Testing financial mutations

Use the `financial_mutation` service boundary, or `mutation_transaction()` when
composing multiple services. Start with a clean session; never manually begin a
deferred transaction before entering it. Repositories add/delete/flush only
inside this boundary. Do not commit in nested services or swallow a failed
sub-operation and continue writing. The owner commits validation, raw writes
and durable retry receipt together; any failed sub-operation rolls back all of
them. Existing nonfinancial authentication workflows retain their own commits.

All financial HTTP POSTs (including confirmed account removal) require the
hidden `mutation_token` issued with the rendered form, in addition to CSRF.
Keep the token unchanged on a network retry. After success, the existing page
reload issues new intents. Reusing a successful token with changed fields or a
different action is a conflict. Edits/removals require the account revision from
the form's render; a conflict uses the existing form-level error and asks for a
refresh. No formatted numeric value serves as a concurrency token.

`tests/_mutation_client.py` supplies fresh signed intents for existing route
tests, as a newly rendered form would. Set `auto_mutation_tokens=False` for
missing-token, stale-form and retry tests and reuse explicit tokens. This test
helper never bypasses production token verification. Direct service tests may
pass `expected_revision` when simulating an old read. Test concurrency with
separate application contexts/connections and inject failures after SQL writes,
not only before validation. Relevant groups:

```bash
pytest -q tests/test_mutation_integrity.py tests/test_mutation_migration.py tests/test_cash_account_policy.py tests/test_portfolio_transfers.py
```

The mutation receipt table has no automatic pruning: its history protects
successful retries and its monotonic IDs provide revisions. A future retention
change must preserve both contracts. Raw fixture seeding is for legacy/test
states only and deliberately bypasses these application guards.

## Repository Safety

Never commit:

- `.env` or environment variants with secrets
- local SQLite databases
- virtual environments
- Python, pytest, or tool caches
- screenshots
- logs
- generated local artifacts such as `project-structure.txt`

## Workflow

1. Create or switch to a branch for the change.
2. Make focused edits.
3. Run validation commands.
4. Review `git diff`.
5. Commit with a concise message describing the behavior or documentation change.
6. Prefer squash-merge for a short-lived branch when the final branch history should be one coherent change.

Do not mix schema changes, financial calculation changes, UI redesigns, and documentation cleanup in one branch.
