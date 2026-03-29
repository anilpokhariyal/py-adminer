# PyAdminer — improvement plan (implemented)

This document summarizes the industry-oriented upgrades applied to the project. The codebase is a Flask web UI for MySQL (Adminer-style browsing, structure, data, SQL panel).

## Security baseline

- Removed unsafe `eval()` on collation input; collations are selected as `charset|collation` strings and validated.
- CSRF protection (Flask-WTF) on forms; AJAX delete sends `X-CSRFToken`.
- Dynamic SQL uses validated identifiers (`[a-zA-Z0-9_]{1,64}`) and parameterized clauses for search filters and row delete/update.
- `SECRET_KEY` and `DEBUG` come from environment (`SECRET_KEY`, `FLASK_DEBUG`).
- `CREATE TABLE` submissions are restricted to DDL that starts with `CREATE TABLE` and references the submitted table name.

## Engineering

- Application factory (`create_app`), package layout under `pyadminer/`, blueprint `main`.
- `pyproject.toml` with runtime and `[dev]` extras; `LICENSE` (MIT); `.gitignore` extended.
- Docker image installs MySQL client dev libraries for `mysqlclient`; `EXPOSE 5000` matches the app port.
- `/health` JSON endpoint for probes.

## Quality

- `pytest` for validators, `/health`, and optional MySQL integration (`MYSQL_TEST_*`).
- `ruff` in CI.
- GitHub Actions workflow: Ubuntu, MySQL 8 service, install `default-libmysqlclient-dev`, run ruff + pytest.

## Product

- Table structure view includes **indexes** (`information_schema.STATISTICS`) and **foreign keys** (`KEY_COLUMN_USAGE`).
- Row **edit/delete** use real **primary keys** (including composite); JSON payload / hidden `pk_json`.
- **Export** table as CSV or SQL (`/export/csv` and `/export/sql`).
- **Database diagram** (Mermaid ER) and **Advanced** panel: views, routines, triggers, events (with safe drop helpers where applicable).
- **Visualization** (`viz` query param): column **profile** API, **charts** (categorical, time series, scatter), **pivot** `GROUP BY`; **Impact** (incoming FKs, views/routines mentioning the table), **Quality** (PK duplicate groups, FK orphan counts), **Diff** (column overlap and optional `EXCEPT` row counts).
- **Data** grid: optional **numeric heatmap**, **JSON** and long-text **expand** cells.
- **AI assistant** (optional): settings page for provider, API key, model, and enable/disable; **natural language → suggested `SELECT`** on the SQL panel (OpenAI, Anthropic, or OpenAI-compatible API). Encrypted settings file under `instance/` (or `PYADMINER_AI_SETTINGS_PATH`). Server can force-disable with `PYADMINER_AI_DISABLE`.
- **Activity log** UI for JSON audit tail + download; sidebar navigation uses `url_for` so links work from `/py_adminer/audit_log` and `/py_adminer/ai_settings`.

## Hardening (optional via env)

- `PYADMINER_READ_ONLY=true` blocks mutating routes and mutating SQL in the SQL panel (prefix check).
- `PYADMINER_AUTH_USERNAME` / `PYADMINER_AUTH_PASSWORD` enable HTTP Basic Auth in front of the app.
- `RATELIMIT_ENABLED`, `RATELIMIT_STORAGE_URI` (Flask-Limiter); limits on destructive or heavy POST routes.
- `pyadminer.audit` logger records exports, DDL, SQL execution (truncated), drops, etc.

## Environment reference

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Flask session signing (required in production) |
| `FLASK_DEBUG` | `1` / `true` for debug |
| `FLASK_RUN_HOST`, `FLASK_RUN_PORT` | Dev server bind |
| `MYSQL_PORT` | Default MySQL port for sessions (default 3306) |
| `PYADMINER_READ_ONLY` | Read-only mode |
| `PYADMINER_AUTH_USERNAME` / `PYADMINER_AUTH_PASSWORD` | Optional Basic Auth |
| `RATELIMIT_ENABLED`, `RATELIMIT_STORAGE_URI` | Rate limiting |
| `PYADMINER_AUDIT_LOG_PATH`, `PYADMINER_AUDIT_MAX_QUERY_CHARS` | Audit log file path and per-line SQL cap |
| `PYADMINER_AI_DISABLE`, `PYADMINER_AI_SETTINGS_PATH` | Disable AI globally; custom encrypted settings path |
| `PYADMINER_DEFAULT_MYSQL_HOST` | Prefill MySQL host on login form |
| `MYSQL_TEST_*` | Integration tests in CI |
