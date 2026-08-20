# OnePortfolio

OnePortfolio is a Flask web app for manual portfolio record keeping. It tracks portfolios, capital entries, assets, buy/sell asset entries, and income records from data you enter yourself.

It does not fetch live prices, calculate market value, calculate unrealized P&L, connect to brokers, or provide financial advice.

## What It Tracks

- **Portfolios**: user-defined buckets such as Stocks, ETFs, Gold, or any other name.
- **Capital entries**: deposits and withdrawals.
- **Assets**: symbols tracked inside a portfolio.
- **Asset entries**: buy and sell records with price, quantity, fees, date, and notes.
- **Income**: income records attributed to an asset symbol.

## Current Terminology

- **TOTAL CAPITAL** = deposits - withdrawals.
- **TOTAL CASH** = available cash.
- **POSITIONS** = recorded cost basis of current positions.
- **BOOK VALUE** = total cash + recorded cost basis of current positions.
- **TOTAL INCOME** = income records.
- **REALIZED P&L** = profit or loss from completed sales using the Average Cost Method and sell fees.
- **RETURN** includes realized P&L plus income.

For exact formulas, see [docs/DOMAIN_AND_CALCULATIONS.md](docs/DOMAIN_AND_CALCULATIONS.md).

## Features

- Manual multi-portfolio tracking.
- Capital entry log with deposits and withdrawals.
- Asset list with buy and sell entries.
- Average Cost Method calculations for open positions and sells.
- Separate income tracking.
- Overview totals, portfolio summaries, assets page, and Overview allocation charts based on recorded data.
- Multi-user accounts with per-user data scoping.
- Passwordless email-code login, registration, and account settings.
- Responsive dark-only UI using Bootstrap, Bootstrap Icons, and local design tokens.

## Tech Stack

- Python 3
- Flask
- Flask-SQLAlchemy
- SQLite by default
- Flask-Login
- Flask-WTF CSRF support plus custom validation
- Flask-Mail for email delivery
- Flask-Limiter for auth rate limits
- Bootstrap 5, Bootstrap Icons, vanilla JavaScript
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
- [Development](docs/DEVELOPMENT.md)
- [Design system](docs/DESIGN_SYSTEM.md)
- [Migrations](docs/MIGRATIONS.md)

## Testing

```bash
python -m pytest -v
python -m compileall portfolio_app
git diff --check
```

Tests live in `tests/`.

## Deployment Notes

Use `wsgi.py` or your host's WSGI configuration to create the Flask app. Set required environment variables in the host environment rather than source control. Use HTTPS and set `SESSION_COOKIE_SECURE=1` for production deployments.

## License

MIT. See [LICENSE](LICENSE).

## Disclaimer

OnePortfolio is for personal record keeping and educational use. It does not provide financial advice and does not connect to any broker or market-data service.
