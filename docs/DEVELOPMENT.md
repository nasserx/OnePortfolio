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

Fill `.env` with local values. Do not commit `.env`.

## Running the App

```bash
python app.py
```

Open `http://127.0.0.1:5000`.

For local development only, `DEV_AUTO_LOGIN=1` can auto-login as the first user. Never enable it outside local development.

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

- Realized P&L remains sell-only.
- Income remains separate.
- Total Cash includes income.
- Book Value includes income through Total Cash.
- Positions do not change because of income.
- Return includes realized P&L plus income.

For UI changes, check desktop and narrow viewports and confirm text does not overlap or overflow.

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
