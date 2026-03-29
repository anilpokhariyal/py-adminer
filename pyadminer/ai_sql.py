"""Validate and normalize SQL produced by the NL assistant."""

from __future__ import annotations

import json
import re
from typing import Any

from pyadminer.validators import sql_looks_mutating

_FORBIDDEN_SUBSTRINGS = (
    "INTO OUTFILE",
    "INTO DUMPFILE",
    "LOAD DATA",
    "LOAD_FILE",
    "FOR UPDATE",
    "LOCK TABLE",
    "UNLOCK TABLE",
    "PREPARE ",
    "EXECUTE ",
    "DEALLOCATE ",
    "CALL ",
    "DO ",
    "HANDLER ",
    "REPAIR ",
    "OPTIMIZE ",
    "CHECK ",
    "INSTALL ",
    "UNINSTALL ",
    "SHUTDOWN",
    "KILL ",
)

_LIMIT_TAIL = re.compile(r"\bLIMIT\s+[0-9]+\s*$", re.IGNORECASE)
_MUTATING_WORD = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|REPLACE)\b",
    re.IGNORECASE,
)


def sql_looks_safe_for_ai(sql: str) -> tuple[bool, str]:
    s = (sql or "").strip()
    if not s:
        return False, "Empty SQL."
    s = s.rstrip().rstrip(";")
    inner = s
    if ";" in inner:
        return False, "Only a single SQL statement is allowed."
    head = inner.split(None, 1)[0].upper()
    if head not in ("SELECT", "WITH"):
        return False, "Only SELECT (or WITH … SELECT) queries are allowed."
    if sql_looks_mutating(inner):
        return False, "This statement looks mutating and is not allowed."
    if _MUTATING_WORD.search(inner):
        return False, "Statement contains a disallowed SQL keyword."
    upper = inner.upper()
    for bad in _FORBIDDEN_SUBSTRINGS:
        if bad in upper:
            return False, f"Disallowed construct ({bad.strip()})."
    return True, ""


def ensure_select_limit(sql: str, cap: int = 500) -> str:
    s = (sql or "").strip().rstrip(";").strip()
    if _LIMIT_TAIL.search(s):
        return s
    return f"{s} LIMIT {max(1, min(int(cap), 10_000))}"


def extract_json_object_from_llm(text: str) -> dict[str, Any]:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t)
        t = t.strip()
    obj = json.loads(t)
    if not isinstance(obj, dict):
        raise ValueError("Model did not return a JSON object.")
    return obj
