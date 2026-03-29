"""
Integration tests against a real MySQL server.
CI sets MYSQL_TEST_HOST; locally skip if unset.
"""

import pytest

from pyadminer.db import fetch_all, run_sql
from pyadminer.extensions import mysql

pytestmark = pytest.mark.integration


def test_mysql_list_schemata(app, mysql_env):
    cfg = app.config
    cfg["MYSQL_HOST"] = mysql_env["host"]
    cfg["MYSQL_USER"] = mysql_env["user"]
    cfg["MYSQL_PASSWORD"] = mysql_env["password"]
    cfg["MYSQL_DB"] = mysql_env["database"]
    cfg["MYSQL_PORT"] = mysql_env["port"]

    with app.app_context():
        conn = mysql.connect
        cur, err = run_sql(conn, "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA LIMIT 3")
        assert err is None
        rows = fetch_all(cur)
        assert len(rows) >= 1
        assert "SCHEMA_NAME" in rows[0]
