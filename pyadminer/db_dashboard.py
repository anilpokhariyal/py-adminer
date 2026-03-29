"""Per-table health heuristics and standard (non-AI) performance hints."""

from __future__ import annotations

from typing import Any

from pyadminer.db import fetch_all, get_primary_key_columns, run_sql
from pyadminer.validators import validate_mysql_identifier


def _fmt_bytes(n: Any) -> str:
    if n is None:
        return "—"
    try:
        b = int(n)
    except (TypeError, ValueError):
        return "—"
    if b < 1024:
        return f"{b} B"
    if b < 1024 * 1024:
        return f"{b / 1024:.1f} KB"
    if b < 1024**3:
        return f"{b / (1024 * 1024):.1f} MB"
    return f"{b / (1024**3):.2f} GB"


def _index_leading_columns(conn, database: str, table: str) -> dict[str, list[str]]:
    """INDEX_NAME -> ordered column names."""
    cur, _ = run_sql(
        conn,
        "SELECT INDEX_NAME, COLUMN_NAME, SEQ_IN_INDEX FROM STATISTICS "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY INDEX_NAME, SEQ_IN_INDEX",
        (database, table),
        store_error=False,
    )
    if not cur:
        return {}
    idx: dict[str, list[str]] = {}
    for row in fetch_all(cur):
        name = row["INDEX_NAME"]
        col = row["COLUMN_NAME"]
        seq = int(row["SEQ_IN_INDEX"] or 0)
        if name not in idx:
            idx[name] = []
        while len(idx[name]) < seq:
            idx[name].append("")
        idx[name][seq - 1] = col
    return {k: [c for c in v if c] for k, v in idx.items()}


def _fk_outbound_columns(conn, database: str, table: str) -> list[str]:
    cur, _ = run_sql(
        conn,
        "SELECT DISTINCT COLUMN_NAME FROM KEY_COLUMN_USAGE "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND REFERENCED_TABLE_NAME IS NOT NULL",
        (database, table),
        store_error=False,
    )
    if not cur:
        return []
    return [r["COLUMN_NAME"] for r in fetch_all(cur)]


def _has_leading_index_on_column(index_map: dict[str, list[str]], column: str) -> bool:
    for cols in index_map.values():
        if cols and cols[0] == column:
            return True
    return False


def _count_wide_columns(conn, database: str, table: str) -> int:
    cur, _ = run_sql(
        conn,
        "SELECT COLUMN_TYPE FROM COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
        (database, table),
        store_error=False,
    )
    if not cur:
        return 0
    n = 0
    for row in fetch_all(cur):
        ct = (row.get("COLUMN_TYPE") or "").lower()
        if any(
            ct.startswith(p)
            for p in (
                "tinytext",
                "text",
                "mediumtext",
                "longtext",
                "tinyblob",
                "blob",
                "mediumblob",
                "longblob",
                "json",
            )
        ):
            n += 1
        elif ct.startswith("varchar("):
            try:
                inner = ct[8:].split(")", 1)[0]
                ln = int(inner)
                if ln >= 768:
                    n += 1
            except (ValueError, IndexError):
                pass
    return n


def _analyze_base_table(conn, database: str, row: dict[str, Any]) -> dict[str, Any]:
    table = row["TABLE_NAME"]
    engine = (row.get("ENGINE") or "") or "—"
    eng_l = engine.lower()
    rows_est = int(row.get("TABLE_ROWS") or 0)
    data_b = int(row.get("DATA_LENGTH") or 0)
    idx_b = int(row.get("INDEX_LENGTH") or 0)
    coll = row.get("TABLE_COLLATION") or ""

    suggestions: list[str] = []
    pk = get_primary_key_columns(conn, database, table)
    has_pk = bool(pk)

    if eng_l and eng_l not in ("innodb", "memory", "blackhole", "csv"):
        suggestions.append(
            f"Storage engine `{engine}`: prefer InnoDB for FKs, transactions, and crash safety."
        )

    if eng_l == "innodb" and not has_pk:
        suggestions.append(
            "No PRIMARY KEY on InnoDB table: add one for clustered index order, "
            "replication, and tooling."
        )

    if coll and coll.startswith("utf8") and not coll.startswith("utf8mb4"):
        suggestions.append(
            "Table collation is legacy utf8 (3-byte); consider utf8mb4 for full Unicode."
        )

    idx_map = _index_leading_columns(conn, database, table)
    for fk_col in _fk_columns_without_index(conn, database, table, idx_map):
        suggestions.append(
            f"FK column `{fk_col}` has no index leading with that column; "
            "add one if you filter/join on it."
        )

    if rows_est > 100_000 and data_b > 10 * 1024 * 1024 and idx_b < data_b * 0.03:
        suggestions.append(
            "Large table with small index footprint vs data; review filters, JOIN keys, "
            "and covering indexes."
        )

    if idx_b > 0 and data_b > 0 and idx_b > data_b * 2.5:
        suggestions.append(
            "Index size much larger than data; check redundant indexes and very wide "
            "indexed VARCHARs."
        )

    wide = _count_wide_columns(conn, database, table)
    if wide >= 6:
        suggestions.append(
            "Many wide TEXT/BLOB/VARCHAR columns; consider vertical splits for rarely read "
            "large fields."
        )

    if rows_est > 500_000 and eng_l == "innodb" and has_pk and not suggestions:
        suggestions.append(
            "High row count: monitor buffer pool hit rate and slow query log for this table."
        )

    health = "good"
    if suggestions:
        health = "review"
    if eng_l == "innodb" and not has_pk:
        health = "attention"

    return {
        "table": table,
        "kind": "BASE TABLE",
        "engine": engine,
        "rows_estimate": rows_est,
        "data_bytes": data_b,
        "index_bytes": idx_b,
        "data_human": _fmt_bytes(data_b),
        "index_human": _fmt_bytes(idx_b),
        "has_primary_key": has_pk,
        "collation": coll or "—",
        "suggestions_standard": suggestions
        or ["No standard checks flagged issues (still validate with EXPLAIN and metrics)."],
        "health_label": health,
    }


def _fk_columns_without_index(
    conn,
    database: str,
    table: str,
    idx_map: dict[str, list[str]],
) -> list[str]:
    out: list[str] = []
    for col in _fk_outbound_columns(conn, database, table):
        if not _has_leading_index_on_column(idx_map, col):
            out.append(col)
    return out


def _view_row(row: dict[str, Any]) -> dict[str, Any]:
    table = row["TABLE_NAME"]
    return {
        "table": table,
        "kind": "VIEW",
        "engine": row.get("ENGINE") or "—",
        "rows_estimate": "—",
        "data_bytes": 0,
        "index_bytes": 0,
        "data_human": "—",
        "index_human": "—",
        "has_primary_key": True,
        "collation": row.get("TABLE_COLLATION") or "—",
        "suggestions_standard": [
            "Views follow underlying tables; tune base tables, indexes, and the view SQL text."
        ],
        "health_label": "info",
    }


def build_database_dashboard(conn, database: str) -> list[dict[str, Any]]:
    validate_mysql_identifier(database)
    run_sql(conn, "USE information_schema;")
    tcur, err = run_sql(
        conn,
        "SELECT TABLE_NAME, TABLE_TYPE, ENGINE, TABLE_ROWS, DATA_LENGTH, INDEX_LENGTH, "
        "AUTO_INCREMENT, TABLE_COLLATION, TABLE_COMMENT FROM TABLES WHERE TABLE_SCHEMA=%s "
        "ORDER BY TABLE_NAME",
        (database,),
        store_error=False,
    )
    if err or not tcur:
        return []
    out: list[dict[str, Any]] = []
    for row in fetch_all(tcur):
        tname = row["TABLE_NAME"]
        try:
            validate_mysql_identifier(tname)
        except ValueError:
            continue
        ttype = (row.get("TABLE_TYPE") or "BASE TABLE").upper()
        if ttype == "VIEW":
            out.append(_view_row(row))
        else:
            out.append(_analyze_base_table(conn, database, row))
    return out


def compact_for_ai_payload(rows: list[dict[str, Any]], *, limit: int = 28) -> list[dict[str, Any]]:
    """Trim dashboard rows for LLM context."""
    payload: list[dict[str, Any]] = []
    for r in rows:
        if r.get("kind") != "BASE TABLE":
            continue
        std = r.get("suggestions_standard") or []
        payload.append(
            {
                "table": r["table"],
                "engine": r.get("engine"),
                "rows_estimate": r.get("rows_estimate"),
                "data_bytes": r.get("data_bytes"),
                "index_bytes": r.get("index_bytes"),
                "has_primary_key": r.get("has_primary_key"),
                "standard_hints": std[:6],
            }
        )
        if len(payload) >= limit:
            break
    return payload
