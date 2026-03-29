from __future__ import annotations

import ast
from typing import Any

import MySQLdb
from flask import current_app, session


def format_mysql_error(err) -> str:
    """Turn driver/MySQL exceptions into a readable message for the UI."""
    if err is None:
        return "Unknown database error."
    if isinstance(err, str):
        s = err.strip()
        try:
            parsed = ast.literal_eval(s)
            if (
                isinstance(parsed, tuple)
                and len(parsed) == 2
                and isinstance(parsed[0], int)
            ):
                return f"MySQL error {parsed[0]}: {parsed[1]}"
        except (SyntaxError, ValueError, TypeError):
            pass
        return err
    args = getattr(err, "args", None) or ()
    if len(args) >= 2 and isinstance(args[0], int):
        code, msg = args[0], args[1]
        return f"MySQL error {code}: {msg}"
    if len(args) == 1 and isinstance(args[0], str):
        return args[0]
    return str(err)


def mysql_config(app) -> None:
    app.config["MYSQL_HOST"] = session["host"]
    app.config["MYSQL_USER"] = session["user"]
    app.config["MYSQL_PASSWORD"] = session["password"]
    # Empty default catalog breaks mysqlclient; use system schema until user picks a DB.
    raw_db = (session.get("database") or "").strip()
    app.config["MYSQL_DB"] = raw_db if raw_db else "mysql"
    app.config["MYSQL_PORT"] = app.config.get("MYSQL_PORT", 3306)


def mysql_connection():
    from pyadminer.extensions import mysql

    return mysql.connect


def run_sql(
    connection,
    sql: str,
    params: tuple | dict | None = None,
    *,
    store_error: bool = True,
):
    """
    Execute SQL. Always commits (mysqlclient / InnoDB reads are fine).
    Returns (cursor_or_None, error_or_None).
    """
    from flask import session as flask_session

    try:
        cursor = connection.cursor(MySQLdb.cursors.DictCursor)
        if params is not None:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        connection.commit()
        return cursor, None
    except MySQLdb.OperationalError as err:
        current_app.logger.error("MySQL operational error: %s", err)
        if store_error:
            flask_session["error"] = format_mysql_error(err)
        return None, str(err)
    except MySQLdb.ProgrammingError as err:
        current_app.logger.error("MySQL programming error: %s", err)
        if store_error:
            flask_session["error"] = format_mysql_error(err)
        return None, str(err)
    except Exception as err:
        current_app.logger.exception("MySQL error")
        if store_error:
            flask_session["error"] = format_mysql_error(err)
        return None, str(err)


def fetch_all(cursor) -> list[dict[str, Any]]:
    if cursor is None:
        return []
    rows = cursor.fetchall()
    return list(rows) if rows else []


def get_primary_key_columns(connection, database: str, table: str) -> list[str]:
    """Ordered PRIMARY KEY column names for a table."""
    sql = (
        "SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE "
        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND CONSTRAINT_NAME = 'PRIMARY' "
        "ORDER BY ORDINAL_POSITION"
    )
    cur, err = run_sql(connection, sql, (database, table), store_error=False)
    if err or cur is None:
        return []
    rows = fetch_all(cur)
    return [r["COLUMN_NAME"] for r in rows]


def get_table_column_names(connection, database: str, table: str) -> list[str]:
    sql = (
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s ORDER BY ORDINAL_POSITION"
    )
    cur, err = run_sql(connection, sql, (database, table), store_error=False)
    if err or cur is None:
        return []
    return [r["COLUMN_NAME"] for r in fetch_all(cur)]
