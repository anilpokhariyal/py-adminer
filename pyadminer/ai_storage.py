"""Encrypted on-disk storage for AI assistant settings (API keys, provider, toggles)."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from typing import Any

from flask import Flask

_DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "provider": "openai",
    "api_key": "",
    "base_url": "",
    "model": "gpt-4o-mini",
    "anthropic_version": "2023-06-01",
}


def _fernet_for_app(app: Flask):
    from cryptography.fernet import Fernet

    raw = str(app.config.get("SECRET_KEY") or "")
    key = base64.urlsafe_b64encode(hashlib.sha256(raw.encode("utf-8")).digest())
    return Fernet(key)


def _storage_path(app: Flask) -> str:
    custom = app.config.get("PYADMINER_AI_SETTINGS_PATH")
    if custom:
        return os.path.abspath(str(custom))
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass
    return os.path.join(app.instance_path, "ai_settings.enc")


def load_ai_settings(app: Flask) -> dict[str, Any]:
    """Return merged settings dict (includes api_key when present)."""
    path = _storage_path(app)
    out = dict(_DEFAULTS)
    if not os.path.isfile(path):
        return out
    try:
        f = _fernet_for_app(app)
        with open(path, "rb") as fp:
            raw = f.decrypt(fp.read())
        data = json.loads(raw.decode("utf-8"))
        if isinstance(data, dict):
            for k, v in data.items():
                if k in _DEFAULTS:
                    out[k] = v
    except Exception:
        pass
    return out


def save_ai_settings(app: Flask, data: dict[str, Any]) -> None:
    path = _storage_path(app)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    merged = dict(_DEFAULTS)
    merged.update(load_ai_settings(app))
    for k in _DEFAULTS:
        if k in data:
            merged[k] = data[k]
    f = _fernet_for_app(app)
    blob = f.encrypt(json.dumps(merged, separators=(",", ":")).encode("utf-8"))
    with open(path, "wb") as fp:
        fp.write(blob)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def is_ai_globally_disabled(app: Flask) -> bool:
    return bool(app.config.get("PYADMINER_AI_DISABLE"))


def is_ai_assistant_available(app: Flask) -> bool:
    if is_ai_globally_disabled(app):
        return False
    s = load_ai_settings(app)
    return bool(s.get("enabled")) and bool((s.get("api_key") or "").strip())


def public_ai_settings(app: Flask) -> dict[str, Any]:
    """Safe fields for templates (no api_key)."""
    s = load_ai_settings(app)
    return {
        "enabled": bool(s.get("enabled")),
        "provider": s.get("provider") or "openai",
        "base_url": (s.get("base_url") or "").strip(),
        "model": (s.get("model") or "").strip(),
        "anthropic_version": (s.get("anthropic_version") or "2023-06-01").strip(),
        "has_api_key": bool((s.get("api_key") or "").strip()),
        "globally_disabled": is_ai_globally_disabled(app),
    }
