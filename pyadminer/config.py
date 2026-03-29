import os
import secrets


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    DEBUG = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes")

    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None

    MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))

    PYADMINER_READ_ONLY = os.environ.get("PYADMINER_READ_ONLY", "").lower() in (
        "1",
        "true",
        "yes",
    )
    PYADMINER_AUTH_USERNAME = os.environ.get("PYADMINER_AUTH_USERNAME", "").strip()
    PYADMINER_AUTH_PASSWORD = os.environ.get("PYADMINER_AUTH_PASSWORD", "")

    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_ENABLED = os.environ.get("RATELIMIT_ENABLED", "true").lower() in (
        "1",
        "true",
        "yes",
    )

    # Audit log (JSON lines). Empty path → Flask instance folder.
    _audit_path = os.environ.get("PYADMINER_AUDIT_LOG_PATH", "").strip()
    PYADMINER_AUDIT_LOG_PATH = _audit_path or None
    PYADMINER_AUDIT_MAX_QUERY_CHARS = int(
        os.environ.get("PYADMINER_AUDIT_MAX_QUERY_CHARS", "16384")
    )

    # Natural-language SQL assistant (optional). Set PYADMINER_AI_DISABLE=1 to force off.
    PYADMINER_AI_DISABLE = os.environ.get("PYADMINER_AI_DISABLE", "").lower() in (
        "1",
        "true",
        "yes",
    )
    _ai_path = os.environ.get("PYADMINER_AI_SETTINGS_PATH", "").strip()
    PYADMINER_AI_SETTINGS_PATH = _ai_path or None


def get_host_port():
    host = os.environ.get("FLASK_RUN_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_RUN_PORT", "5000"))
    return host, port
