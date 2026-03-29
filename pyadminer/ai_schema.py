"""Build compact schema text for LLM prompts."""

from __future__ import annotations

from pyadminer.db import fetch_all, run_sql
from pyadminer.validators import validate_mysql_identifier


def fetch_schema_for_nl(
    conn,
    database: str,
    focus_table: str | None = None,
    *,
    max_tables: int = 55,
    max_cols_per_table: int = 40,
    max_chars: int = 28_000,
) -> str:
    validate_mysql_identifier(database)
    if focus_table:
        validate_mysql_identifier(focus_table)
    max_tables = max(1, min(int(max_tables), 200))
    max_cols_per_table = max(1, min(int(max_cols_per_table), 200))

    run_sql(conn, "USE information_schema;")
    tcur, _ = run_sql(
        conn,
        "SELECT TABLE_NAME, TABLE_TYPE FROM TABLES WHERE TABLE_SCHEMA=%s "
        "AND TABLE_TYPE IN ('BASE TABLE','VIEW') ORDER BY TABLE_NAME",
        (database,),
        store_error=False,
    )
    if not tcur:
        return f"Database `{database}`: (could not list tables)"
    all_rows = fetch_all(tcur)
    names = [r["TABLE_NAME"] for r in all_rows]
    ordered: list[str] = []
    if focus_table and focus_table in names:
        ordered.append(focus_table)
    for n in names:
        if n not in ordered:
            ordered.append(n)
    ordered = ordered[:max_tables]

    lines: list[str] = [f"Database: `{database}`", "Tables:"]
    total = 0
    for tname in ordered:
        validate_mysql_identifier(tname)
        ccur, _ = run_sql(
            conn,
            "SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_KEY "
            "FROM COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
            "ORDER BY ORDINAL_POSITION",
            (database, tname),
            store_error=False,
        )
        cols = fetch_all(ccur) if ccur else []
        cols = cols[:max_cols_per_table]
        col_bits = []
        for c in cols:
            cn = c["COLUMN_NAME"]
            ct = c.get("COLUMN_TYPE") or ""
            nn = c.get("IS_NULLABLE")
            ck = c.get("COLUMN_KEY") or ""
            bits = f"`{cn}` {ct}"
            if ck == "PRI":
                bits += " PK"
            if nn == "NO":
                bits += " NOT NULL"
            col_bits.append(bits)
        chunk = f"\n- `{tname}`: " + "; ".join(col_bits)
        if total + len(chunk) > max_chars:
            lines.append("\n… (schema truncated for size)")
            break
        lines.append(chunk)
        total += len(chunk)

    return "".join(lines)
