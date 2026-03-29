import re
from typing import Iterable, Optional, Tuple

# MySQL unquoted identifier (simplified; covers typical names)
MYSQL_IDENT_RE = re.compile(r"^[a-zA-Z0-9_]{1,64}$")

ALLOWED_SEARCH_OPS = frozenset(
    {
        "=",
        "<",
        ">",
        "<=",
        ">=",
        "!=",
        "LIKE",
        "LIKE %%",
        "REGEXP",
        "IN",
        "FIND_IN_SET",
        "IS NULL",
        "NOT LIKE",
        "NOT REGEXP",
        "NOT IN",
        "IS NOT NULL",
    }
)

_MUTATING_SQL_PREFIXES = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "CREATE",
    "ALTER",
    "TRUNCATE",
    "RENAME",
    "GRANT",
    "REVOKE",
    "REPLACE",
    "CALL",
)


def mysql_column_type_is_numeric(column_type: str) -> bool:
    t = (column_type or "").lower()
    return any(
        x in t for x in ("int", "decimal", "numeric", "float", "double", "real", "bit")
    )


def mysql_column_type_is_temporal(column_type: str) -> bool:
    t = (column_type or "").lower()
    return (
        "date" in t
        or "time" in t
        or t.startswith("year")
    )


def mysql_column_type_is_json(column_type: str) -> bool:
    return "json" in (column_type or "").lower()


def validate_mysql_identifier(name: str) -> str:
    if not name or not MYSQL_IDENT_RE.match(name):
        raise ValueError("Invalid MySQL identifier")
    return name


def quote_ident(name: str) -> str:
    """Return backtick-quoted identifier after validation."""
    v = validate_mysql_identifier(name)
    return f"`{v}`"


def parse_collation_pair(raw: Optional[str]) -> Optional[Tuple[str, str]]:
    """Parse 'charset|collation' from select options; empty means server default."""
    if not raw or raw.strip() in ("|", "(collection)", "(collation)", "default|"):
        return None
    parts = raw.split("|", 1)
    if len(parts) != 2:
        return None
    charset, collation = parts[0].strip(), parts[1].strip()
    if not charset or not collation:
        return None
    validate_mysql_identifier(charset)
    validate_mysql_identifier(collation)
    return charset, collation


def validate_order_direction(order: Optional[str]) -> str:
    o = (order or "asc").lower()
    if o not in ("asc", "desc"):
        raise ValueError("Invalid ORDER direction")
    return o.upper()


def validate_limit(limit_raw, default: int = 1000) -> int:
    try:
        n = int(limit_raw) if limit_raw is not None else default
    except (TypeError, ValueError):
        n = default
    return max(1, min(n, 10_000))


def column_in_set(column: str, allowed: Iterable[str]) -> str:
    validate_mysql_identifier(column)
    allowed_set = set(allowed)
    if column not in allowed_set:
        raise ValueError("Unknown column")
    return column


def sql_looks_mutating(sql: str) -> bool:
    s = (sql or "").strip()
    if not s:
        return False
    head = s.split(None, 1)[0].upper()
    return head in _MUTATING_SQL_PREFIXES


# View AS-clause body must be a single SELECT (or WITH … SELECT).
_VIEW_DEFINITION_OK = re.compile(r"(?is)^\s*(WITH|SELECT)\b")


def view_definition_allowed(definition: str) -> bool:
    """True if text is suitable for CREATE VIEW … AS <definition>."""
    return bool(_VIEW_DEFINITION_OK.match((definition or "").strip()))
