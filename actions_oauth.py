"""OAuth 2.0 authorization endpoints for HEXORA GPT Actions.

The GPT Action is a confidential OAuth client. Its client credentials and exact
ChatGPT callback URL are configured only in the hosting environment.
"""
import hashlib
import hmac
import os
import secrets
import time
from urllib.parse import urlencode

from flask import Blueprint, abort, jsonify, redirect, request, session
from markupsafe import escape

from database import get_db

actions_oauth = Blueprint("actions_oauth", __name__)
ALLOWED_SCOPES = {"questions:read", "questions:write"}


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _client_credentials():
    return (
        os.environ.get("HEXORA_ACTIONS_CLIENT_ID", "").strip(),
        os.environ.get("HEXORA_ACTIONS_CLIENT_SECRET", ""),
    )


def _allowed_redirect_uris():
    return {
        item.strip()
        for item in os.environ.get("HEXORA_ACTIONS_REDIRECT_URIS", "").splitlines()
        if item.strip()
    }


def _ensure_action_tables(db):
    db.execute(
        """CREATE TABLE IF NOT EXISTS actions_oauth_tokens (
            token_hash TEXT PRIMARY KEY,
            token_type TEXT NOT NULL,
            client_id TEXT NOT NULL,
            user_uuid TEXT NOT NULL,
            scope TEXT NOT NULL,
            expires_at BIGINT NOT NULL,
            created_at BIGINT NOT NULL
        )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS actions_oauth_codes (
            code_hash TEXT PRIMARY KEY,
            client_id TEXT NOT NULL,
            user_uuid TEXT NOT NULL,
            redirect_uri TEXT NOT NULL,
            scope TEXT NOT NULL,
            expires_at BIGINT NOT NULL,
            created_at BIGINT NOT NULL
        )"""
    )


def _valid_client(client_id, client_secret):
    expected_id, expected_secret = _client_credentials()
    return bool(
        expected_id
        and expected_secret
        and hmac.compare_digest(expected_id, str(client_id))
        and hmac.compare_digest(expected_secret, str(client_secret))
    )


@actions_oauth.get("/actions/oauth/authorize")
def authorize():
    db = get_db()
    _ensure_action_tables(db)

    configured_client_id, _ = _client_credentials()
    client_id = request.args.get("client_id", "")
    redirect_uri = request.args.get("redirect_uri", "")
    state = request.args.get("state", "")
    response_type = request.args.get("response_type", "")
    scope = request.args.get("scope", "questions:read")

    if (
        not configured_client_id
        or not hmac.compare_digest(configured_client_id, client_id)
        or redirect_uri not in _allowed_redirect_uris()
        or response_type != "code"
        or not state
        or len(state) > 512
        or not set(scope.split()).issubset(ALLOWED_SCOPES)
        or not scope.split()
    ):
        return jsonify({"error": "invalid_request"}), 400

    if not session.get("user_uuid"):
        return redirect("/login?" + urlencode({"next": request.full_path.rstrip("?")}))

    safe_client_id = escape(client_id)
    safe_redirect_uri = escape(redirect_uri)
    safe_state = escape(state)
    safe_scope = escape(scope)
    scope_label = escape(", ".join(scope.split()))
    csrf_value = escape(session.get("csrf_token", ""))
    html = f"""<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HEXORA 계정 연결</title>
<main style="max-width:560px;margin:10vh auto;padding:24px;font:16px system-ui">
  <h1>HEXORA 계정 연결</h1>
  <p>ChatGPT가 HEXORA 계정으로 요청을 보내도록 허용할까요?</p>
  <p>요청 권한: <strong>{scope_label}</strong></p>
  <p>문항 등록 권한은 문항을 공유 문제 은행에 추가할 수 있습니다.</p>
  <form method="post">
    <input type="hidden" name="client_id" value="{safe_client_id}">
    <input type="hidden" name="redirect_uri" value="{safe_redirect_uri}">
    <input type="hidden" name="state" value="{safe_state}">
    <input type="hidden" name="scope" value="{safe_scope}">
    <input type="hidden" name="_csrf_token" value="{csrf_value}">
    <button name="decision" value="allow">허용</button>
    <button name="decision" value="deny">거부</button>
  </form>
</main>"""
    return html


@actions_oauth.post("/actions/oauth/authorize")
def authorize_post():
    db = get_db()
    _ensure_action_tables(db)

    if not session.get("user_uuid") or not hmac.compare_digest(
        str(session.get("csrf_token", "")),
        str(request.form.get("_csrf_token", "")),
    ):
        abort(400)

    configured_client_id, _ = _client_credentials()
    client_id = request.form.get("client_id", "")
    redirect_uri = request.form.get("redirect_uri", "")
    state = request.form.get("state", "")
    scope = request.form.get("scope", "questions:read")
    if (
        not configured_client_id
        or not hmac.compare_digest(configured_client_id, client_id)
        or redirect_uri not in _allowed_redirect_uris()
        or not state
        or len(state) > 512
        or not set(scope.split()).issubset(ALLOWED_SCOPES)
        or not scope.split()
    ):
        abort(400)

    query = {"state": state}
    if request.form.get("decision") != "allow":
        query["error"] = "access_denied"
        return redirect(redirect_uri + "?" + urlencode(query))

    code = secrets.token_urlsafe(40)
    now = int(time.time())
    db.execute(
        """INSERT INTO actions_oauth_codes
        (code_hash, client_id, user_uuid, redirect_uri, scope, expires_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (_digest(code), client_id, session["user_uuid"], redirect_uri, scope,
         now + 300, now),
    )
    db.commit()
    query["code"] = code
    return redirect(redirect_uri + "?" + urlencode(query))


@actions_oauth.post("/actions/oauth/token")
def token():
    db = get_db()
    _ensure_action_tables(db)

    body = request.form if request.form else (request.get_json(silent=True) or {})
    client_id = str(body.get("client_id", ""))
    client_secret = str(body.get("client_secret", ""))
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Basic "):
        import base64
        try:
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
            client_id, client_secret = decoded.split(":", 1)
        except (ValueError, UnicodeDecodeError):
            return jsonify({"error": "invalid_client"}), 401
    if not _valid_client(client_id, client_secret):
        return jsonify({"error": "invalid_client"}), 401

    now = int(time.time())
    grant_type = body.get("grant_type", "")
    if grant_type == "authorization_code":
        code = str(body.get("code", ""))
        code_hash = _digest(code)
        record = db.execute(
            "SELECT * FROM actions_oauth_codes WHERE code_hash = ?",
            (code_hash,),
        ).fetchone()
        if (
            record is None
            or record["expires_at"] < now
            or record["client_id"] != client_id
            or record["redirect_uri"] != body.get("redirect_uri")
        ):
            return jsonify({"error": "invalid_grant"}), 400
        db.execute("DELETE FROM actions_oauth_codes WHERE code_hash = ?", (code_hash,))
        user_uuid, scope = record["user_uuid"], record["scope"]
    elif grant_type == "refresh_token":
        refresh = str(body.get("refresh_token", ""))
        token_hash = _digest(refresh)
        record = db.execute(
            """SELECT * FROM actions_oauth_tokens
            WHERE token_hash = ? AND token_type = 'refresh_token'""",
            (token_hash,),
        ).fetchone()
        if (
            record is None
            or record["expires_at"] < now
            or record["client_id"] != client_id
        ):
            return jsonify({"error": "invalid_grant"}), 400
        db.execute("DELETE FROM actions_oauth_tokens WHERE token_hash = ?", (token_hash,))
        user_uuid, scope = record["user_uuid"], record["scope"]
    else:
        return jsonify({"error": "unsupported_grant_type"}), 400

    access_token = secrets.token_urlsafe(48)
    refresh_token = secrets.token_urlsafe(56)
    for value, kind, lifetime in (
        (access_token, "access_token", 3600),
        (refresh_token, "refresh_token", 30 * 24 * 3600),
    ):
        db.execute(
            """INSERT INTO actions_oauth_tokens
            (token_hash, token_type, client_id, user_uuid, scope, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (_digest(value), kind, client_id, user_uuid, scope, now + lifetime, now),
        )
    db.commit()
    return jsonify({
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": 3600,
        "refresh_token": refresh_token,
        "scope": scope,
    })


def register_actions_oauth_routes(app):
    app.register_blueprint(actions_oauth)
