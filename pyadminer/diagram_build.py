"""Pure helpers to build Mermaid erDiagram text (no DB / Flask imports)."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

_MERMAID_LABEL_SAFE = re.compile(r"[^\w\s\-]")


def simplify_mysql_type_for_mermaid(col_type: str) -> str:
    """Map MySQL COLUMN_TYPE to Mermaid ER attribute types."""
    t = (col_type or "varchar(1)").lower()
    if "int" in t and "point" not in t:
        return "int"
    if any(x in t for x in ("char", "text", "binary", "blob", "enum", "set")):
        return "string"
    if any(x in t for x in ("decimal", "numeric", "float", "double", "real")):
        return "float"
    if "bool" in t or t.startswith("tinyint(1)"):
        return "boolean"
    if "date" in t or "time" in t or "year" in t:
        return "datetime"
    if "json" in t:
        return "json"
    return "string"


def _mermaid_label(raw: str) -> str:
    s = _MERMAID_LABEL_SAFE.sub("", raw or "")
    return (s[:48] + "...") if len(s) > 48 else s or "fk"


def group_foreign_keys(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Group KEY_COLUMN_USAGE rows by (child_table, parent_table, constraint_name).
    Each group has cols: list of (child_col, parent_col).
    """
    key_order: list[tuple[str, str, str]] = []
    groups: dict[tuple[str, str, str], list[tuple[str, str]]] = defaultdict(list)
    for r in rows:
        child = r.get("TABLE_NAME")
        parent = r.get("REFERENCED_TABLE_NAME")
        cname = r.get("CONSTRAINT_NAME") or "fk"
        if not child or not parent:
            continue
        k = (child, parent, cname)
        if k not in groups:
            key_order.append(k)
        groups[k].append((str(r.get("COLUMN_NAME", "")), str(r.get("REFERENCED_COLUMN_NAME", ""))))
    out = []
    for k in key_order:
        child, parent, cname = k
        pairs = groups[k]
        out.append(
            {
                "child": child,
                "parent": parent,
                "name": cname,
                "cols": pairs,
            }
        )
    return out


def build_mermaid_er_diagram(
    tables_cols: dict[str, list[dict[str, Any]]],
    fk_groups: list[dict[str, Any]],
    table_types: dict[str, str] | None = None,
) -> str:
    """Build Mermaid erDiagram text. tables_cols: table -> column rows from COLUMNS."""
    table_types = table_types or {}
    lines = ["erDiagram"]
    if not tables_cols:
        return ""

    for tname in sorted(tables_cols.keys()):
        cols = tables_cols[tname]
        ttype = table_types.get(tname, "BASE TABLE")
        if ttype == "VIEW":
            lines.append(f"    %% view: {tname}")
        lines.append(f"    {tname} {{")
        if not cols:
            lines.append("        string placeholder")
        for c in cols:
            cn = c.get("COLUMN_NAME", "col")
            ctype = simplify_mysql_type_for_mermaid(str(c.get("COLUMN_TYPE", "")))
            flags: list[str] = []
            if c.get("COLUMN_KEY") == "PRI":
                flags.append("PK")
            if c.get("COLUMN_KEY") == "UNI":
                flags.append("UK")
            if str(c.get("EXTRA", "")).lower().find("auto_increment") >= 0:
                if "PK" not in flags:
                    flags.append("AI")
            flag_s = (" " + " ".join(flags)) if flags else ""
            lines.append(f"        {ctype} {cn}{flag_s}")
        lines.append("    }")

    seen_pairs: dict[tuple[str, str], int] = {}
    for fk in fk_groups:
        child = fk["child"]
        parent = fk["parent"]
        cname = fk["name"]
        pairs = fk.get("cols") or []
        pair_hint = ""
        if pairs:
            pair_hint = ", ".join(f"{a}->{b}" for a, b in pairs[:4])
            if len(pairs) > 4:
                pair_hint += ",..."
        label = _mermaid_label(f"{cname} {pair_hint}".strip())
        pair_key = (child, parent)
        seen_pairs[pair_key] = seen_pairs.get(pair_key, 0) + 1
        if seen_pairs[pair_key] > 1:
            label = f"{label} ({seen_pairs[pair_key]})"
        lines.append(f'    {child} }}o--|| {parent} : "{label}"')

    return "\n".join(lines) + "\n"
