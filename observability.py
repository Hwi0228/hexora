"""Request correlation, structured logs, and lightweight health endpoints."""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone

from flask import current_app, g, jsonify, request


_SAFE_EXTRA_FIELDS = (
    "event", "request_id", "method", "path", "status_code", "duration_ms",
    "stage", "file_type", "question_count", "elapsed_ms", "error_type",
)


class JsonLogFormatter(logging.Formatter):
    """Emit a stable, allow-listed JSON shape without serializing request data."""

    def format(self, record):
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "message": record.getMessage(),
        }
        for key in _SAFE_EXTRA_FIELDS:
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["error_type"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _configure_json_logging(app):
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    app.logger.handlers.clear()
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
    app.logger.propagate = False


def register_observability(app):
    _configure_json_logging(app)

    @app.before_request
    def start_request_context():
        g.request_id = uuid.uuid4().hex
        g.request_started_at = time.perf_counter()

    @app.after_request
    def log_request(response):
        request_id = getattr(g, "request_id", None)
        if request_id:
            response.headers["X-Request-ID"] = request_id
            current_app.logger.info(
                "http_request",
                extra={
                    "event": "http_request",
                    "request_id": request_id,
                    "method": request.method,
                    # Do not log query strings, form values, or headers.
                    "path": request.path,
                    "status_code": response.status_code,
                    "duration_ms": round(
                        (time.perf_counter() - g.request_started_at) * 1000, 2
                    ),
                },
            )
        return response

    @app.get("/health/live")
    def health_live():
        return jsonify({"status": "alive"}), 200

    @app.get("/health/ready")
    def health_ready():
        from database import get_db

        try:
            get_db().execute("SELECT 1").fetchone()
        except Exception as error:
            current_app.logger.error(
                "health_check_failed",
                extra={"event": "health_check_failed", "error_type": type(error).__name__},
            )
            return jsonify({"status": "not_ready"}), 503
        return jsonify({"status": "ready"}), 200
