import importlib.util
import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "_pyadminer_ai_sql", _ROOT / "pyadminer" / "ai_sql.py"
)
_m = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_m)

sql_looks_safe_for_ai = _m.sql_looks_safe_for_ai
ensure_select_limit = _m.ensure_select_limit
extract_json_object_from_llm = _m.extract_json_object_from_llm


@pytest.mark.parametrize(
    "sql,ok",
    [
        ("SELECT 1", True),
        ("WITH a AS (SELECT 1) SELECT * FROM a", True),
        ("INSERT INTO t VALUES (1)", False),
        ("SELECT 1; DROP TABLE x", False),
        ("SELECT 1 INTO OUTFILE '/tmp/x'", False),
    ],
)
def test_sql_looks_safe_for_ai(sql, ok):
    good, _msg = sql_looks_safe_for_ai(sql)
    assert good is ok


def test_ensure_select_limit_appends():
    s = ensure_select_limit("SELECT * FROM `t`", cap=100)
    assert s.rstrip().endswith("LIMIT 100")


def test_ensure_select_limit_preserves_existing():
    s = ensure_select_limit("SELECT * FROM t LIMIT 10", cap=500)
    assert "LIMIT 10" in s


def test_extract_json_object_from_llm_strips_fence():
    raw = '```json\n{"sql":"SELECT 1","explanation":"ok"}\n```'
    obj = extract_json_object_from_llm(raw)
    assert obj["sql"] == "SELECT 1"
    assert json.loads(json.dumps(obj)) == obj
