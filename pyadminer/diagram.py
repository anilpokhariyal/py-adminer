"""Load schema from MySQL information_schema and produce Mermaid ER diagram text."""

from __future__ import annotations

from typing import Any

from pyadminer.db import fetch_all, run_sql
from pyadminer.diagram_build import build_mermaid_er_diagram, group_foreign_keys
from pyadminer.validators import validate_mysql_identifier


def fetch_mermaid_diagram(
    connection,
    database: str,
    *,
    max_tables_warn: int = 80,
) -> tuple[str, list[str]]:
    """
    Load tables, columns, and FKs from information_schema.
    Returns Mermaid source and warnings.
    """
    warnings: list[str] = []
    validate_mysql_identifier(database)

    run_sql(connection, "USE information_schema;")
    tcur, terr = run_sql(
        connection,
        "SELECT TABLE_NAME, TABLE_TYPE FROM TABLES WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME",
        (database,),
        store_error=False,
    )
    if terr or not tcur:
        return "", [f"Could not read tables: {terr or 'unknown'}"]

    table_rows = fetch_all(tcur)
    valid_tables: list[str] = []
    table_types: dict[str, str] = {}
    for r in table_rows:
        tn = r.get("TABLE_NAME")
        try:
            validate_mysql_identifier(str(tn))
        except (ValueError, TypeError):
            warnings.append(f"Skipped invalid table name: {tn!r}")
            continue
        valid_tables.append(str(tn))
        table_types[str(tn)] = str(r.get("TABLE_TYPE") or "BASE TABLE")

    if len(valid_tables) > max_tables_warn:
        warnings.append(
            f"Large schema ({len(valid_tables)} objects). "
            "Diagram may be slow; export .mmd to edit externally."
        )

    tables_cols: dict[str, list[dict[str, Any]]] = {t: [] for t in valid_tables}

    ccur, cerr = run_sql(
        connection,
        "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, COLUMN_KEY, EXTRA "
        "FROM COLUMNS WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME, ORDINAL_POSITION",
        (database,),
        store_error=False,
    )
    if not cerr and ccur:
        for r in fetch_all(ccur):
            tn = r.get("TABLE_NAME")
            if tn in tables_cols:
                tables_cols[str(tn)].append(dict(r))

    fkcur, fkerr = run_sql(
        connection,
        "SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, "
        "REFERENCED_COLUMN_NAME, CONSTRAINT_NAME, ORDINAL_POSITION "
        "FROM KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=%s AND REFERENCED_TABLE_NAME IS NOT NULL "
        "AND REFERENCED_TABLE_SCHEMA = %s "
        "ORDER BY CONSTRAINT_NAME, ORDINAL_POSITION",
        (database, database),
        store_error=False,
    )
    fk_rows: list[dict[str, Any]] = []
    if not fkerr and fkcur:
        fk_rows = fetch_all(fkcur)

    valid_set = set(tables_cols.keys())
    fk_groups = [
        g
        for g in group_foreign_keys(fk_rows)
        if g["child"] in valid_set and g["parent"] in valid_set
    ]
    if not fk_groups and valid_tables:
        warnings.append(
            "No foreign keys found in information_schema. Tables are shown with columns only; "
            "add FK constraints in MySQL to see relationship lines."
        )

    mermaid = build_mermaid_er_diagram(tables_cols, fk_groups, table_types)
    return mermaid, warnings
