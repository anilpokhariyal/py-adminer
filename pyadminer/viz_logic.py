"""Read-only visualization and profiling queries (validated identifiers only)."""

from __future__ import annotations

import json
from typing import Any

from pyadminer.db import fetch_all, run_sql
from pyadminer.validators import (
    mysql_column_type_is_json,
    mysql_column_type_is_numeric,
    mysql_column_type_is_temporal,
    quote_ident,
    validate_mysql_identifier,
)

AGGREGATES = frozenset({"SUM", "AVG", "COUNT", "MIN", "MAX"})

# Re-export for routes / templates context building
is_numeric_column_type = mysql_column_type_is_numeric
is_temporal_column_type = mysql_column_type_is_temporal
is_json_column_type = mysql_column_type_is_json


def _scalar(
    conn, sql: str, params: tuple | list | dict | None = None
) -> tuple[Any | None, str | None]:
    cur, err = run_sql(conn, sql, params, store_error=False)
    if err:
        return None, err
    if not cur:
        return None, "empty"
    rows = fetch_all(cur)
    if not rows:
        return None, None
    return next(iter(rows[0].values())), None


def get_column_type(conn, database: str, table: str, column: str) -> str | None:
    validate_mysql_identifier(database)
    validate_mysql_identifier(table)
    validate_mysql_identifier(column)
    run_sql(conn, "USE information_schema;")
    cur, err = run_sql(
        conn,
        "SELECT COLUMN_TYPE FROM COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
        "AND COLUMN_NAME=%s",
        (database, table, column),
        store_error=False,
    )
    if err or not cur:
        return None
    rows = fetch_all(cur)
    return rows[0]["COLUMN_TYPE"] if rows else None


def column_profile(conn, database: str, table: str, column: str) -> dict[str, Any]:
    ct = get_column_type(conn, database, table, column)
    if not ct:
        return {"error": "Unknown column"}

    validate_mysql_identifier(database)
    qdb = quote_ident(database)
    qt = quote_ident(table)
    qc = quote_ident(column)

    run_sql(conn, f"USE {qdb};")
    total, e1 = _scalar(conn, f"SELECT COUNT(*) AS c FROM {qt}")
    non_null, e2 = _scalar(conn, f"SELECT COUNT({qc}) AS c FROM {qt}")
    distinct, e3 = _scalar(conn, f"SELECT COUNT(DISTINCT {qc}) AS c FROM {qt}")

    null_count = None
    if total is not None and non_null is not None:
        null_count = int(total) - int(non_null)

    out: dict[str, Any] = {
        "column": column,
        "column_type": ct,
        "row_count": int(total) if total is not None else None,
        "non_null_count": int(non_null) if non_null is not None else None,
        "null_count": null_count,
        "distinct_count": int(distinct) if distinct is not None else None,
        "errors": [x for x in (e1, e2, e3) if x],
    }
    if out["row_count"] is not None and out["row_count"] > 0 and null_count is not None:
        out["null_pct"] = round(100.0 * null_count / out["row_count"], 3)

    if mysql_column_type_is_numeric(ct) or mysql_column_type_is_temporal(ct):
        mn, _ = _scalar(conn, f"SELECT MIN({qc}) AS m FROM {qt} WHERE {qc} IS NOT NULL")
        mx, _ = _scalar(conn, f"SELECT MAX({qc}) AS m FROM {qt} WHERE {qc} IS NOT NULL")
        out["min"] = mn
        out["max"] = mx

    samples_cur, serr = run_sql(
        conn,
        f"SELECT {qc} AS v FROM {qt} WHERE {qc} IS NOT NULL LIMIT 5",
        store_error=False,
    )
    if serr or not samples_cur:
        out["samples"] = []
    else:
        raw = [r["v"] for r in fetch_all(samples_cur)]
        out["samples"] = [_sample_repr(v) for v in raw]

    return out


def _sample_repr(v: Any) -> Any:
    if isinstance(v, (bytes, bytearray, memoryview)):
        return f"<binary {len(v)} bytes>"
    if isinstance(v, str) and v.strip().startswith(("{", "[")):
        try:
            return json.loads(v)
        except (json.JSONDecodeError, TypeError):
            pass
    return v


def chart_categorical(
    conn, database: str, table: str, column: str, *, limit: int = 25
) -> dict[str, Any]:
    validate_mysql_identifier(database)
    validate_mysql_identifier(table)
    validate_mysql_identifier(column)
    lim = max(1, min(int(limit), 100))
    qdb = quote_ident(database)
    qt = quote_ident(table)
    qc = quote_ident(column)
    run_sql(conn, f"USE {qdb};")
    sql = f"SELECT {qc} AS k, COUNT(*) AS c FROM {qt} GROUP BY {qc} ORDER BY c DESC LIMIT {lim}"
    cur, err = run_sql(conn, sql, store_error=False)
    if err or not cur:
        return {"error": err or "query failed", "labels": [], "values": []}
    rows = fetch_all(cur)
    labels = []
    values = []
    for r in rows:
        k = r["k"]
        labels.append(str(k) if k is not None else "(NULL)")
        values.append(int(r["c"]))
    return {"labels": labels, "values": values}


def chart_timeseries(
    conn, database: str, table: str, column: str, *, limit: int = 90
) -> dict[str, Any]:
    ct = get_column_type(conn, database, table, column)
    if not ct:
        return {"error": "Unknown column"}
    if not mysql_column_type_is_temporal(ct):
        return {"error": "Column is not a date/time type"}

    validate_mysql_identifier(database)
    validate_mysql_identifier(table)
    validate_mysql_identifier(column)
    lim = max(1, min(int(limit), 366))
    qdb = quote_ident(database)
    qt = quote_ident(table)
    qc = quote_ident(column)
    run_sql(conn, f"USE {qdb};")
    sql = (
        f"SELECT DATE({qc}) AS d, COUNT(*) AS c FROM {qt} WHERE {qc} IS NOT NULL "
        f"GROUP BY DATE({qc}) ORDER BY d ASC LIMIT {lim}"
    )
    cur, err = run_sql(conn, sql, store_error=False)
    if err or not cur:
        return {"error": err or "query failed", "labels": [], "values": []}
    rows = fetch_all(cur)
    labels = [str(r["d"]) for r in rows]
    values = [int(r["c"]) for r in rows]
    return {"labels": labels, "values": values}


def chart_scatter(
    conn,
    database: str,
    table: str,
    column_x: str,
    column_y: str,
    *,
    limit: int = 500,
) -> dict[str, Any]:
    ctx = get_column_type(conn, database, table, column_x)
    cty = get_column_type(conn, database, table, column_y)
    if not ctx or not cty:
        return {"error": "Unknown column"}
    if not (mysql_column_type_is_numeric(ctx) and mysql_column_type_is_numeric(cty)):
        return {"error": "Scatter requires two numeric columns"}

    validate_mysql_identifier(database)
    validate_mysql_identifier(table)
    validate_mysql_identifier(column_x)
    validate_mysql_identifier(column_y)
    lim = max(1, min(int(limit), 5_000))
    qdb = quote_ident(database)
    qt = quote_ident(table)
    qx = quote_ident(column_x)
    qy = quote_ident(column_y)
    run_sql(conn, f"USE {qdb};")
    sql = (
        f"SELECT {qx} AS x, {qy} AS y FROM {qt} "
        f"WHERE {qx} IS NOT NULL AND {qy} IS NOT NULL LIMIT {lim}"
    )
    cur, err = run_sql(conn, sql, store_error=False)
    if err or not cur:
        return {"error": err or "query failed", "points": []}
    rows = fetch_all(cur)
    points = []
    for r in rows:
        try:
            points.append({"x": float(r["x"]), "y": float(r["y"])})
        except (TypeError, ValueError):
            continue
    return {"points": points}


def pivot_aggregate(
    conn,
    database: str,
    table: str,
    row_column: str,
    col_column: str,
    value_column: str,
    agg: str,
    *,
    limit: int = 2000,
) -> dict[str, Any]:
    a = (agg or "").strip().upper()
    if a not in AGGREGATES:
        return {"error": "Invalid aggregate"}

    validate_mysql_identifier(database)
    validate_mysql_identifier(table)
    validate_mysql_identifier(row_column)
    validate_mysql_identifier(col_column)
    validate_mysql_identifier(value_column)
    if len({row_column, col_column, value_column}) < 3:
        return {"error": "Row, column, and value must differ"}

    lim = max(1, min(int(limit), 5_000))
    qdb = quote_ident(database)
    qt = quote_ident(table)
    qr = quote_ident(row_column)
    qc = quote_ident(col_column)
    qv = quote_ident(value_column)

    run_sql(conn, f"USE {qdb};")
    sql = f"SELECT {qr} AS r, {qc} AS c, {a}({qv}) AS v FROM {qt} GROUP BY {qr}, {qc} LIMIT {lim}"
    cur, err = run_sql(conn, sql, store_error=False)
    if err or not cur:
        return {"error": err or "query failed", "cells": []}
    rows = fetch_all(cur)
    cells = []
    for r in rows:
        v = r["v"]
        if v is None:
            jv = None
        elif isinstance(v, (int, float)):
            jv = float(v)
        else:
            try:
                jv = float(v)
            except (TypeError, ValueError):
                jv = str(v)
        cells.append({"r": r["r"], "c": r["c"], "v": jv})
    return {"cells": cells}


def fk_incoming(conn, database: str, table: str) -> list[dict[str, Any]]:
    validate_mysql_identifier(database)
    validate_mysql_identifier(table)
    run_sql(conn, "USE information_schema;")
    cur, err = run_sql(
        conn,
        "SELECT TABLE_NAME, COLUMN_NAME, CONSTRAINT_NAME, REFERENCED_COLUMN_NAME "
        "FROM KEY_COLUMN_USAGE WHERE REFERENCED_TABLE_SCHEMA=%s AND REFERENCED_TABLE_NAME=%s "
        "ORDER BY TABLE_NAME, COLUMN_NAME",
        (database, table),
        store_error=False,
    )
    if err or not cur:
        return []
    return fetch_all(cur)


def views_referencing(conn, database: str, table: str) -> list[dict[str, Any]]:
    validate_mysql_identifier(database)
    validate_mysql_identifier(table)
    run_sql(conn, "USE information_schema;")
    pattern = f"%{table}%"
    cur, err = run_sql(
        conn,
        "SELECT TABLE_NAME AS view_name FROM VIEWS WHERE TABLE_SCHEMA=%s "
        "AND VIEW_DEFINITION LIKE %s ORDER BY TABLE_NAME",
        (database, pattern),
        store_error=False,
    )
    if err or not cur:
        return []
    return fetch_all(cur)


def routines_referencing(conn, database: str, table: str) -> list[dict[str, Any]]:
    validate_mysql_identifier(database)
    validate_mysql_identifier(table)
    run_sql(conn, "USE information_schema;")
    pattern = f"%{table}%"
    cur, err = run_sql(
        conn,
        "SELECT ROUTINE_NAME, ROUTINE_TYPE FROM ROUTINES WHERE ROUTINE_SCHEMA=%s "
        "AND ROUTINE_DEFINITION LIKE %s ORDER BY ROUTINE_NAME",
        (database, pattern),
        store_error=False,
    )
    if err or not cur:
        return []
    return fetch_all(cur)


def pk_duplicate_rows(
    conn, database: str, table: str, pk_cols: list[str]
) -> tuple[list[dict[str, Any]], str | None]:
    if not pk_cols:
        return [], "No primary key on this table."
    for c in pk_cols:
        validate_mysql_identifier(c)
    validate_mysql_identifier(database)
    validate_mysql_identifier(table)
    qcols = ", ".join(quote_ident(c) for c in pk_cols)
    qt = quote_ident(table)
    run_sql(conn, f"USE {quote_ident(database)};")
    sql = (
        f"SELECT {qcols}, COUNT(*) AS __dup_count FROM {qt} GROUP BY {qcols} "
        "HAVING COUNT(*) > 1 ORDER BY COUNT(*) DESC LIMIT 20"
    )
    cur, err = run_sql(conn, sql, store_error=False)
    if err or not cur:
        return [], err
    return fetch_all(cur), None


def fk_orphan_count(
    conn,
    database: str,
    child_table: str,
    child_column: str,
    parent_schema: str,
    parent_table: str,
    parent_column: str,
) -> tuple[int | None, str | None]:
    for name in (
        database,
        child_table,
        child_column,
        parent_schema,
        parent_table,
        parent_column,
    ):
        validate_mysql_identifier(name)
    qdb = quote_ident(database)
    qchild = quote_ident(child_table)
    qcc = quote_ident(child_column)
    qps = quote_ident(parent_schema)
    qpt = quote_ident(parent_table)
    qpc = quote_ident(parent_column)
    run_sql(conn, f"USE {qdb};")
    sql = (
        f"SELECT COUNT(*) AS c FROM {qchild} AS ch "
        f"LEFT JOIN {qps}.{qpt} AS p ON ch.{qcc} = p.{qpc} "
        f"WHERE ch.{qcc} IS NOT NULL AND p.{qpc} IS NULL"
    )
    val, err = _scalar(conn, sql)
    if err:
        return None, err
    return int(val) if val is not None else 0, None


def list_table_columns(conn, database: str, table: str) -> set[str]:
    validate_mysql_identifier(database)
    validate_mysql_identifier(table)
    run_sql(conn, "USE information_schema;")
    cur, err = run_sql(
        conn,
        "SELECT COLUMN_NAME FROM COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
        (database, table),
        store_error=False,
    )
    if err or not cur:
        return set()
    return {r["COLUMN_NAME"] for r in fetch_all(cur)}


def table_diff_summary(conn, database: str, table_a: str, table_b: str) -> dict[str, Any]:
    validate_mysql_identifier(database)
    validate_mysql_identifier(table_a)
    validate_mysql_identifier(table_b)

    cols_a = list_table_columns(conn, database, table_a)
    cols_b = list_table_columns(conn, database, table_b)
    shared = sorted(cols_a & cols_b)
    only_a = sorted(cols_a - cols_b)
    only_b = sorted(cols_b - cols_a)

    qdb = quote_ident(database)
    qta = quote_ident(table_a)
    qtb = quote_ident(table_b)
    run_sql(conn, f"USE {qdb};")
    na, e1 = _scalar(conn, f"SELECT COUNT(*) AS c FROM {qta}")
    nb, e2 = _scalar(conn, f"SELECT COUNT(*) AS c FROM {qtb}")

    out: dict[str, Any] = {
        "table_a": table_a,
        "table_b": table_b,
        "row_count_a": int(na) if na is not None else None,
        "row_count_b": int(nb) if nb is not None else None,
        "shared_columns": shared,
        "columns_only_a": only_a,
        "columns_only_b": only_b,
        "errors": [x for x in (e1, e2) if x],
        "except_a_not_b": None,
        "except_b_not_a": None,
    }

    if shared and not only_a and not only_b:
        sql_ab = f"(SELECT * FROM {qta} EXCEPT SELECT * FROM {qtb}) AS x"
        sql_ba = f"(SELECT * FROM {qtb} EXCEPT SELECT * FROM {qta}) AS y"
        ca, err_ab = _scalar(conn, f"SELECT COUNT(*) AS c FROM {sql_ab}")
        if err_ab:
            out["except_note"] = "Row-level EXCEPT not available or failed on this server."
        else:
            cb, err_ba = _scalar(conn, f"SELECT COUNT(*) AS c FROM {sql_ba}")
            out["except_a_not_b"] = int(ca) if ca is not None else None
            out["except_b_not_a"] = int(cb) if cb is not None and not err_ba else None

    return out
