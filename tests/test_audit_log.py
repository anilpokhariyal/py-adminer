"""Audit log reader tests (load audit.py directly to avoid full app import chain)."""

import importlib.util
import json
import os
import tempfile
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "_pyadminer_audit_under_test", _ROOT / "pyadminer" / "audit.py"
)
_audit_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_audit_mod)
read_audit_entries = _audit_mod.read_audit_entries


@pytest.mark.parametrize("limit", [5])
def test_read_audit_entries_tail_and_filters(limit):
    lines = []
    for i in range(30):
        lines.append(
            json.dumps(
                {
                    "ts": f"2026-01-01T12:00:{i:02d}Z",
                    "action": "sql_execute" if i % 2 == 0 else "login",
                    "detail": f"d{i}",
                    "query": f"SELECT {i}" if i % 2 == 0 else "",
                },
                separators=(",", ":"),
            )
        )
    body = "\n".join(lines) + "\n"
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
        f.write(body)
        path = f.name
    try:
        entries, meta = read_audit_entries(path, limit=limit, max_scan_bytes=4096)
        assert meta["file_missing"] is False
        assert len(entries) == limit
        assert entries[0]["ts"] >= entries[1]["ts"]

        entries2, _ = read_audit_entries(path, limit=50, action_contains="sql", max_scan_bytes=4096)
        for e in entries2:
            assert "sql" in e["action"].lower()

        entries3, _ = read_audit_entries(
            path, limit=50, text_contains="SELECT 28", max_scan_bytes=4096
        )
        assert any("28" in e.get("query", "") for e in entries3)
    finally:
        os.unlink(path)
