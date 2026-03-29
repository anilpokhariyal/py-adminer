"""Call OpenAI-compatible or Anthropic chat APIs (stdlib HTTP)."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from typing import Any


def _post_json(
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    *,
    timeout: float = 90.0,
) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"API HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"API connection error: {e}") from e


def complete_chat(
    *,
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
    system: str,
    user: str,
    anthropic_version: str,
) -> str:
    provider = (provider or "openai").strip().lower()
    if provider == "anthropic":
        root = (base_url or "https://api.anthropic.com").rstrip("/")
        url = f"{root}/v1/messages"
        body = {
            "model": model,
            "max_tokens": 2048,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": anthropic_version or "2023-06-01",
        }
        out = _post_json(url, headers, body)
        blocks = out.get("content") or []
        parts = []
        for b in blocks:
            if isinstance(b, dict) and b.get("type") == "text":
                parts.append(b.get("text") or "")
        text = "".join(parts).strip()
        if not text:
            raise RuntimeError("Empty response from Anthropic API.")
        return text

    # openai + openai_compatible
    root = (base_url or "https://api.openai.com/v1").rstrip("/")
    url = f"{root}/chat/completions"
    body = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    out = _post_json(url, headers, body)
    choices = out.get("choices") or []
    if not choices:
        raise RuntimeError("No choices in API response.")
    msg = choices[0].get("message") or {}
    text = (msg.get("content") or "").strip()
    if not text:
        raise RuntimeError("Empty message content from API.")
    return text
