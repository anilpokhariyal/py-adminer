# PyAdminer vs Adminer / phpMyAdmin — feature gaps

This is a high-level checklist. PyAdminer targets a **MySQL-only**, **Flask + server-rendered** admin UI similar in spirit to [Adminer](https://www.adminer.org/) (single-file PHP) and [phpMyAdmin](https://www.phpmyadmin.net/).

## Recently aligned with Adminer-style DB view

- **Empty database**: database-level actions (new table, alter database, SQL) are shown even when `TABLES` is empty (previously hidden because the template required a non-empty table list).

## Present in PyAdminer

- Connect with server/user/password/database
- List databases (sizes, collations)
- Create / rename (alter path) / drop databases
- List tables, table structure (columns, indexes, FKs)
- Browse data with filters, order, limit
- Edit / delete rows (by primary key)
- Raw SQL panel
- Export table as CSV or SQL INSERTs
- CSRF, read-only mode, optional Basic Auth, rate limits (see improvement plan)

## Common in Adminer / phpMyAdmin, missing or partial here

| Area | Adminer / phpMyAdmin | PyAdminer |
|------|----------------------|-----------|
| **Engines** | PostgreSQL, SQLite, … | MySQL only |
| **Import** | SQL/CSV upload | Not implemented |
| **Routine SQL** | `SHOW CREATE TABLE`, triggers, events, views, procedures | Partial (raw SQL only; no dedicated UI) |
| **User / privileges** | Grant UI | Not implemented |
| **Search** | Search all tables in DB | Per-table filters only |
| **Copy / move table** | Yes | Not implemented |
| **Table maintenance** | Optimize, repair, check | Not implemented |
| **Designer / relations graph** | phpMyAdmin | Not implemented |
| **Query builder** | Some | Not implemented |
| **Bookmarks / history** | phpMyAdmin | Not implemented |
| **Two-factor / SSO** | Varies | Optional Basic Auth only |
| **BLOB preview / upload** | Yes | Basic text fields in forms |
| **Multi-server bookmarks** | Adminer | Session per browser only |

## Practical next steps (if you want parity)

1. **Import** — file upload + execute SQL or `LOAD DATA` (with strict size limits and confirmation).
2. **Table ops** — drop table, truncate, empty, `SHOW CREATE TABLE` page.
3. **Routines** — list views/triggers/procedures from `information_schema`.
4. **Global search** — optional slow path across tables with limits.

Pull requests welcome for any of the above.
