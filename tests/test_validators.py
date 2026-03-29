import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "_pyadminer_validators", _ROOT / "pyadminer" / "validators.py"
)
_v = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_v)

parse_collation_pair = _v.parse_collation_pair
sql_looks_mutating = _v.sql_looks_mutating
validate_limit = _v.validate_limit
validate_mysql_identifier = _v.validate_mysql_identifier
view_definition_allowed = _v.view_definition_allowed
mysql_column_type_is_json = _v.mysql_column_type_is_json
mysql_column_type_is_numeric = _v.mysql_column_type_is_numeric
mysql_column_type_is_temporal = _v.mysql_column_type_is_temporal


def test_validate_mysql_identifier_ok():
    assert validate_mysql_identifier("foo_bar1") == "foo_bar1"


@pytest.mark.parametrize(
    "name",
    ["", "bad-name", "a" * 65, "space name", None],
)
def test_validate_mysql_identifier_bad(name):
    with pytest.raises(ValueError):
        validate_mysql_identifier(name or "")


def test_parse_collation_pair():
    assert parse_collation_pair("utf8mb4|utf8mb4_unicode_ci") == (
        "utf8mb4",
        "utf8mb4_unicode_ci",
    )
    assert parse_collation_pair("|") is None
    assert parse_collation_pair(None) is None


def test_validate_limit():
    assert validate_limit("50", 1000) == 50
    assert validate_limit(999999, 1000) == 10_000
    assert validate_limit("nope", 100) == 100


def test_sql_looks_mutating():
    assert sql_looks_mutating("SELECT 1") is False
    assert sql_looks_mutating("  delete from t") is True
    assert sql_looks_mutating("UPDATE x SET y=1") is True


def test_view_definition_allowed():
    assert view_definition_allowed("SELECT * FROM t") is True
    assert view_definition_allowed("  with c as (select 1) select * from c") is True
    assert view_definition_allowed("INSERT INTO t VALUES (1)") is False
    assert view_definition_allowed("") is False


@pytest.mark.parametrize(
    ("ctype", "expected"),
    [
        ("int(11)", True),
        ("bigint unsigned", True),
        ("decimal(10,2)", True),
        ("float", True),
        ("double", True),
        ("varchar(32)", False),
        ("json", False),
    ],
)
def test_mysql_column_type_is_numeric(ctype, expected):
    assert mysql_column_type_is_numeric(ctype) is expected


@pytest.mark.parametrize(
    ("ctype", "expected"),
    [
        ("datetime", True),
        ("date", True),
        ("timestamp", True),
        ("time", True),
        ("year(4)", True),
        ("varchar(10)", False),
    ],
)
def test_mysql_column_type_is_temporal(ctype, expected):
    assert mysql_column_type_is_temporal(ctype) is expected


def test_mysql_column_type_is_json():
    assert mysql_column_type_is_json("json") is True
    assert mysql_column_type_is_json("longtext") is False
