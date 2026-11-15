"""Database-backed request throttling for public write endpoints.

The counter store uses portable SQLite/PostgreSQL SQL so deployments do not
need Redis or trust client-supplied forwarding headers.
"""

import hashlib
import hmac
import os
import time

from flask import current_app, g, make_response, request


_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS hexora_rate_limit_hits (
    bucket_key TEXT NOT NULL,
    window_start BIGINT NOT NULL,
    hits INTEGER NOT NULL,
    PRIMARY KEY (bucket_key, window_start)
)
"""


def _positive_int(value, default, environment_key=None):
    if value is None and environment_key:
        value = os.environ.get(environment_key)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _digest(value):
    secret = str(current_app.config["SECRET_KEY"]).encode("utf-8")
    return hmac.new(secret, str(value).encode("utf-8"), hashlib.sha256).hexdigest()


def _consume(connection, bucket, limit, window_seconds, now):
    window_start = (now // window_seconds) * window_seconds
    cursor = connection.execute(
        """
        INSERT INTO hexora_rate_limit_hits (bucket_key, window_start, hits)
        VALUES (?, ?, 1)
        ON CONFLICT(bucket_key, window_start)
        DO UPDATE SET hits = hexora_rate_limit_hits.hits + 1
        RETURNING hits
        """,
        (bucket, window_start),
    )
    hits = cursor.fetchone()["hits"]
    retry_after = max(1, window_start + window_seconds - now)
    return hits > limit, retry_after


def check_request_limits(endpoint, remote_addr, account_identifier=None):
    """Consume all applicable fixed-window buckets and return retry seconds."""
    connection = _get_connection()
    connection.execute(_TABLE_SQL)
    now = int(time.time())
    blocked = False
    retry_after = 1

    ip_key = _digest(remote_addr or "unknown")
    if endpoint == "login":
        window = _positive_int(
            current_app.config.get("RATE_LIMIT_LOGIN_WINDOW_SECONDS"), 900, "RATE_LIMIT_LOGIN_WINDOW_SECONDS"
        )
        ip_limit = _positive_int(
            current_app.config.get("RATE_LIMIT_LOGIN_IP_MAX"), 30, "RATE_LIMIT_LOGIN_IP_MAX"
        )
        account_limit = _positive_int(
            current_app.config.get("RATE_LIMIT_LOGIN_ACCOUNT_MAX"), 8, "RATE_LIMIT_LOGIN_ACCOUNT_MAX"
        )
        ip_blocked, ip_retry = _consume(
            connection, f"login:ip:{ip_key}", ip_limit, window, now
        )
        blocked = blocked or ip_blocked
        retry_after = max(retry_after, ip_retry if ip_blocked else 1)
        if account_identifier:
            account_key = _digest(account_identifier.strip().lower())
            account_blocked, account_retry = _consume(
                connection,
                f"login:account:{ip_key}:{account_key}",
                account_limit,
                window,
                now,
            )
            blocked = blocked or account_blocked
            retry_after = max(retry_after, account_retry if account_blocked else 1)
    elif endpoint == "signup":
        window = _positive_int(
            current_app.config.get("RATE_LIMIT_SIGNUP_WINDOW_SECONDS"), 3600, "RATE_LIMIT_SIGNUP_WINDOW_SECONDS"
        )
        limit = _positive_int(
            current_app.config.get("RATE_LIMIT_SIGNUP_IP_MAX"), 5, "RATE_LIMIT_SIGNUP_IP_MAX"
        )
        blocked, retry_after = _consume(
            connection, f"signup:ip:{ip_key}", limit, window, now
        )
    elif endpoint == "report_request":
        window = _positive_int(
            current_app.config.get("RATE_LIMIT_REPORT_WINDOW_SECONDS"), 3600, "RATE_LIMIT_REPORT_WINDOW_SECONDS"
        )
        limit = _positive_int(
            current_app.config.get("RATE_LIMIT_REPORT_IP_MAX"), 3, "RATE_LIMIT_REPORT_IP_MAX"
        )
        blocked, retry_after = _consume(
            connection, f"report:ip:{ip_key}", limit, window, now
        )

    # Bound storage without depending on a background worker or external cache.
    connection.execute(
        "DELETE FROM hexora_rate_limit_hits WHERE window_start < ?",
        (now - 86400,),
    )
    connection.commit()
    return retry_after if blocked else None


def _get_connection():
    # Import lazily to avoid changing the app/database import graph.
    from database import get_db

    return get_db()


def register_rate_limit(app):
    """Apply limits before endpoint handlers; only trusted REMOTE_ADDR is used."""

    @app.before_request
    def enforce_public_write_limits():
        if request.method != "POST" or request.endpoint not in {
            "login", "signup", "report_request"
        }:
            return None

        identifier = (
            request.form.get("email", "")
            if request.endpoint == "login"
            else None
        )
        try:
            retry_after = check_request_limits(
                request.endpoint, request.remote_addr, identifier
            )
        except Exception:
            current_app.logger.exception("rate_limit_storage_unavailable")
            response = make_response(
                "요청 제한 기능을 일시적으로 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.",
                503,
            )
            response.headers["Cache-Control"] = "no-store"
            return response

        if retry_after is None:
            return None

        response = make_response(
            "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.", 429
        )
        response.headers["Retry-After"] = str(retry_after)
        response.headers["Cache-Control"] = "no-store"
        return response
