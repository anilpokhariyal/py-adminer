"""AI assistant settings page and NL→SQL API."""

from __future__ import annotations

import json

from flask import (
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf.csrf import generate_csrf

from pyadminer.ai_client import complete_chat
from pyadminer.ai_schema import fetch_schema_for_nl
from pyadminer.ai_sql import (
    ensure_select_limit,
    extract_json_object_from_llm,
    sql_looks_safe_for_ai,
)
from pyadminer.ai_storage import (
    is_ai_assistant_available,
    is_ai_globally_disabled,
    load_ai_settings,
    public_ai_settings,
    save_ai_settings,
)
from pyadminer.audit import audit_event
from pyadminer.extensions import limiter
from pyadminer.validators import validate_mysql_identifier


def register_ai_routes(bp):
    from pyadminer.routes import (
        _limiter_disabled,
        _list_databases_and_version,
        _require_mysql_session,
    )

    @bp.route("/py_adminer/ai_settings", methods=["GET", "POST"])
    @limiter.limit("30 per minute", methods=["POST"], exempt_when=_limiter_disabled)
    def ai_settings():
        conn = _require_mysql_session()
        if not conn:
            return redirect(url_for("main.py_admin"))

        databases, mysql_version = _list_databases_and_version(conn)
        error = session.pop("error", None)

        if request.method == "POST":
            if is_ai_globally_disabled(current_app):
                session["error"] = "AI features are disabled by the server (PYADMINER_AI_DISABLE)."
                return redirect(url_for("main.ai_settings"))

            prev = load_ai_settings(current_app)
            api_key_in = (request.form.get("api_key") or "").strip()
            new_key = api_key_in if api_key_in else prev.get("api_key", "")

            data = {
                "enabled": request.form.get("ai_enabled") == "yes",
                "provider": (request.form.get("provider") or "openai").strip().lower(),
                "api_key": new_key,
                "base_url": (request.form.get("base_url") or "").strip(),
                "model": (request.form.get("model") or "").strip(),
                "anthropic_version": (
                    request.form.get("anthropic_version") or "2023-06-01"
                ).strip(),
            }
            if data["provider"] not in ("openai", "anthropic", "openai_compatible"):
                data["provider"] = "openai"
            save_ai_settings(current_app, data)
            audit_event(
                "ai_settings_update",
                f"enabled={data['enabled']} provider={data['provider']}",
            )
            return redirect(url_for("main.ai_settings"))

        pub = public_ai_settings(current_app)
        return render_template(
            "ai_settings.html",
            py_admin_url="/py_adminer",
            login=True,
            databases=databases,
            mysql_version=mysql_version,
            selected_db=None,
            selected_table=None,
            tables=[],
            ai_public=pub,
            error=error,
            csrf_token=generate_csrf,
        )

    @bp.route("/py_adminer/api/ai/nl_to_sql", methods=["POST"])
    @limiter.limit("20 per minute", methods=["POST"], exempt_when=_limiter_disabled)
    def api_ai_nl_to_sql():
        conn = _require_mysql_session()
        if not conn:
            return jsonify({"error": "Not connected"}), 401
        if is_ai_globally_disabled(current_app):
            return jsonify({"error": "AI is disabled on this server."}), 403
        if not is_ai_assistant_available(current_app):
            return jsonify({"error": "AI assistant is not enabled or API key is missing."}), 403

        body = request.get_json(silent=True) or {}
        question = (body.get("question") or "").strip()
        if not question or len(question) > 4000:
            return jsonify({"error": "Question missing or too long (max 4000 chars)."}), 400

        try:
            database = validate_mysql_identifier(str(body.get("database", "")))
        except ValueError:
            return jsonify({"error": "Invalid database name."}), 400

        focus = (body.get("table") or "").strip() or None
        if focus:
            try:
                focus = validate_mysql_identifier(focus)
            except ValueError:
                focus = None

        settings = load_ai_settings(current_app)
        api_key = (settings.get("api_key") or "").strip()
        provider = (settings.get("provider") or "openai").strip().lower()
        model = (settings.get("model") or "").strip() or "gpt-4o-mini"
        base_url = (settings.get("base_url") or "").strip()
        anthropic_version = (settings.get("anthropic_version") or "2023-06-01").strip()

        if provider == "openai" and not base_url:
            base_url = "https://api.openai.com/v1"
        if provider == "anthropic" and not base_url:
            base_url = "https://api.anthropic.com"

        try:
            schema = fetch_schema_for_nl(conn, database, focus)
        except ValueError:
            return jsonify({"error": "Invalid schema context."}), 400
        except Exception as exc:
            current_app.logger.warning("ai schema fetch failed: %s", exc)
            return jsonify({"error": "Could not load schema for this database."}), 500

        system = (
            "You are a careful MySQL assistant. The user asks for data in plain English.\n"
            "Reply with ONLY valid JSON (no markdown fences) in this exact shape:\n"
            '{"sql":"<one MySQL SELECT or WITH…SELECT>","explanation":"<one short sentence>"}\n'
            "Rules for sql:\n"
            "- Read-only: only SELECT or WITH leading to SELECT. No DDL/DML, no admin commands.\n"
            "- Use backticks around every table and column name, e.g. `orders`.`id`.\n"
            "- Use only tables and columns that appear in the schema below.\n"
            "- Prefer an explicit LIMIT (at most 500) on row-returning queries.\n"
            "- Single statement only; do not use semicolons inside the sql string.\n"
            "- Current database is implied; qualify tables as `tablename` not `db`.`tablename` "
            "unless required for clarity.\n"
        )

        user_msg = f"Schema:\n{schema}\n\nQuestion:\n{question}"

        try:
            raw = complete_chat(
                provider=provider,
                base_url=base_url,
                api_key=api_key,
                model=model,
                system=system,
                user=user_msg,
                anthropic_version=anthropic_version,
            )
            obj = extract_json_object_from_llm(raw)
        except (json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
            current_app.logger.info("ai nl parse error: %s", exc)
            return jsonify({"error": "Could not parse model response as JSON."}), 502
        except RuntimeError as exc:
            current_app.logger.warning("ai nl api error: %s", exc)
            return jsonify({"error": str(exc)}), 502

        sql = (obj.get("sql") or "").strip()
        explanation = (obj.get("explanation") or "").strip()
        ok, reason = sql_looks_safe_for_ai(sql)
        if not ok:
            return jsonify({"error": f"Generated SQL rejected: {reason}"}), 400
        sql = ensure_select_limit(sql, cap=500)

        audit_event(
            "ai_nl_question",
            question[:500],
            query=sql[: current_app.config.get("PYADMINER_AUDIT_MAX_QUERY_CHARS", 16384)],
        )

        return jsonify({"sql": sql, "explanation": explanation})
