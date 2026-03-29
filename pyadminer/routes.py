from __future__ import annotations

import csv
import io
import json
import os
import re
import zipfile
from functools import wraps

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_wtf.csrf import generate_csrf

from pyadminer import viz_logic as viz_logic
from pyadminer.ai_routes import register_ai_routes
from pyadminer.ai_storage import is_ai_assistant_available
from pyadminer.audit import audit_event, get_audit_log_path, read_audit_entries
from pyadminer.db import (
    fetch_all,
    format_mysql_error,
    get_primary_key_columns,
    get_table_column_names,
    mysql_config,
    mysql_connection,
    run_sql,
)
from pyadminer.db_dashboard import build_database_dashboard, compact_for_ai_payload
from pyadminer.diagram import fetch_mermaid_diagram
from pyadminer.extensions import limiter
from pyadminer.validators import (
    ALLOWED_SEARCH_OPS,
    column_in_set,
    parse_collation_pair,
    quote_ident,
    sql_looks_mutating,
    validate_limit,
    validate_mysql_identifier,
    validate_order_direction,
    view_definition_allowed,
)
from pyadminer.viz_routes import register_viz_routes

bp = Blueprint("main", __name__)

_CONNECT_FAILED_MSG = (
    "Could not connect to MySQL. If PyAdminer runs in Docker Compose, set Server to "
    "the database service name (e.g. mysql), not localhost."
)

_LIST_DATABASES_SQL = (
    "SELECT s.SCHEMA_NAME, s.DEFAULT_COLLATION_NAME, "
    "COALESCE(tagg.TABLES_COUNT, 0) AS TABLES_COUNT, "
    "COALESCE(tagg.SCHEMA_SIZE, 0) AS SCHEMA_SIZE "
    "FROM information_schema.SCHEMATA s "
    "LEFT JOIN ( "
    "  SELECT TABLE_SCHEMA, "
    "    COUNT(TABLE_NAME) AS TABLES_COUNT, "
    "    SUM(DATA_LENGTH) AS SCHEMA_SIZE "
    "  FROM information_schema.TABLES "
    "  GROUP BY TABLE_SCHEMA "
    ") tagg ON tagg.TABLE_SCHEMA = s.SCHEMA_NAME"
)

_ALLOWED_AUDIT_SCAN_KB = (128, 256, 512, 1024, 2048, 4096)

_EXPORT_ROW_LIMIT = 100_000

_VIZ_MODES = frozenset({"visualize", "impact", "quality", "diff"})


def _insert_lines_from_rows(rows: list, table: str) -> list[str]:
    """Build INSERT statements for table export (same rules as single-table SQL export)."""
    import MySQLdb

    if not rows:
        return []
    keys = list(rows[0].keys())
    qtbl = quote_ident(table)
    lines: list[str] = []
    for row in rows:
        cols = ", ".join(quote_ident(k) for k in keys)
        lit: list[str] = []
        for k in keys:
            v = row.get(k)
            if v is None:
                lit.append("NULL")
            elif isinstance(v, (bytes, bytearray, memoryview)):
                lit.append(f"0x{bytes(v).hex()}")
            else:
                raw = str(v).encode("utf-8", errors="replace")
                esc = MySQLdb.escape_string(raw).decode("utf-8")
                lit.append(f"'{esc}'")
        lines.append(f"INSERT INTO {qtbl} ({cols}) VALUES ({', '.join(lit)});")
    return lines


def _list_base_tables(conn, database: str) -> list[str]:
    run_sql(conn, "USE information_schema;")
    cur, _ = run_sql(
        conn,
        "SELECT TABLE_NAME FROM TABLES WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE' "
        "ORDER BY TABLE_NAME",
        (database,),
    )
    if not cur:
        return []
    out: list[str] = []
    for r in fetch_all(cur):
        t = r["TABLE_NAME"]
        try:
            validate_mysql_identifier(t)
            out.append(t)
        except ValueError:
            continue
    return out


def _database_sql_dump_body(conn, database: str) -> str:
    """Full DB as SQL: USE + INSERTs per table (row cap per table)."""
    tables = _list_base_tables(conn, database)
    parts = [
        f"-- PyAdminer database export `{database}`",
        "-- Row cap per table: " + str(_EXPORT_ROW_LIMIT) + " (increase in code if you need more).",
        "SET NAMES utf8mb4;",
        "SET FOREIGN_KEY_CHECKS=0;",
        f"USE {quote_ident(database)};",
    ]
    for tname in tables:
        run_sql(conn, f"USE {quote_ident(database)};")
        q = f"SELECT * FROM {quote_ident(tname)} LIMIT {_EXPORT_ROW_LIMIT}"
        cur, err = run_sql(conn, q, store_error=False)
        parts.append(f"\n-- Table {quote_ident(tname)}")
        if err or not cur:
            parts.append(f"-- Skipped (read error): {err or 'no cursor'}")
            continue
        rows = fetch_all(cur)
        parts.append(f"-- Rows: {len(rows)}")
        parts.extend(_insert_lines_from_rows(rows, tname))
    parts.append("\nSET FOREIGN_KEY_CHECKS=1;\n")
    return "\n".join(parts) + "\n"


def _list_databases_and_version(connection):
    """Sidebar database list + server version (same query as main admin)."""
    databases: list = []
    mysql_version = 0
    cur, _ = run_sql(connection, "USE information_schema;")
    if not cur:
        return databases, mysql_version
    dcur, _ = run_sql(connection, _LIST_DATABASES_SQL)
    databases = fetch_all(dcur) if dcur else []
    vcur, _ = run_sql(connection, "SELECT VERSION() AS version")
    if vcur:
        rows = fetch_all(vcur)
        mysql_version = rows[0] if rows else 0
    return databases, mysql_version


def _limiter_disabled() -> bool:
    return not current_app.config.get("RATELIMIT_ENABLED", True)


def _read_only() -> bool:
    return bool(current_app.config.get("PYADMINER_READ_ONLY"))


def read_only_guard(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if _read_only():
            if request.is_json:
                return jsonify({"error": "Read-only mode"}), 403
            session["error"] = "Read-only mode is enabled."
            return redirect(request.referrer or "/py_adminer")
        return f(*args, **kwargs)

    return wrapped


def _require_mysql_session():
    if session.get("system") != "mysql":
        return None
    try:
        mysql_config(current_app)
        return mysql_connection()
    except Exception as exc:
        current_app.logger.warning("MySQL connection failed: %s", exc)
        detail = format_mysql_error(exc)
        session["error"] = f"{_CONNECT_FAILED_MSG} ({detail})" if detail else _CONNECT_FAILED_MSG
        for key in ("system", "host", "user", "password", "database", "pass"):
            session.pop(key, None)
        return None


def _validate_create_table_ddl(sql: str, expected_table: str) -> bool:
    s = (sql or "").strip()
    if not re.match(r"(?is)^CREATE\s+TABLE\s+", s):
        return False
    validate_mysql_identifier(expected_table)
    if f"`{expected_table}`" not in s and not re.search(
        rf"(?is)CREATE\s+TABLE\s+`?{re.escape(expected_table)}`?\b", s
    ):
        return False
    return True


def _build_search_where(
    connection,
    database: str,
    table: str,
    search_by: list,
    expression: list,
    search_value: list,
) -> tuple[str, list]:
    allowed_cols = get_table_column_names(connection, database, table)
    if not allowed_cols:
        return "", []
    parts: list[str] = []
    params: list = []
    allowed_set = set(allowed_cols)
    for i in range(len(search_value)):
        val = search_value[i] if i < len(search_value) else ""
        if (
            not val
            and i < len(expression)
            and expression[i]
            not in (
                "IS NULL",
                "IS NOT NULL",
            )
        ):
            continue
        if i >= len(search_by) or i >= len(expression):
            continue
        col = column_in_set(search_by[i], allowed_set)
        op = expression[i]
        if op not in ALLOWED_SEARCH_OPS:
            continue
        qcol = quote_ident(col)
        if op == "IS NULL":
            parts.append(f"{qcol} IS NULL")
        elif op == "IS NOT NULL":
            parts.append(f"{qcol} IS NOT NULL")
        elif op == "IN":
            vals = [x.strip() for x in val.split(",") if x.strip()]
            if not vals:
                continue
            ph = ", ".join(["%s"] * len(vals))
            parts.append(f"{qcol} IN ({ph})")
            params.extend(vals)
        elif op == "NOT IN":
            vals = [x.strip() for x in val.split(",") if x.strip()]
            if not vals:
                continue
            ph = ", ".join(["%s"] * len(vals))
            parts.append(f"{qcol} NOT IN ({ph})")
            params.extend(vals)
        elif op == "FIND_IN_SET":
            parts.append(f"FIND_IN_SET(%s, {qcol})")
            params.append(val)
        elif op == "LIKE %%":
            parts.append(f"{qcol} LIKE %s")
            params.append(f"%{val}%")
        else:
            parts.append(f"{qcol} {op} %s")
            params.append(val)
    if not parts:
        return "", []
    return " WHERE " + " AND ".join(parts), params


@bp.route("/", methods=["GET", "POST"])
def home():
    return redirect(url_for("main.py_admin"))


@bp.route("/create_database", methods=["POST"])
@read_only_guard
@limiter.limit("30 per minute", methods=["POST"], exempt_when=_limiter_disabled)
def create_database():
    conn = _require_mysql_session()
    if not conn:
        return redirect(url_for("main.py_admin"))

    try:
        db_name = validate_mysql_identifier(request.form.get("database_name", ""))
    except ValueError:
        session["error"] = "Invalid database name."
        return redirect(url_for("main.py_admin"))

    alter_raw = request.form.get("alter_db_name") or ""
    alter_db = None
    if alter_raw and alter_raw != "None":
        try:
            alter_db = validate_mysql_identifier(alter_raw)
        except ValueError:
            session["error"] = "Invalid alter database name."
            return redirect(url_for("main.py_admin"))

    pair = parse_collation_pair(request.form.get("database_collection"))
    if pair:
        charset, collation = pair
        create_sql = (
            f"CREATE DATABASE {quote_ident(db_name)} "
            f"CHARACTER SET {quote_ident(charset)} COLLATE {quote_ident(collation)};"
        )
    else:
        create_sql = f"CREATE DATABASE {quote_ident(db_name)};"

    _, err = run_sql(conn, create_sql)
    if err:
        audit_event("create_database_failed", db_name, query=create_sql)
        return redirect(url_for("main.py_admin"))

    audit_event("create_database", db_name, query=create_sql)

    if alter_db and alter_db != db_name:
        run_sql(conn, "USE information_schema;")
        tcur, _ = run_sql(
            conn,
            "SELECT TABLE_NAME FROM TABLES WHERE TABLE_SCHEMA = %s",
            (alter_db,),
        )
        tables = fetch_all(tcur) if tcur else []
        run_sql(conn, f"USE {quote_ident(alter_db)};")
        for table in tables:
            tname = table["TABLE_NAME"]
            try:
                validate_mysql_identifier(tname)
            except ValueError:
                continue
            run_sql(
                conn,
                f"RENAME TABLE {quote_ident(alter_db)}.{quote_ident(tname)} "
                f"TO {quote_ident(db_name)}.{quote_ident(tname)};",
            )
        run_sql(conn, f"DROP DATABASE {quote_ident(alter_db)};")
        audit_event("rename_database", f"{alter_db}->{db_name}")

    return redirect(url_for("main.py_admin"))


@bp.route("/drop_database", methods=["POST"])
@read_only_guard
@limiter.limit("20 per minute", methods=["POST"], exempt_when=_limiter_disabled)
def drop_database():
    conn = _require_mysql_session()
    if not conn:
        return redirect(url_for("main.py_admin"))
    for name in request.form.getlist("db_name"):
        try:
            dbn = validate_mysql_identifier(name)
        except ValueError:
            continue
        run_sql(conn, f"DROP DATABASE {quote_ident(dbn)};")
        audit_event("drop_database", dbn, query=f"DROP DATABASE {quote_ident(dbn)};")
    return redirect(url_for("main.py_admin"))


@bp.route("/create_table", methods=["POST"])
@read_only_guard
@limiter.limit("30 per minute", methods=["POST"], exempt_when=_limiter_disabled)
def create_table():
    database = request.form.get("database")
    table_name = request.form.get("table_name")
    conn = _require_mysql_session()
    if not conn:
        return redirect(url_for("main.py_admin"))
    try:
        validate_mysql_identifier(database or "")
        validate_mysql_identifier(table_name or "")
    except ValueError:
        session["error"] = "Invalid database or table name."
        return redirect("/py_adminer")

    ddl = request.form.get("create_table_query") or ""
    if not _validate_create_table_ddl(ddl, table_name or ""):
        session["error"] = "Only CREATE TABLE for the named table is allowed."
        return redirect(f"/py_adminer?database={database}")

    run_sql(conn, f"USE {quote_ident(database)};")
    _, err = run_sql(conn, ddl)
    if not err:
        audit_event("create_table", f"{database}.{table_name}", query=ddl)
    return redirect(f"/py_adminer?database={database}&table={table_name}")


@bp.route("/delete_table_row", methods=["POST"])
@bp.route("/delete_table_row_by_id", methods=["POST"])
@read_only_guard
@limiter.limit("60 per minute", methods=["POST"], exempt_when=_limiter_disabled)
def delete_table_row():
    """Delete row by primary key JSON object."""
    data = request.get_json(silent=True) or {}
    conn = _require_mysql_session()
    if not conn:
        return jsonify({"error": "Unauthorized"}), 401
    database = data.get("database")
    table_name = data.get("table_name")
    pk = data.get("pk")
    if not isinstance(pk, dict) or not pk:
        return jsonify({"error": "Missing primary key"}), 400
    try:
        validate_mysql_identifier(database)
        validate_mysql_identifier(table_name)
    except ValueError:
        return jsonify({"error": "Invalid identifier"}), 400

    pk_cols = get_primary_key_columns(conn, database, table_name)
    if not pk_cols:
        return jsonify({"error": "Table has no primary key"}), 400
    if set(pk.keys()) != set(pk_cols):
        return jsonify({"error": "Primary key mismatch"}), 400

    where_parts = [f"{quote_ident(c)} = %s" for c in pk_cols]
    params = [pk[c] for c in pk_cols]
    sql = f"DELETE FROM {quote_ident(table_name)} WHERE " + " AND ".join(where_parts)
    run_sql(conn, f"USE {quote_ident(database)};")
    _, err = run_sql(conn, sql, tuple(params))
    if err:
        return jsonify({"error": err}), 400
    audit_event("delete_row", f"{database}.{table_name}", query=sql)
    return jsonify({"status": "success", "msg": "Row deleted."})


@bp.route("/update_table_data", methods=["POST"])
@read_only_guard
def update_table_data():
    conn = _require_mysql_session()
    if not conn:
        return redirect(url_for("main.py_admin"))
    database = request.form.get("database")
    table_name = request.form.get("table_name")
    pk_raw = request.form.get("pk_json")
    try:
        validate_mysql_identifier(database or "")
        validate_mysql_identifier(table_name or "")
        pk = json.loads(pk_raw or "{}")
        if not isinstance(pk, dict):
            raise ValueError
    except (ValueError, json.JSONDecodeError, TypeError):
        session["error"] = "Invalid update payload."
        return redirect(f"/py_adminer?database={database}&table={table_name}&action=data")

    pk_cols = get_primary_key_columns(conn, database, table_name)
    if not pk_cols or set(pk.keys()) != set(pk_cols):
        session["error"] = "Invalid primary key for update."
        return redirect(f"/py_adminer?database={database}&table={table_name}&action=data")

    run_sql(conn, "USE information_schema;")
    cur, _ = run_sql(
        conn,
        "SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE FROM COLUMNS "
        "WHERE TABLE_NAME=%s AND TABLE_SCHEMA=%s ORDER BY ORDINAL_POSITION",
        (table_name, database),
    )
    table_columns = fetch_all(cur) if cur else []

    set_parts: list[str] = []
    params: list = []
    for column in table_columns:
        cname = column["COLUMN_NAME"]
        if cname in pk_cols:
            continue
        raw_val = request.form.get(cname)
        if raw_val is None or raw_val == "":
            if column.get("IS_NULLABLE") == "YES":
                set_parts.append(f"{quote_ident(cname)} = NULL")
            else:
                set_parts.append(f"{quote_ident(cname)} = %s")
                params.append("")
        else:
            set_parts.append(f"{quote_ident(cname)} = %s")
            params.append(raw_val)

    where_parts = [f"{quote_ident(c)} = %s" for c in pk_cols]
    params.extend(pk[c] for c in pk_cols)

    if not set_parts:
        return redirect(f"/py_adminer?database={database}&table={table_name}&action=data")

    sql = (
        f"UPDATE {quote_ident(table_name)} SET "
        + ", ".join(set_parts)
        + " WHERE "
        + " AND ".join(where_parts)
    )
    run_sql(conn, f"USE {quote_ident(database)};")
    run_sql(conn, sql, tuple(params))
    audit_event("update_row", f"{database}.{table_name}", query=sql)
    return redirect(f"/py_adminer?database={database}&table={table_name}&action=data")


@bp.route("/export/<string:fmt>")
def export_table(fmt: str):
    conn = _require_mysql_session()
    if not conn:
        return redirect(url_for("main.py_admin"))
    database = request.args.get("database")
    table_name = request.args.get("table")
    try:
        validate_mysql_identifier(database or "")
        validate_mysql_identifier(table_name or "")
    except ValueError:
        abort(400)

    run_sql(conn, f"USE {quote_ident(database)};")
    export_sql_q = f"SELECT * FROM {quote_ident(table_name)} LIMIT {_EXPORT_ROW_LIMIT}"
    cur, err = run_sql(conn, export_sql_q, store_error=False)
    if err or not cur:
        abort(500)
    rows = fetch_all(cur)
    if fmt == "csv":
        output = io.StringIO()
        if not rows:
            writer = csv.writer(output)
            writer.writerow([])
        else:
            writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        audit_event("export_csv", f"{database}.{table_name}", query=export_sql_q)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={table_name}.csv",
            },
        )
    if fmt == "sql":
        lines = [
            f"-- PyAdminer export {database}.{table_name}",
            f"USE `{database}`;",
        ]
        lines.extend(_insert_lines_from_rows(rows, table_name))
        body = "\n".join(lines) + "\n"
        audit_event("export_sql", f"{database}.{table_name}", query=export_sql_q)
        return Response(
            body,
            mimetype="text/plain",
            headers={
                "Content-Disposition": f"attachment; filename={table_name}.sql",
            },
        )
    abort(404)


@bp.route("/export_database/diagram_mmd", methods=["GET"])
@limiter.limit("30 per minute", exempt_when=_limiter_disabled)
def export_diagram_mmd():
    """Download Mermaid source for the database ER diagram."""
    conn = _require_mysql_session()
    if not conn:
        return redirect(url_for("main.py_admin"))
    database = request.args.get("database") or ""
    try:
        validate_mysql_identifier(database)
    except ValueError:
        abort(400)
    text, _warn = fetch_mermaid_diagram(conn, database)
    body = text if text.strip() else "erDiagram\n    %% empty schema\n"
    audit_event("export_diagram_mmd", database)
    safe_name = database.replace("/", "_").replace("\\", "_")
    return Response(
        body,
        mimetype="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}_diagram.mmd"',
        },
    )


@bp.route("/export_database/sql", methods=["GET"])
@limiter.limit("30 per minute", exempt_when=_limiter_disabled)
def export_database_sql():
    """Download all base tables in a database as a single .sql file (INSERTs, row cap per table)."""
    conn = _require_mysql_session()
    if not conn:
        return redirect(url_for("main.py_admin"))
    database = request.args.get("database") or ""
    try:
        validate_mysql_identifier(database)
    except ValueError:
        abort(400)
    body = _database_sql_dump_body(conn, database)
    audit_event(
        "export_database_sql",
        database,
        query=f"-- all base tables, LIMIT {_EXPORT_ROW_LIMIT} per table",
    )
    safe_name = database.replace("/", "_").replace("\\", "_")
    return Response(
        body,
        mimetype="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}_export.sql"',
        },
    )


@bp.route("/export_databases", methods=["POST"])
@limiter.limit("10 per minute", methods=["POST"], exempt_when=_limiter_disabled)
def export_databases_zip():
    """ZIP of one .sql file per selected database (same format as export_database_sql)."""
    conn = _require_mysql_session()
    if not conn:
        return redirect(url_for("main.py_admin"))
    names_in = request.form.getlist("db_name")
    validated: list[str] = []
    for name in names_in:
        try:
            validated.append(validate_mysql_identifier(name))
        except ValueError:
            continue
    if not validated:
        session["error"] = "Select at least one database to export."
        return redirect(url_for("main.py_admin"))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for dbn in validated:
            sql_text = _database_sql_dump_body(conn, dbn)
            safe = dbn.replace("/", "_").replace("\\", "_")
            zf.writestr(f"{safe}.sql", sql_text.encode("utf-8"))
    buf.seek(0)
    audit_event("export_databases_zip", ",".join(validated))
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name="pyadminer-databases-export.zip",
    )


_MAX_VIEW_DEFINITION_CHARS = 500_000


def _redirect_database_advanced(database: str):
    return redirect(url_for("main.py_admin", database=database, advanced=1))


@bp.route("/create_view", methods=["POST"])
@read_only_guard
@limiter.limit("30 per minute", methods=["POST"], exempt_when=_limiter_disabled)
def create_database_view():
    conn = _require_mysql_session()
    if not conn:
        return redirect(url_for("main.py_admin"))
    database = request.form.get("database") or ""
    view_name = request.form.get("view_name") or ""
    body = (request.form.get("view_definition") or "").strip().rstrip(";")
    try:
        validate_mysql_identifier(database)
        validate_mysql_identifier(view_name)
    except ValueError:
        session["error"] = "Invalid database or view name."
        return redirect(url_for("main.py_admin"))
    if len(body) > _MAX_VIEW_DEFINITION_CHARS:
        session["error"] = "View definition is too long."
        return _redirect_database_advanced(database)
    if not view_definition_allowed(body):
        session["error"] = "View definition must start with SELECT or WITH (single statement)."
        return _redirect_database_advanced(database)
    run_sql(conn, f"USE {quote_ident(database)};")
    sql = f"CREATE OR REPLACE VIEW {quote_ident(view_name)} AS {body}"
    _, err = run_sql(conn, sql)
    if not err:
        audit_event("create_view", f"{database}.{view_name}", query=sql)
    return _redirect_database_advanced(database)


@bp.route("/drop_view", methods=["POST"])
@read_only_guard
@limiter.limit("60 per minute", methods=["POST"], exempt_when=_limiter_disabled)
def drop_database_view():
    conn = _require_mysql_session()
    if not conn:
        return redirect(url_for("main.py_admin"))
    database = request.form.get("database") or ""
    view_name = request.form.get("view_name") or ""
    try:
        validate_mysql_identifier(database)
        validate_mysql_identifier(view_name)
    except ValueError:
        session["error"] = "Invalid database or view name."
        return redirect(url_for("main.py_admin"))
    run_sql(conn, f"USE {quote_ident(database)};")
    sql = f"DROP VIEW IF EXISTS {quote_ident(view_name)}"
    _, err = run_sql(conn, sql)
    if not err:
        audit_event("drop_view", f"{database}.{view_name}", query=sql)
    return _redirect_database_advanced(database)


@bp.route("/drop_routine", methods=["POST"])
@read_only_guard
@limiter.limit("60 per minute", methods=["POST"], exempt_when=_limiter_disabled)
def drop_database_routine():
    conn = _require_mysql_session()
    if not conn:
        return redirect(url_for("main.py_admin"))
    database = request.form.get("database") or ""
    routine_name = request.form.get("routine_name") or ""
    rtype = (request.form.get("routine_type") or "").upper()
    if rtype not in ("PROCEDURE", "FUNCTION"):
        session["error"] = "Invalid routine type."
        return redirect(url_for("main.py_admin"))
    try:
        validate_mysql_identifier(database)
        validate_mysql_identifier(routine_name)
    except ValueError:
        session["error"] = "Invalid database or routine name."
        return redirect(url_for("main.py_admin"))
    run_sql(conn, f"USE {quote_ident(database)};")
    sql = f"DROP {rtype} IF EXISTS {quote_ident(routine_name)}"
    _, err = run_sql(conn, sql)
    if not err:
        audit_event("drop_routine", f"{database}.{routine_name} ({rtype})", query=sql)
    return _redirect_database_advanced(database)


@bp.route("/drop_trigger", methods=["POST"])
@read_only_guard
@limiter.limit("60 per minute", methods=["POST"], exempt_when=_limiter_disabled)
def drop_database_trigger():
    conn = _require_mysql_session()
    if not conn:
        return redirect(url_for("main.py_admin"))
    database = request.form.get("database") or ""
    trigger_name = request.form.get("trigger_name") or ""
    try:
        validate_mysql_identifier(database)
        validate_mysql_identifier(trigger_name)
    except ValueError:
        session["error"] = "Invalid database or trigger name."
        return redirect(url_for("main.py_admin"))
    run_sql(conn, f"USE {quote_ident(database)};")
    sql = f"DROP TRIGGER IF EXISTS {quote_ident(trigger_name)}"
    _, err = run_sql(conn, sql)
    if not err:
        audit_event("drop_trigger", f"{database}.{trigger_name}", query=sql)
    return _redirect_database_advanced(database)


@bp.route("/drop_event", methods=["POST"])
@read_only_guard
@limiter.limit("60 per minute", methods=["POST"], exempt_when=_limiter_disabled)
def drop_database_event():
    conn = _require_mysql_session()
    if not conn:
        return redirect(url_for("main.py_admin"))
    database = request.form.get("database") or ""
    event_name = request.form.get("event_name") or ""
    try:
        validate_mysql_identifier(database)
        validate_mysql_identifier(event_name)
    except ValueError:
        session["error"] = "Invalid database or event name."
        return redirect(url_for("main.py_admin"))
    run_sql(conn, f"USE {quote_ident(database)};")
    sql = f"DROP EVENT IF EXISTS {quote_ident(event_name)}"
    _, err = run_sql(conn, sql)
    if not err:
        audit_event("drop_event", f"{database}.{event_name}", query=sql)
    return _redirect_database_advanced(database)


@bp.route("/py_adminer", methods=["GET", "POST"])
@limiter.limit("120 per minute", methods=["POST"], exempt_when=_limiter_disabled)
def py_admin():
    databases: list = []
    db_collations: dict = {}
    tables: list = []
    table_structure: list = []
    table_indexes: list = []
    table_foreign_keys: list = []
    table_data: list = []
    primary_keys: list[str] = []
    search_by: list = []
    expression: list = []
    search_value: list = []
    data_query = ""
    order_by = ""
    order = "asc"
    limit = 1000
    table_columns: list = []
    db_engines: list = []
    mysql_version = 0
    login = False
    selected_db = None
    selected_table = None
    action = request.values.get("action", None)
    _viz_arg = (request.args.get("viz") or "").strip().lower()
    viz_mode = _viz_arg if _viz_arg in _VIZ_MODES else ""
    create = request.values.get("create", None)
    sql_panel = request.values.get("sql_panel", None)
    sql_query = request.values.get("sql_query", None)
    query_output = []
    _adv = request.values.get("advanced") or request.args.get("advanced") or ""
    advanced_panel = bool(str(_adv).strip())
    _dia = request.values.get("diagram") or request.args.get("diagram") or ""
    diagram_panel = bool(str(_dia).strip())
    _dash = request.values.get("dashboard") or request.args.get("dashboard") or ""
    dashboard_panel = bool(str(_dash).strip())
    mermaid_diagram = ""
    diagram_warnings: list[str] = []
    dashboard_rows: list = []
    dashboard_ai_payload: list = []
    db_views: list = []
    db_routines: list = []
    db_triggers: list = []
    db_events: list = []
    viz_impact: dict = {"incoming": [], "views": [], "routines": []}
    viz_quality: dict = {"pk_duplicates": [], "pk_error": None, "fk_orphans": []}
    viz_diff: dict | None = None
    viz_diff_table = ""
    numeric_column_names: list[str] = []
    json_column_names: list[str] = []
    wide_text_column_names: list[str] = []
    if "pass" in session:
        login = True

    if request.method == "POST" and "pass" not in session:
        session["system"] = request.values.get("system", "mysql")
        session["host"] = request.values.get("server", "localhost")
        session["user"] = request.values.get("username")
        session["password"] = request.values.get("password")
        session["database"] = request.values.get("database")
        login_ok = False
        try:
            mysql_config(current_app)
            conn = mysql_connection()
            ping, ping_err = run_sql(conn, "SELECT 1 AS _pyadminer_ping", store_error=False)
            if ping_err:
                session["error"] = format_mysql_error(ping_err)
            elif ping is None:
                session["error"] = "Could not verify connection (empty result from server)."
            else:
                login_ok = True
        except Exception as exc:
            session["error"] = format_mysql_error(exc)

        if not login_ok:
            for key in ("system", "host", "user", "password", "database", "pass"):
                session.pop(key, None)
        else:
            audit_event(
                "login",
                "user="
                + (request.values.get("username") or "")
                + " host="
                + (request.values.get("server") or ""),
            )
            db_arg = (request.values.get("database") or "").strip()
            if db_arg:
                return redirect(url_for("main.py_admin", database=db_arg))
            return redirect(url_for("main.py_admin"))

    if session.get("system") == "mysql":
        connection = _require_mysql_session()
        if connection is None:
            return redirect(url_for("main.py_admin"))

        arg_database = None
        arg_table = None
        if request.args.get("database"):
            try:
                arg_database = validate_mysql_identifier(str(request.args.get("database")))
            except ValueError:
                session["error"] = "Invalid database name in URL."
        if request.args.get("table"):
            try:
                arg_table = validate_mysql_identifier(str(request.args.get("table")))
            except ValueError:
                session["error"] = "Invalid table name in URL."

        cur, _ = run_sql(connection, "USE information_schema;")
        if not cur:
            pass
        else:
            databases, mysql_version = _list_databases_and_version(connection)

        if arg_database and create:
            selected_db = arg_database

        if create or action == "alter":
            run_sql(connection, "USE information_schema;")
            coll_cur, _ = run_sql(connection, "SELECT * FROM COLLATIONS ORDER BY SORTLEN ASC")
            all_collations = fetch_all(coll_cur) if coll_cur else []
            for collation in all_collations:
                cset = collation["CHARACTER_SET_NAME"]
                if cset in db_collations:
                    db_collations[cset].append(collation)
                else:
                    db_collations[cset] = [collation]
            run_sql(connection, "USE information_schema;")
            eng_cur, _ = run_sql(connection, "SELECT * FROM ENGINES")
            db_engines = fetch_all(eng_cur) if eng_cur else []

        if arg_database and not create:
            selected_db = arg_database
            run_sql(connection, "USE information_schema;")
            tcur, _ = run_sql(
                connection,
                "SELECT TABLE_NAME, ENGINE, TABLE_ROWS, DATA_LENGTH, INDEX_LENGTH,"
                " AUTO_INCREMENT, TABLE_COLLATION, TABLE_COMMENT "
                "FROM TABLES WHERE TABLE_SCHEMA = %s",
                (arg_database,),
            )
            tables = fetch_all(tcur) if tcur else []

            if advanced_panel and not sql_panel and not diagram_panel and not dashboard_panel:
                run_sql(connection, "USE information_schema;")
                vcur, _ = run_sql(
                    connection,
                    "SELECT TABLE_NAME AS view_name FROM VIEWS WHERE TABLE_SCHEMA=%s "
                    "ORDER BY TABLE_NAME",
                    (selected_db,),
                )
                db_views = fetch_all(vcur) if vcur else []
                rcur, _ = run_sql(
                    connection,
                    "SELECT ROUTINE_NAME, ROUTINE_TYPE FROM ROUTINES WHERE ROUTINE_SCHEMA=%s "
                    "ORDER BY ROUTINE_NAME",
                    (selected_db,),
                )
                db_routines = fetch_all(rcur) if rcur else []
                trcur, _ = run_sql(
                    connection,
                    "SELECT TRIGGER_NAME, EVENT_MANIPULATION, EVENT_OBJECT_TABLE "
                    "FROM TRIGGERS WHERE TRIGGER_SCHEMA=%s ORDER BY TRIGGER_NAME",
                    (selected_db,),
                )
                db_triggers = fetch_all(trcur) if trcur else []
                ecur, _ = run_sql(
                    connection,
                    "SELECT EVENT_NAME, INTERVAL_VALUE, INTERVAL_FIELD, STATUS "
                    "FROM EVENTS WHERE EVENT_SCHEMA=%s ORDER BY EVENT_NAME",
                    (selected_db,),
                    store_error=False,
                )
                db_events = fetch_all(ecur) if ecur else []

            if diagram_panel and not sql_panel and not dashboard_panel:
                try:
                    mermaid_diagram, diagram_warnings = fetch_mermaid_diagram(
                        connection, selected_db
                    )
                except ValueError:
                    mermaid_diagram = ""
                    diagram_warnings = ["Invalid database name for diagram."]

            if dashboard_panel and not sql_panel and not advanced_panel and not diagram_panel:
                try:
                    dashboard_rows = build_database_dashboard(connection, selected_db)
                    dashboard_ai_payload = compact_for_ai_payload(dashboard_rows)
                except ValueError:
                    dashboard_rows = []
                    dashboard_ai_payload = []

        if selected_db and arg_table and (not action or action == "alter" or viz_mode):
            table_name = arg_table
            selected_table = table_name
            run_sql(connection, "USE information_schema;")
            s_cur, _ = run_sql(
                connection,
                (
                    "SELECT COLUMN_NAME,IS_NULLABLE,COLUMN_DEFAULT,COLUMN_TYPE,"
                    "COLUMN_KEY,EXTRA,COLUMN_COMMENT FROM COLUMNS "
                    "WHERE TABLE_NAME=%s AND TABLE_SCHEMA=%s ORDER BY ORDINAL_POSITION"
                ),
                (table_name, selected_db),
            )
            table_structure = fetch_all(s_cur) if s_cur else []
            primary_keys = get_primary_key_columns(connection, selected_db, table_name)

            idx_cur, _ = run_sql(
                connection,
                "SELECT INDEX_NAME, NON_UNIQUE, COLUMN_NAME, SEQ_IN_INDEX, INDEX_TYPE, COLLATION "
                "FROM STATISTICS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
                "ORDER BY INDEX_NAME, SEQ_IN_INDEX",
                (selected_db, table_name),
            )
            table_indexes = fetch_all(idx_cur) if idx_cur else []

            fk_cur, _ = run_sql(
                connection,
                "SELECT CONSTRAINT_NAME, COLUMN_NAME, REFERENCED_TABLE_SCHEMA, "
                "REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME "
                "FROM KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
                "AND REFERENCED_TABLE_NAME IS NOT NULL",
                (selected_db, table_name),
            )
            table_foreign_keys = fetch_all(fk_cur) if fk_cur else []

            if viz_mode == "impact":
                viz_impact["incoming"] = viz_logic.fk_incoming(connection, selected_db, table_name)
                viz_impact["views"] = viz_logic.views_referencing(
                    connection, selected_db, table_name
                )
                viz_impact["routines"] = viz_logic.routines_referencing(
                    connection, selected_db, table_name
                )

            if viz_mode == "quality":
                dups, pk_err = viz_logic.pk_duplicate_rows(
                    connection, selected_db, table_name, primary_keys
                )
                viz_quality["pk_duplicates"] = dups
                viz_quality["pk_error"] = pk_err
                orphans: list[dict] = []
                for fk in table_foreign_keys or []:
                    cnt, oerr = viz_logic.fk_orphan_count(
                        connection,
                        selected_db,
                        table_name,
                        fk["COLUMN_NAME"],
                        fk["REFERENCED_TABLE_SCHEMA"],
                        fk["REFERENCED_TABLE_NAME"],
                        fk["REFERENCED_COLUMN_NAME"],
                    )
                    orphans.append(
                        {
                            "column": fk["COLUMN_NAME"],
                            "parent": fk["REFERENCED_TABLE_NAME"],
                            "parent_column": fk["REFERENCED_COLUMN_NAME"],
                            "orphan_count": cnt,
                            "error": oerr,
                        }
                    )
                viz_quality["fk_orphans"] = orphans

            if viz_mode == "diff":
                dt_raw = (request.args.get("diff_table") or "").strip()
                if dt_raw:
                    try:
                        viz_diff_table = validate_mysql_identifier(dt_raw)
                        viz_diff = viz_logic.table_diff_summary(
                            connection, selected_db, table_name, viz_diff_table
                        )
                    except ValueError:
                        session["error"] = "Invalid diff table name."
                else:
                    viz_diff = None

        if selected_db and arg_table and action == "data":
            table_name = arg_table
            selected_table = table_name
            search_by = request.form.getlist("search_by[]")
            expression = request.form.getlist("expression[]")
            search_value = request.form.getlist("search_value[]")
            limit = validate_limit(request.form.get("limit", 1000))
            order_by = request.form.get("order_by") or ""
            order = validate_order_direction(request.form.get("order", "asc"))

            run_sql(connection, "USE information_schema;")
            col_cur, _ = run_sql(
                connection,
                "SELECT COLUMN_NAME, COLUMN_TYPE FROM COLUMNS "
                "WHERE TABLE_NAME=%s AND TABLE_SCHEMA=%s ORDER BY ORDINAL_POSITION",
                (table_name, selected_db),
            )
            table_columns = fetch_all(col_cur) if col_cur else []
            allowed_col_names = [c["COLUMN_NAME"] for c in table_columns]

            where_sql, where_params = _build_search_where(
                connection,
                selected_db,
                table_name,
                search_by,
                expression,
                search_value,
            )
            try:
                if order_by:
                    order_by = column_in_set(order_by, allowed_col_names)
            except ValueError:
                order_by = ""

            run_sql(connection, f"USE {quote_ident(selected_db)};")
            order_query = ""
            if order_by:
                order_query = f" ORDER BY {quote_ident(order_by)} {order}"
            data_query = (
                f"SELECT * FROM {quote_ident(table_name)}{where_sql}{order_query} LIMIT {limit}"
            )
            dcur, _ = run_sql(
                connection,
                f"SELECT * FROM {quote_ident(table_name)}{where_sql}{order_query} LIMIT {limit}",
                tuple(where_params) if where_params else None,
            )
            table_data = fetch_all(dcur) if dcur else []
            primary_keys = get_primary_key_columns(connection, selected_db, table_name)
            numeric_column_names = [
                c["COLUMN_NAME"]
                for c in table_columns
                if viz_logic.is_numeric_column_type(c.get("COLUMN_TYPE", ""))
            ]
            json_column_names = [
                c["COLUMN_NAME"]
                for c in table_columns
                if viz_logic.is_json_column_type(c.get("COLUMN_TYPE", ""))
            ]
            wide_text_column_names = [
                c["COLUMN_NAME"]
                for c in table_columns
                if any(x in (c.get("COLUMN_TYPE") or "").lower() for x in ("char", "text", "blob"))
                and c["COLUMN_NAME"] not in json_column_names
            ]

        if sql_query and selected_db:
            if _read_only() and sql_looks_mutating(sql_query):
                session["error"] = "Mutating SQL is not allowed in read-only mode."
            else:
                run_sql(connection, f"USE {quote_ident(selected_db)};")
                qcur, _ = run_sql(connection, sql_query)
                query_output = qcur
                if qcur and not session.get("error"):
                    short = (sql_query[:200] + "...") if len(sql_query) > 200 else sql_query
                    audit_event("sql_execute", short, query=sql_query)

        if databases:
            session["pass"] = True
            login = True

    error = session.pop("error", None)

    ai_assistant_available = False
    if (
        login
        and session.get("system") == "mysql"
        and selected_db
        and sql_panel
        and is_ai_assistant_available(current_app)
    ):
        ai_assistant_available = True

    ai_dashboard_available = False
    if (
        login
        and session.get("system") == "mysql"
        and selected_db
        and dashboard_panel
        and not sql_panel
        and is_ai_assistant_available(current_app)
    ):
        ai_dashboard_available = True

    return render_template(
        "py_adminer.html",
        py_admin_url="/py_adminer",
        login=login,
        databases=databases,
        mysql_version=mysql_version,
        create=create,
        action=action,
        tables=tables,
        table_structure=table_structure,
        table_indexes=table_indexes,
        table_foreign_keys=table_foreign_keys,
        primary_keys=primary_keys,
        db_engines=db_engines,
        data_query=data_query,
        table_data=table_data,
        search_by=search_by,
        expression=expression,
        search_value=search_value,
        order_by=order_by,
        order=order,
        limit=limit,
        table_columns=table_columns,
        db_collations=db_collations,
        selected_db=selected_db,
        selected_table=selected_table,
        sql_panel=sql_panel,
        sql_query=sql_query,
        query_output=query_output,
        advanced_panel=advanced_panel,
        diagram_panel=diagram_panel,
        dashboard_panel=dashboard_panel,
        dashboard_rows=dashboard_rows,
        dashboard_ai_payload=dashboard_ai_payload,
        mermaid_diagram=mermaid_diagram,
        diagram_warnings=diagram_warnings,
        db_views=db_views,
        db_routines=db_routines,
        db_triggers=db_triggers,
        db_events=db_events,
        error=error,
        csrf_token=generate_csrf,
        default_mysql_host=os.environ.get("PYADMINER_DEFAULT_MYSQL_HOST", ""),
        viz_mode=viz_mode,
        viz_impact=viz_impact,
        viz_quality=viz_quality,
        viz_diff=viz_diff,
        viz_diff_table=viz_diff_table,
        numeric_column_names=numeric_column_names,
        json_column_names=json_column_names,
        wide_text_column_names=wide_text_column_names,
        ai_assistant_available=ai_assistant_available,
        ai_dashboard_available=ai_dashboard_available,
    )


@bp.route("/py_adminer/audit_log", methods=["GET"])
def audit_log():
    conn = _require_mysql_session()
    if not conn:
        return redirect(url_for("main.py_admin"))
    databases, mysql_version = _list_databases_and_version(conn)

    path = get_audit_log_path() or ""
    try:
        limit = int(request.args.get("limit", "100"))
    except (TypeError, ValueError):
        limit = 100
    limit = max(10, min(500, limit))

    try:
        scan_kb = int(request.args.get("scan_kb", "512"))
    except (TypeError, ValueError):
        scan_kb = 512
    if scan_kb not in _ALLOWED_AUDIT_SCAN_KB:
        scan_kb = 512
    max_scan_bytes = scan_kb * 1024

    action_filter = (request.args.get("action") or "").strip()
    text_filter = (request.args.get("q") or "").strip()

    entries, meta = read_audit_entries(
        path,
        limit=limit,
        max_scan_bytes=max_scan_bytes,
        action_contains=action_filter,
        text_contains=text_filter,
    )

    error = session.pop("error", None)
    return render_template(
        "audit_log.html",
        py_admin_url="/py_adminer",
        login=True,
        databases=databases,
        mysql_version=mysql_version,
        selected_db=None,
        selected_table=None,
        tables=[],
        audit_entries=entries,
        audit_meta=meta,
        audit_limit=limit,
        audit_scan_kb=scan_kb,
        audit_action_filter=action_filter,
        audit_text_filter=text_filter,
        allowed_scan_kb=_ALLOWED_AUDIT_SCAN_KB,
        audit_log_path_display=os.path.basename(path) if path else "",
        csrf_token=generate_csrf,
        error=error,
    )


@bp.route("/py_adminer/audit_log/download", methods=["GET"])
def audit_log_download():
    conn = _require_mysql_session()
    if not conn:
        return redirect(url_for("main.py_admin"))
    path = get_audit_log_path() or ""
    if not path or not os.path.isfile(path):
        abort(404)
    return send_file(
        path,
        as_attachment=True,
        download_name="pyadminer_audit.log",
        mimetype="text/plain; charset=utf-8",
    )


@bp.route("/logout", methods=["GET", "POST"])
def logout():
    if session.get("pass"):
        audit_event(
            "logout",
            "user=" + str(session.get("user", "")) + " host=" + str(session.get("host", "")),
        )
    for key in ("system", "host", "user", "password", "database", "pass"):
        session.pop(key, None)
    return redirect(url_for("main.py_admin"))


def handle_csrf_error(_e):
    session["error"] = "Session expired or invalid form. Please try again."
    return redirect(request.referrer or url_for("main.py_admin"))


register_viz_routes(bp)
register_ai_routes(bp)
