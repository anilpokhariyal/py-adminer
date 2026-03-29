"""JSON API routes for table visualization (registered on main blueprint)."""

from __future__ import annotations

from flask import jsonify, request

from pyadminer import viz_logic as vl
from pyadminer.extensions import limiter
from pyadminer.validators import validate_mysql_identifier


def register_viz_routes(bp):
    from pyadminer.routes import _limiter_disabled, _require_mysql_session

    @bp.route("/py_adminer/api/viz/profile", methods=["GET"])
    @limiter.limit("120 per minute", exempt_when=_limiter_disabled)
    def api_viz_profile():
        conn = _require_mysql_session()
        if not conn:
            return jsonify({"error": "Not connected"}), 401
        try:
            database = validate_mysql_identifier(str(request.args.get("database", "")))
            table = validate_mysql_identifier(str(request.args.get("table", "")))
            column = validate_mysql_identifier(str(request.args.get("column", "")))
        except ValueError:
            return jsonify({"error": "Invalid identifier"}), 400
        data = vl.column_profile(conn, database, table, column)
        if data.get("error"):
            return jsonify(data), 404
        return jsonify(data)

    @bp.route("/py_adminer/api/viz/chart", methods=["GET"])
    @limiter.limit("120 per minute", exempt_when=_limiter_disabled)
    def api_viz_chart():
        conn = _require_mysql_session()
        if not conn:
            return jsonify({"error": "Not connected"}), 401
        kind = (request.args.get("kind") or "").strip().lower()
        try:
            database = validate_mysql_identifier(str(request.args.get("database", "")))
            table = validate_mysql_identifier(str(request.args.get("table", "")))
        except ValueError:
            return jsonify({"error": "Invalid identifier"}), 400

        if kind == "categorical":
            try:
                column = validate_mysql_identifier(str(request.args.get("column", "")))
            except ValueError:
                return jsonify({"error": "Invalid column"}), 400
            try:
                lim = int(request.args.get("limit", 25))
            except (TypeError, ValueError):
                lim = 25
            return jsonify(vl.chart_categorical(conn, database, table, column, limit=lim))

        if kind == "timeseries":
            try:
                column = validate_mysql_identifier(str(request.args.get("column", "")))
            except ValueError:
                return jsonify({"error": "Invalid column"}), 400
            try:
                lim = int(request.args.get("limit", 90))
            except (TypeError, ValueError):
                lim = 90
            return jsonify(
                vl.chart_timeseries(conn, database, table, column, limit=lim)
            )

        if kind == "scatter":
            try:
                cx = validate_mysql_identifier(str(request.args.get("column", "")))
                cy = validate_mysql_identifier(str(request.args.get("column2", "")))
            except ValueError:
                return jsonify({"error": "Invalid column"}), 400
            try:
                lim = int(request.args.get("limit", 500))
            except (TypeError, ValueError):
                lim = 500
            return jsonify(
                vl.chart_scatter(conn, database, table, cx, cy, limit=lim)
            )

        return jsonify({"error": "Unknown chart kind"}), 400

    @bp.route("/py_adminer/api/viz/pivot", methods=["POST"])
    @limiter.limit("60 per minute", methods=["POST"], exempt_when=_limiter_disabled)
    def api_viz_pivot():
        conn = _require_mysql_session()
        if not conn:
            return jsonify({"error": "Not connected"}), 401
        body = request.get_json(silent=True) or {}
        try:
            database = validate_mysql_identifier(str(body.get("database", "")))
            table = validate_mysql_identifier(str(body.get("table", "")))
            row_c = validate_mysql_identifier(str(body.get("row", "")))
            col_c = validate_mysql_identifier(str(body.get("col", "")))
            val_c = validate_mysql_identifier(str(body.get("value", "")))
        except ValueError:
            return jsonify({"error": "Invalid identifier"}), 400
        agg = str(body.get("agg", "SUM"))
        try:
            lim = int(body.get("limit", 2000))
        except (TypeError, ValueError):
            lim = 2000
        return jsonify(
            vl.pivot_aggregate(
                conn, database, table, row_c, col_c, val_c, agg, limit=lim
            )
        )
