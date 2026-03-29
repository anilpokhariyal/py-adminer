import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "_diagram_build", _ROOT / "pyadminer" / "diagram_build.py"
)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)

build_mermaid_er_diagram = _mod.build_mermaid_er_diagram
group_foreign_keys = _mod.group_foreign_keys
simplify_mysql_type_for_mermaid = _mod.simplify_mysql_type_for_mermaid


def test_simplify_mysql_type_for_mermaid():
    assert simplify_mysql_type_for_mermaid("int(11)") == "int"
    assert simplify_mysql_type_for_mermaid("varchar(255)") == "string"
    assert simplify_mysql_type_for_mermaid("json") == "json"


def test_group_foreign_keys_orders_by_first_seen():
    rows = [
        {
            "TABLE_NAME": "orders",
            "COLUMN_NAME": "cid",
            "REFERENCED_TABLE_NAME": "customers",
            "REFERENCED_COLUMN_NAME": "id",
            "CONSTRAINT_NAME": "fk_o_c",
            "ORDINAL_POSITION": 1,
        },
        {
            "TABLE_NAME": "orders",
            "COLUMN_NAME": "pid",
            "REFERENCED_TABLE_NAME": "products",
            "REFERENCED_COLUMN_NAME": "id",
            "CONSTRAINT_NAME": "fk_o_p",
            "ORDINAL_POSITION": 1,
        },
    ]
    g = group_foreign_keys(rows)
    assert len(g) == 2
    assert g[0]["cols"] == [("cid", "id")]


def test_build_mermaid_er_diagram_contains_entities_and_relationship():
    tables_cols = {
        "customers": [
            {
                "COLUMN_NAME": "id",
                "COLUMN_TYPE": "int",
                "COLUMN_KEY": "PRI",
                "EXTRA": "",
            },
            {"COLUMN_NAME": "name", "COLUMN_TYPE": "varchar(100)", "COLUMN_KEY": "", "EXTRA": ""},
        ],
        "orders": [
            {
                "COLUMN_NAME": "id",
                "COLUMN_TYPE": "int",
                "COLUMN_KEY": "PRI",
                "EXTRA": "",
            },
            {
                "COLUMN_NAME": "customer_id",
                "COLUMN_TYPE": "int",
                "COLUMN_KEY": "MUL",
                "EXTRA": "",
            },
        ],
    }
    fk_groups = [
        {
            "child": "orders",
            "parent": "customers",
            "name": "fk_orders_customer",
            "cols": [("customer_id", "id")],
        }
    ]
    text = build_mermaid_er_diagram(tables_cols, fk_groups, {"orders": "BASE TABLE", "customers": "BASE TABLE"})
    assert "erDiagram" in text
    assert "customers {" in text
    assert "orders {" in text
    assert "int id PK" in text
    assert "orders }o--|| customers" in text
