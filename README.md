# OnePortfolio

OnePortfolio is a Flask web app for manual portfolio record keeping. It tracks portfolios, funding entries, assets, buy/sell asset entries, and Dividend Income records from data you enter yourself.

It does not fetch live prices, calculate market value, calculate unrealized P&L, connect to brokers, or provide financial advice.

OnePortfolio models a cash account, not margin or borrowing. Recorded funding must
cover purchases and withdrawals at each effective day's close; same-day inflows
and outflows are netted because execution times and settlement are not modeled.
Legacy cash deficits remain visible and repairable. See the
[cash-account policy](docs/FINANCIAL_READ_MODEL.md#cash-account-policy).

## What It Tracks

- **Portfolios**: user-defined buckets such as Stocks, ETFs, Gold, or any other name.
- **Funding Entries**: deposits and withdrawals.
- **Internal Transfers**: linked cash movements between your portfolios; excluded
  from Net Contributions and consolidated capital/earnings. Incoming transfers
  count toward the receiving portfolio's historical paid-in capital. No FX.
- **Assets**: symbols tracked inside a portfolio.
- **Asset entries**: buy and sell records with price, quantity, fees, date, and notes.
- **Dividend Income**: dividend/distribution income attributed to an asset symbol.

## Financial terminology

See the [canonical financial glossary](docs/DOMAIN_AND_CALCULATIONS.md) for all
names and formulas. Book Value remains Cash + Cost Basis. Cumulative P&L includes
realized trading results and cash dividends. Asset Return divides this P&L by
historical Purchase Cost including buy fees; portfolio Return uses all external
deposits plus incoming transfers; consolidated Return uses external deposits only.
Withdrawals never reduce historical capital. Redeposits and incoming transfer
round trips count again, intentionally diluting local return. Retained/reinvested
earnings are not portfolio contributions. Zero capital displays a dash, while
positive capital with zero earnings displays 0%. Sale rows remain trading-only.
These are cumulative, non-annualized accounting returns, not market performance.
Annualized returns, TWR, MWR, XIRR and external valuations are not implemented.

## Features

- Manual multi-portfolio tracking.
- Funding entry log with deposits and withdrawals.
- Asset list with buy and sell entries.
- Average Cost Method calculations for open positions and sells.
- Separate Dividend Income tracking.
- Overview totals, portfolio summaries, assets page, and Overview allocation charts based on recorded data.
- Multi-user accounts with per-user data scoping.
- Passwordless email-code login, registration, and account settings.
- Responsive UI with light and dark themes using the Nova design contract,
  Geist typography, Tabler icons, and Bootstrap runtime behavior.

## Tech Stack

- Python 3
- Flask
- Flask-SQLAlchemy
- SQLite by default
- Flask-Login
- Flask-WTF CSRF support plus custom validation
- Flask-Mail for email delivery
- Flask-Limiter for auth rate limits
- Bootstrap 5 runtime, Tabler icons, Geist, vanilla JavaScript
- pytest

## Quick Start

Prerequisite: Python 3.8 or newer.

### Windows PowerShell

```powershell
git clone https://github.com/nasserx/OnePortfolio.git
cd OnePortfolio
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
# Paste the printed value into SECRET_KEY in .env, then:
python app.py
```

### Linux/macOS

```bash
git clone https://github.com/nasserx/OnePortfolio.git
cd OnePortfolio
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
# Paste the printed value into SECRET_KEY in .env, then:
python app.py
```

`SECRET_KEY` is required. A copied `.env.example` leaves it blank, and `python app.py` then stops at startup with `SECRET_KEY environment variable must be set`.

There is no separate database-initialization step. The application factory creates and migrates the SQLite database on startup, so the first `python app.py` prepares `portfolio.db` by itself.

Sending authentication and account-verification codes needs real `EMAIL_USER` and `EMAIL_PASSWORD` credentials; local delivery is not stubbed or suppressed.

The development server runs at `http://127.0.0.1:5000` by default. `python app.py` is the local entry point only: it selects the debug development configuration, while production runs the base configuration through `wsgi.py` (see [Deployment Notes](#deployment-notes)). Registered users manage only their own accounts and tenant-scoped portfolio data; the public application exposes no privileged cross-user role. Exceptional deployment or database maintenance remains outside the application authorization model.

## Configuration

Copy `.env.example` to `.env` and fill only local or deployment-specific values. Do not commit `.env`.

Supported environment variables are defined in [config.py](config.py):

| Variable | Description |
| --- | --- |
| `SECRET_KEY` | Flask session and CSRF signing key. Read when `config.py` is imported, so `python app.py` does not exempt it: set it unless `FLASK_DEBUG` or pytest enables the dev-only insecure fallback. |
| `DATABASE_URL` | SQLAlchemy database URI. Defaults to local SQLite `portfolio.db`. |
| `EMAIL_USER` | Gmail sender address for authentication and account-verification codes. |
| `EMAIL_PASSWORD` | Gmail app password for the sender account. |
| `SESSION_COOKIE_SECURE` | Controls Secure session cookies and HSTS. Unset/blank uses automatic mode: secure outside debug/test contexts. Explicit values are `1`/`true` or `0`/`false`; other values fail startup. |
| `RATELIMIT_STORAGE_URI` | Flask-Limiter storage URI. Unset/blank uses process-local `memory://`, suitable when one application process is authoritative for counters. Multi-process deployments require a shared Flask-Limiter backend and its deployment-specific client/service; none is bundled by this repository. |
| `DEV_AUTO_LOGIN` | Development-only first-user auto-login. Never enable in production. |
| `FLASK_DEBUG` | Enables Flask debug mode when set by your run environment. Also allows the dev-only secret fallback. |
Gmail requires an app password, not the regular account password.

Authentication uses email plus a six-digit one-time code. Codes expire after 10
minutes, allow at most five failed verification attempts, and are rotated on
resend. A successful login has a rolling seven-day inactivity lifetime and a
30-day absolute lifetime. Sensitive account changes require authentication in
the preceding 15 minutes. Password and Google OAuth runtime paths are not
available, remember-me is not used, and the application publishes no shared
demo credentials.

## Project Structure

```text
OnePortfolio/
├── app.py                    # Local development entry point
├── wsgi.py                   # WSGI entry point
├── config.py                 # Environment-driven configuration
├── requirements.txt          # Python dependencies
├── pytest.ini                # pytest configuration
├── tests/                    # Test suite
├── docs/                     # Project documentation
└── portfolio_app/
    ├── __init__.py           # Application factory, startup migrations, app wiring
    ├── models/               # SQLAlchemy models
    ├── repositories/         # Scoped data access
    ├── services/             # Business workflows
    ├── calculators/          # Financial calculations
    ├── forms/                # Form validation
    ├── routes/               # Flask blueprints
    ├── templates/            # Jinja templates
    ├── static/               # CSS, JavaScript, icons
    └── utils/                # Formatting, decimal, messages, email, OTP/session helpers
```

## Documentation

- [Domain and calculations](docs/DOMAIN_AND_CALCULATIONS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Financial read models](docs/FINANCIAL_READ_MODEL.md)
- [Development](docs/DEVELOPMENT.md)
- [Design system](docs/DESIGN_SYSTEM.md)
- [Migrations](docs/MIGRATIONS.md)

## Testing

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -v
python -m compileall portfolio_app
```

Tests live in `tests/` and use isolated databases. See
[Development](docs/DEVELOPMENT.md#validation-commands) for all JavaScript assertion
and syntax checks. Node.js is needed for those checks, not for application runtime.

The current SQLite schema is 40. Its account-lifetime session identities
intentionally invalidate pre-upgrade login cookies; existing users sign in again.
See [Migrations](docs/MIGRATIONS.md#schema-40-account-lifetime-session-identity)
for deployment compatibility and upgrade guarantees.

## Deployment Notes

Use `wsgi.py` or your host's WSGI configuration to create the Flask app. Set required environment variables in the host environment rather than source control. Use HTTPS and set `SESSION_COOKIE_SECURE=1` for production deployments.

## License

MIT. See [LICENSE](LICENSE).

## Disclaimer

OnePortfolio is for personal record keeping and educational use. It does not provide financial advice and does not connect to any broker or market-data service.
