# Claude Code guidance

Read and follow [AGENTS.md](AGENTS.md). It is the project-level instruction
source, including financial correctness, tenant isolation and the canonical
UI design reference. Existing local components are not design authority;
visual acceptance belongs to the user.

## Project references

- [Architecture](docs/ARCHITECTURE.md): routes, services, repositories,
  canonical snapshots, mutation ownership, audit history and authentication.
- [Domain and calculations](docs/DOMAIN_AND_CALCULATIONS.md): the canonical
  financial glossary and accounting formulas.
- [Financial read models](docs/FINANCIAL_READ_MODEL.md): exact persistence,
  arithmetic, coherent read snapshots and API contracts.
- [Migrations](docs/MIGRATIONS.md): schema 40, supported upgrade history,
  startup coordination and account-lifetime session identities.
- [Development](docs/DEVELOPMENT.md): setup, configuration, isolated tests
  and automated validation commands.
- [Design system](docs/DESIGN_SYSTEM.md): frontend implementation guidance;
  inspect the actual preset before UI changes as required by AGENTS.md.

Keep implementation details in these authoritative documents rather than
maintaining a second architecture or accounting description here.

## Entry points and tests

`app.py` starts the local development application; `wsgi.py` exposes
`application = create_app()` for deployment. Both can create/migrate the
configured database, so do not import them for diagnostics against user data.

Install development dependencies with `python -m pip install -r requirements-dev.txt`.
Run `python -m pytest -v`, or `python -m pytest -v tests/test_app.py::test_name`
for a focused test. Use the JavaScript assertion and syntax commands in
[Development](docs/DEVELOPMENT.md#validation-commands). There is no configured
Python lint tool.
