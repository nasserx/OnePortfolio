# OnePortfolio

![CI](https://github.com/nasserx/OnePortfolio/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![Flask](https://img.shields.io/badge/flask-3.0.0-green.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Status](https://img.shields.io/badge/status-active-success.svg)

> A web application for tracking investment portfolios across multiple asset classes — with transaction history, average cost computation, realized P&L calculations, and dividend income tracking. No external APIs or price feeds required.

## Table of Contents

- [Features](#-features)
- [Tech Stack](#️-tech-stack)
- [Live Demo](#-live-demo)
- [Quick Start](#-quick-start)
- [Configuration](#-configuration)
- [Project Structure](#-project-structure)
- [Testing](#-testing)
- [Deployment](#-deployment)
- [Roadmap](#-roadmap)
- [License](#-license)

## ✨ Features

| Feature | Description |
|---------|-------------|
| **Multi-Asset Support** | Track Stocks, ETFs, Commodities, Crypto, or any custom asset class |
| **Portfolio Overview** | Dashboard with Total Contributed, Book Value, Total Dividends, and Realized P&L across all portfolios |
| **Portfolio Management** | Create portfolios with deposit/withdraw support and a full event audit trail |
| **Transaction Tracking** | Buy/sell operations with automatic Average Cost Method (ACM) computation |
| **Dividend Income** | Record dividends per symbol; automatically factored into Realized P&L |
| **Realized P&L** | Computed on every sell: Σ (sell price − avg cost) × qty − fees + dividends |
| **Financial Metrics** | Book Value (Cost Basis + Cash), Net Deposits, Cost Basis, Available Cash per portfolio |
| **Charts** | Visual breakdown of portfolio allocation and performance |
| **Paginated Views** | Windowed pagination on both transaction symbol cards and portfolio event rows |
| **Dark / Light Mode** | Full theme toggle with Google Material Design 3 color tokens |
| **Email Verification** | 6-digit OTP sent to email on registration |
| **Password Reset** | Secure reset link via email, expires in 1 hour |
| **Multi-User Auth** | Separate accounts with full data isolation; first registered user becomes admin |
| **Account Settings** | Change password, update email, and self-service account deletion with OTP confirmation |
| **Admin Panel** | Manage users, send password reset emails, toggle admin privileges |
| **Manual Entry** | Full control over your data — no third-party price feeds or broker integrations |

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.8+ · Flask 3.0.0 |
| Database | SQLite · Flask-SQLAlchemy |
| Frontend | Bootstrap 5.3 · Vanilla JavaScript · Google Material Design 3 tokens |
| Auth | Flask-Login · Werkzeug password hashing |
| Email | Flask-Mail · Gmail SMTP |
| Forms | Flask-WTF (CSRF) + custom validation layer |
| Testing | pytest |

## 🌐 Live Demo

👉 https://oneportfolio.pythonanywhere.com/

**Demo credentials:**

| Field | Value |
|-------|-------|
| Username | `demo` |
| Password | `demo1234` |

## 🚀 Quick Start

**Prerequisites:** Python 3.8+

```bash
# 1. Clone
git clone https://github.com/nasserx/OnePortfolio.git
cd OnePortfolio

# 2. Virtual environment
python -m venv venv
source venv/bin/activate        # Linux/Mac
.\venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run
python app.py
```

Open `http://localhost:5000` — the first registered account automatically becomes admin.

> **Dev tip:** Set `DEV_AUTO_LOGIN=1` in your environment to skip the login screen and auto-login as the first user during development.

## 🔧 Configuration

Set the following environment variables (in `.env` or your hosting platform's WSGI file):

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | ✅ | Flask session signing key — generate with `secrets.token_hex(32)` |
| `EMAIL_USER` | ✅ | Gmail address used to send verification and reset emails |
| `EMAIL_PASSWORD` | ✅ | Gmail App Password (requires 2FA enabled on the account) |
| `APP_BASE_URL` | ✅ | Public URL of your app (e.g. `https://yourapp.pythonanywhere.com`) |
| `DATABASE_URL` | — | SQLAlchemy URI — defaults to `sqlite:///portfolio.db` |
| `SESSION_COOKIE_SECURE` | — | Set to `1` when serving over HTTPS |
| `DEV_AUTO_LOGIN` | — | Set to `1` to auto-login as the first user (development only) |

> **Note:** Gmail requires an [App Password](https://myaccount.google.com/apppasswords) — your regular password will not work.

## 📁 Project Structure

```
OnePortfolio/
├── app.py                  # Development entry point (localhost:5000, debug=True)
├── wsgi.py                 # Production WSGI entry point (PythonAnywhere)
├── config.py               # Configuration settings
├── requirements.txt        # Python dependencies
├── test_app.py             # Test suite
└── portfolio_app/
    ├── __init__.py         # App factory & idempotent DB migrations
    ├── models/             # SQLAlchemy models (User, Portfolio, Transaction, Asset, Dividend, ClosedTrade, PortfolioEvent)
    ├── repositories/       # Data access layer (filtered by user_id)
    ├── services/           # Business logic (auth, portfolio, transaction, ...)
    ├── calculators/        # P&L, average cost, and dashboard calculators
    ├── forms/              # Custom form validation (base_form.py + Flask-WTF CSRF)
    ├── routes/             # Flask blueprints (dashboard, portfolios, transactions, charts, ...)
    ├── utils/              # Helpers (email, tokens, formatting, constants)
    ├── static/             # CSS (style.css with Material Design 3 tokens) and JS (main.js)
    └── templates/          # Jinja2 HTML templates
```

### Architecture

The app follows a layered clean architecture pattern:

```
Routes (Blueprints) → Services → Repositories → Models (SQLAlchemy)
        ↓                ↓
   Forms (validation)  Calculators (financial math)
```

All services and repositories are resolved via a `get_services()` factory (dependency injection through Flask's `g`) — routes never instantiate services directly.

## 🖼️ Screenshots

### Landing Page
![Landing Page](screenshots/landing.png)

## 🧪 Testing

```bash
# Run all tests
pytest -v

# Run a single test
pytest -v test_app.py::test_name
```

CI runs automatically on every push via GitHub Actions across Python 3.8, 3.10, and 3.12.

## 🚀 Deployment

### PythonAnywhere

```bash
# 1. Clone your repo
git clone https://github.com/nasserx/OnePortfolio.git

# 2. Create and activate virtualenv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

In the **WSGI file** on PythonAnywhere, set environment variables and point to the app factory:

```python
activate_this = '/home/YOUR_USERNAME/.virtualenvs/myenv/bin/activate_this.py'
with open(activate_this) as f:
    exec(f.read(), {'__file__': activate_this})

import os
os.environ['SECRET_KEY']            = 'your-secret-key'
os.environ['EMAIL_USER']            = 'your-gmail@gmail.com'
os.environ['EMAIL_PASSWORD']        = 'your-app-password'
os.environ['APP_BASE_URL']          = 'https://yourapp.pythonanywhere.com'
os.environ['SESSION_COOKIE_SECURE'] = '1'

from portfolio_app import create_app
application = create_app()
```

Then click **Reload** in the Web tab.

> **Note:** PythonAnywhere free accounts only allow outbound connections to whitelisted hosts. Use Gmail SMTP (`smtp.gmail.com:587`) which is supported.

## 🎯 Roadmap

- [x] Multi-user authentication with email verification
- [x] Password reset via email
- [x] Dividend income tracking
- [x] Realized P&L with Average Cost Method
- [x] Portfolio management with deposit/withdraw audit trail
- [x] Account settings with self-service deletion
- [x] Dark / light mode with Material Design 3 tokens
- [x] Paginated transaction and portfolio event views
- [x] Charts page
- [ ] Live market price integration
- [ ] Docker deployment support
- [ ] Export to CSV / Excel

## 📝 License

MIT — see [LICENSE](LICENSE) for details.

**nasserx** · [@nasserx](https://github.com/nasserx)

---

> ⚠️ **Disclaimer:** This project is for educational and organizational purposes only. It does not provide financial advice.
