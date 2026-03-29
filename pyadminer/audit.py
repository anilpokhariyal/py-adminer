from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from typing import Any

_audit = logging.getLogger("pyadminer.audit")
_lock = threading.Lock()
_log_path: str | None = None

_LEGACY_LINE = re.compile(r"^action=(?P<action>\S+)(?:\s+detail=(?P<detail>.*))?$")


def init_audit_log(app) -> None:
    """Resolve log path and ensure parent directory exists."""
    global _log_path
    path = app.config.get("PYADMINER_AUDIT_LOG_PATH")
    if path is None:
        path = os.environ.get("PYADMINER_AUDIT_LOG_PATH", "")
    path = (path or "").strip()
    if path:
        path = os.path.abspath(path)
    else:
        try:
            os.makedirs(app.instance_path, exist_ok=True)
        except OSError:
            pass
        path = os.path.join(app.instance_path, "pyadminer_audit.log")
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    _log_path = path
    app.config["PYADMINER_AUDIT_LOG_PATH_RESOLVED"] = path


def get_audit_log_path() -> str | None:
    return _log_path


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _truncate(s: str, max_len: int) -> str:
    if max_len <= 0 or len(s) <= max_len:
        return s
    return s[:max_len] + "... [truncated]"


def audit_event(action: str, detail: str = "", *, query: str | None = None) -> None:
    """Append one JSON line to the audit log (actions + optional SQL/query text)."""
    global _log_path
    if not _log_path:
        return

    try:
        from flask import has_request_context, request, session
    except ImportError:

        def has_request_context() -> bool:
            return False

        request = None  # type: ignore[assignment]
        session = None  # type: ignore[assignment]

    max_q = 16_384
    try:
        from flask import current_app

        max_q = int(current_app.config.get("PYADMINER_AUDIT_MAX_QUERY_CHARS", 16_384))
    except Exception:
        pass

    record: dict[str, Any] = {
        "ts": _utc_now_iso(),
        "action": action,
        "detail": detail or "",
    }
    if query:
        record["query"] = _truncate(query.strip(), max_q)

    if has_request_context() and request is not None:
        try:
            record["remote_addr"] = request.remote_addr or ""
            record["method"] = request.method
            record["path"] = request.path
        except Exception:
            pass
        try:
            if session is not None:
                if session.get("user"):
                    record["mysql_user"] = str(session.get("user", ""))
                if session.get("host"):
                    record["mysql_host"] = str(session.get("host", ""))
        except Exception:
            pass

    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    short = f"action={action}" + (f" detail={detail[:120]}" if detail else "")
    _audit.info(short)

    try:
        with _lock:
            with open(_log_path, "a", encoding="utf-8") as f:
                f.write(line)
    except OSError as exc:
        _audit.warning("audit log write failed: %s", exc)


def _parse_log_line(raw: str) -> dict[str, Any] | None:
    raw = raw.strip()
    if not raw:
        return None
    if raw.startswith("{"):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"ts": "", "action": "parse_error", "detail": raw[:500], "query": ""}
    m = _LEGACY_LINE.match(raw)
    if m:
        return {
            "ts": "",
            "action": m.group("action"),
            "detail": (m.group("detail") or "").strip(),
            "query": "",
        }
    return {
        "ts": "",
        "action": "legacy",
        "detail": raw[:1000],
        "query": "",
    }


def read_audit_entries(
    path: str,
    *,
    limit: int = 100,
    max_scan_bytes: int = 524_288,
    action_contains: str = "",
    text_contains: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Read the newest matching entries without loading the whole file.
    Scans the last max_scan_bytes of the file, parses JSON lines, filters, returns newest first.
    """
    action_contains = (action_contains or "").strip().lower()
    text_contains = (text_contains or "").strip().lower()
    limit = max(1, min(500, limit))
    max_scan_bytes = max(4096, min(8 * 1024 * 1024, max_scan_bytes))

    meta: dict[str, Any] = {
        "file_size": 0,
        "scanned_bytes": 0,
        "scanned_from_offset": 0,
        "scan_truncated": False,
        "file_missing": False,
        "matched_in_scan": 0,
    }

    if not path or not os.path.isfile(path):
        meta["file_missing"] = True
        return [], meta

    size = os.path.getsize(path)
    meta["file_size"] = size
    if size == 0:
        return [], meta

    to_read = min(size, max_scan_bytes)
    meta["scanned_bytes"] = to_read
    meta["scanned_from_offset"] = size - to_read
    meta["scan_truncated"] = size > to_read

    try:
        with open(path, "rb") as f:
            if meta["scanned_from_offset"] > 0:
                f.seek(meta["scanned_from_offset"])
            chunk = f.read()
    except OSError:
        return [], meta

    text = chunk.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if meta["scanned_from_offset"] > 0 and lines:
        lines = lines[1:]

    parsed: list[dict[str, Any]] = []
    for line in lines:
        row = _parse_log_line(line)
        if not row:
            continue
        act = str(row.get("action", "")).lower()
        if action_contains and action_contains not in act:
            continue
        if text_contains:
            blob = json.dumps(row, ensure_ascii=False).lower()
            if text_contains not in blob:
                continue
        parsed.append(row)

    meta["matched_in_scan"] = len(parsed)

    def sort_key(r: dict[str, Any]) -> str:
        return str(r.get("ts") or "")

    parsed.sort(key=sort_key, reverse=True)
    return parsed[:limit], meta
