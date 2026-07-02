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
- **POSITIONS** = open position book cost.
- **BOOK VALUE** = total cash + positions.
- **TOTAL INCOME** = income records.
- **REALIZED P&L** = sell-only trading profit/loss using the Average Cost Method.
- **RETURN** includes realized P&L plus income.

For exact formulas, see [docs/DOMAIN_AND_CALCULATIONS.md](docs/DOMAIN_AND_CALCULATIONS.md).

## Features

- Manual multi-portfolio tracking.
- Capital entry log with deposits and withdrawals.
- Asset list with buy and sell entries.
- Average Cost Method calculations for open positions and sells.
- Separate income tracking.
- Dashboard totals, portfolio summaries, assets page, and charts based on recorded data.
- Multi-user accounts with per-user data scoping.
- Email verification, password reset, account settings, and admin user management.
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
- Authlib OAuth client foundation and disabled-by-default Google OAuth routes
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
python app.py
```

The development server runs at `http://127.0.0.1:5000` by default. The first registered user is promoted to admin.

## Configuration

Copy `.env.example` to `.env` and fill only local or deployment-specific values. Do not commit `.env`.

Supported environment variables are defined in [config.py](config.py):

| Variable | Description |
| --- | --- |
| `SECRET_KEY` | Flask session and CSRF signing key. Required outside debug/test contexts. |
| `DATABASE_URL` | SQLAlchemy database URI. Defaults to local SQLite `portfolio.db`. |
| `EMAIL_USER` | Gmail sender address for verification and reset emails. |
| `EMAIL_PASSWORD` | Gmail app password for the sender account. |
| `APP_BASE_URL` | Public base URL used in email links, without a trailing slash. |
| `SESSION_COOKIE_SECURE` | Set to `1` when served over HTTPS. Defaults secure outside debug/test contexts. |
| `DEV_AUTO_LOGIN` | Development-only first-user auto-login. Never enable in production. |
| `FLASK_DEBUG` | Enables Flask debug mode when set by your run environment. Also allows the dev-only secret fallback. |
| `GOOGLE_OAUTH_ENABLED` | Optional backend Google OAuth route flag. Disabled by default; existing-account Google sign-in is available only when explicitly configured. |
| `GOOGLE_CLIENT_ID` | Optional Google OAuth client ID, required only when `GOOGLE_OAUTH_ENABLED=1`. |
| `GOOGLE_CLIENT_SECRET` | Optional Google OAuth client secret, required only when `GOOGLE_OAUTH_ENABLED=1`. |
| `GOOGLE_REDIRECT_URI` | Optional Google OAuth callback URI, required only when `GOOGLE_OAUTH_ENABLED=1`. |

Gmail requires an app password, not the regular account password.

Google OAuth is disabled by default. When enabled, the login page shows a Google sign-in control for existing verified accounts only. Previously linked Google identities sign in by Google's stable OpenID Connect subject claim. On first successful Google sign-in, a verified Google email may create one Google identity link for a matching verified local account. Google sign-in does not create local accounts and does not persist provider tokens or payloads.

## Project Structure

```text
OnePortfolio/
├── app.py                    # Local development entry point
├── wsgi.py                   # WSGI entry point
├── config.py                 # Environment-driven configuration
├── init_db.py                # Database initialization helper
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
    └── utils/                # Formatting, decimal, messages, email, tokens
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
