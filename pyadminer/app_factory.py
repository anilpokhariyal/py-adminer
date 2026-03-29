import json
import logging
import os

from flask import Flask, request
from flask_wtf.csrf import CSRFError

from pyadminer.audit import init_audit_log
from pyadminer.auth import check_app_basic_auth
from pyadminer.config import Config
from pyadminer.extensions import csrf, limiter, mysql
from pyadminer.routes import bp, handle_csrf_error


def create_app(config_class: type = Config) -> Flask:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    app = Flask(
        __name__,
        template_folder=os.path.join(root, "templates"),
        static_folder=os.path.join(root, "static"),
    )
    app.config.from_object(config_class)
    app.config.setdefault("MYSQL_PORT", int(os.environ.get("MYSQL_PORT", "3306")))
    init_audit_log(app)

    mysql.init_app(app)
    csrf.init_app(app)

    limiter.init_app(app)

    @app.before_request
    def _app_level_auth():
        if request.endpoint in ("static", "health_check"):
            return None
        return check_app_basic_auth()

    app.register_blueprint(bp)
    app.register_error_handler(CSRFError, handle_csrf_error)

    @app.context_processor
    def _sidebar_nav_defaults():
        # Standalone pages (audit log, AI settings) omit `tables`; sidebar must not error.
        return {"tables": []}

    @app.template_filter("pk_json")
    def _pk_json_filter(row, keys):
        if not keys:
            return "{}"
        return json.dumps({k: row.get(k) for k in keys}, default=str)

    @app.route("/health")
    def health_check():
        return {"status": "ok"}

    logging.basicConfig(level=logging.INFO)
    if not app.debug:
        app.logger.setLevel(logging.INFO)

    return app
