"""OAuth 2.1 authorization server endpoints for HEXORA MCP clients.

Opaque credentials are stored only as SHA-256 hashes in the configured HEXORA
database. Authorization codes are single-use and bound to PKCE S256.
"""
import hashlib
import hmac
import json
import os
import secrets
import time
from urllib.parse import urlencode

from flask import Blueprint, abort, jsonify, redirect, request, session
from markupsafe import escape
from database import get_db

oauth = Blueprint("oauth", __name__)
ISSUER = "https://hexora.kro.kr"
RESOURCE = os.environ.get("MCP_PUBLIC_URL", "https://hexora-mcp.onrender.com").rstrip("/") + "/mcp"
ALLOWED_SCOPES = {"questions:read", "questions:write"}


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def ensure_tables(db):
    statements = (
        """CREATE TABLE IF NOT EXISTS oauth_clients (
            client_id TEXT PRIMARY KEY, client_name TEXT NOT NULL,
            redirect_uris TEXT NOT NULL, created_at BIGINT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS oauth_codes (
            code_hash TEXT PRIMARY KEY, client_id TEXT NOT NULL,
            user_uuid TEXT NOT NULL, redirect_uri TEXT NOT NULL,
            code_challenge TEXT NOT NULL, scope TEXT NOT NULL,
            expires_at BIGINT NOT NULL, created_at BIGINT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS oauth_tokens (
            token_hash TEXT PRIMARY KEY, token_type TEXT NOT NULL,
            client_id TEXT NOT NULL, user_uuid TEXT NOT NULL,
            scope TEXT NOT NULL, expires_at BIGINT NOT NULL,
            created_at BIGINT NOT NULL)""",
    )
    for statement in statements:
        db.execute(statement)


def server_token_ok():
    expected = os.environ.get("HEXORA_MCP_API_TOKEN", "")
    supplied = request.headers.get("Authorization", "")
    supplied = supplied[7:] if supplied.startswith("Bearer ") else ""
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


@oauth.get("/.well-known/oauth-authorization-server")
def authorization_metadata():
    return jsonify({
        "issuer": ISSUER,
        "authorization_endpoint": ISSUER + "/oauth/authorize",
        "token_endpoint": ISSUER + "/oauth/token",
        "registration_endpoint": ISSUER + "/oauth/register",
        "revocation_endpoint": ISSUER + "/oauth/revoke",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": sorted(ALLOWED_SCOPES),
    })


@oauth.get("/.well-known/oauth-protected-resource/mcp")
def protected_resource_metadata():
    return jsonify({
        "resource": RESOURCE,
        "authorization_servers": [ISSUER],
        "bearer_methods_supported": ["header"],
        "scopes_supported": sorted(ALLOWED_SCOPES),
    })


@oauth.post("/oauth/register")
def register_client():
    body = request.get_json(silent=True) or {}
    redirects = body.get("redirect_uris")
    if (not isinstance(redirects, list) or not redirects
            or any(not isinstance(uri, str) or not uri.startswith(("https://", "http://localhost", "http://127.0.0.1"))
                   for uri in redirects)):
        return jsonify({"error": "invalid_redirect_uri"}), 400
    if body.get("token_endpoint_auth_method", "none") != "none":
        return jsonify({"error": "invalid_client_metadata"}), 400
    db = get_db()
    ensure_tables(db)
    client_id = secrets.token_urlsafe(24)
    db.execute(
        "INSERT INTO oauth_clients (client_id, client_name, redirect_uris, created_at) VALUES (?, ?, ?, ?)",
        (client_id, str(body.get("client_name") or "MCP client")[:120],
         json.dumps(redirects), int(time.time())),
    )
    db.commit()
    return jsonify({
        "client_id": client_id, "client_name": str(body.get("client_name") or "MCP client")[:120],
        "redirect_uris": redirects, "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"], "token_endpoint_auth_method": "none",
    }), 201


@oauth.get("/oauth/authorize")
def authorize():
    db = get_db()
    ensure_tables(db)
    client_id = request.args.get("client_id", "")
    redirect_uri = request.args.get("redirect_uri", "")
    state = request.args.get("state", "")
    challenge = request.args.get("code_challenge", "")
    method = request.args.get("code_challenge_method", "")
    response_type = request.args.get("response_type", "")
    scope = request.args.get("scope", "questions:read")
    client = db.execute("SELECT * FROM oauth_clients WHERE client_id = ?", (client_id,)).fetchone()
    if (client is None or redirect_uri not in json.loads(client["redirect_uris"])
            or response_type != "code" or method != "S256" or len(challenge) != 43
            or not set(scope.split()).issubset(ALLOWED_SCOPES)):
        return jsonify({"error": "invalid_request"}), 400
    if not session.get("user_uuid"):
        return redirect("/login?" + urlencode({"next": request.full_path.rstrip("?")}))

    # Bind the consent form to the exact authorization request. Never trust
    # hidden form fields for client, redirect, state, PKCE, or granted scopes.
    now = int(time.time())
    pending_requests = session.get("oauth_pending_authorizations", {})
    if not isinstance(pending_requests, dict):
        pending_requests = {}
    pending_requests = {
        key: value for key, value in pending_requests.items()
        if isinstance(value, dict) and value.get("expires_at", 0) >= now
    }
    request_id = secrets.token_urlsafe(24)
    pending_requests[request_id] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "scope": scope,
        "expires_at": now + 600,
    }
    while len(pending_requests) > 5:
        pending_requests.pop(next(iter(pending_requests)))
    session["oauth_pending_authorizations"] = pending_requests

    safe_name = escape(str(client["client_name"]))
    safe_request_id = escape(request_id)
    html = f"""<!doctype html><meta charset=utf-8><title>HEXORA 연결 승인</title>
    <main style="max-width:520px;margin:10vh auto;font:16px system-ui;padding:24px">
    <h1>HEXORA 계정 연결</h1><p><b>{safe_name}</b> 앱이 HEXORA 계정에 접근하려고 합니다.</p>
    <p>허용 권한: {", ".join(scope.split())}</p>
    <form method=post><input type=hidden name=request_id value="{safe_request_id}">
    <input type=hidden name=_csrf_token value="{session.get('csrf_token','')}">
    <button name=decision value=allow>허용</button>
    <button name=decision value=deny>거부</button></form></main>"""
    return html


@oauth.post("/oauth/authorize")
def authorize_post():
    db = get_db()
    ensure_tables(db)
    return _authorize_post(db)


def _authorize_post(db):
    if not session.get("user_uuid") or not hmac.compare_digest(
        str(session.get("csrf_token", "")), str(request.form.get("_csrf_token", ""))
    ):
        abort(400)

    request_id = request.form.get("request_id", "")
    pending_requests = session.get("oauth_pending_authorizations", {})
    pending = pending_requests.get(request_id) if isinstance(pending_requests, dict) else None
    now = int(time.time())
    if not isinstance(pending, dict) or pending.get("expires_at", 0) < now:
        abort(400)

    client_id = pending["client_id"]
    redirect_uri = pending["redirect_uri"]
    state = pending["state"]
    code_challenge = pending["code_challenge"]
    scope = pending["scope"]
    client = db.execute("SELECT * FROM oauth_clients WHERE client_id = ?", (client_id,)).fetchone()
    if client is None or redirect_uri not in json.loads(client["redirect_uris"]):
        abort(400)

    # Consume this consent request exactly once, regardless of allow/deny.
    pending_requests.pop(request_id, None)
    session["oauth_pending_authorizations"] = pending_requests

    if request.form.get("decision") != "allow":
        return redirect(redirect_uri + ("&" if "?" in redirect_uri else "?") + urlencode({"error": "access_denied", "state": state}))

    code = secrets.token_urlsafe(32)
    db.execute(
        """INSERT INTO oauth_codes
        (code_hash, client_id, user_uuid, redirect_uri, code_challenge, scope, expires_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (digest(code), client_id, session["user_uuid"], redirect_uri,
         code_challenge, scope, now + 300, now),
    )
    db.commit()
    return redirect(redirect_uri + ("&" if "?" in redirect_uri else "?") + urlencode({"code": code, "state": state}))


@oauth.post("/oauth/token")
def token():
    db = get_db()
    ensure_tables(db)
    body = request.form if request.form else (request.get_json(silent=True) or {})
    grant = body.get("grant_type", "")
    now = int(time.time())
    if grant == "authorization_code":
        code = str(body.get("code", ""))
        record = db.execute("SELECT * FROM oauth_codes WHERE code_hash = ?", (digest(code),)).fetchone()
        if record is None:
            return jsonify({"error": "invalid_grant"}), 400
        db.execute("DELETE FROM oauth_codes WHERE code_hash = ?", (digest(code),))
        db.commit()
        verifier = str(body.get("code_verifier", ""))
        computed = __import__("base64").urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        if (record["expires_at"] < now or record["client_id"] != body.get("client_id")
                or record["redirect_uri"] != body.get("redirect_uri")
                or not hmac.compare_digest(computed, record["code_challenge"])):
            return jsonify({"error": "invalid_grant"}), 400
        user_uuid, client_id, scope = record["user_uuid"], record["client_id"], record["scope"]
    elif grant == "refresh_token":
        old = str(body.get("refresh_token", ""))
        record = db.execute(
            "SELECT * FROM oauth_tokens WHERE token_hash = ? AND token_type = 'refresh_token'",
            (digest(old),),
        ).fetchone()
        if record is None or record["expires_at"] < now or record["client_id"] != body.get("client_id"):
            return jsonify({"error": "invalid_grant"}), 400
        db.execute("DELETE FROM oauth_tokens WHERE token_hash = ?", (digest(old),))
        user_uuid, client_id, scope = record["user_uuid"], record["client_id"], record["scope"]
    else:
        return jsonify({"error": "unsupported_grant_type"}), 400
    access, refresh = secrets.token_urlsafe(40), secrets.token_urlsafe(48)
    for value, kind, ttl in ((access, "access_token", 3600), (refresh, "refresh_token", 2592000)):
        db.execute(
            """INSERT INTO oauth_tokens (token_hash, token_type, client_id, user_uuid, scope, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (digest(value), kind, client_id, user_uuid, scope, now + ttl, now),
        )
    db.commit()
    return jsonify({"access_token": access, "token_type": "Bearer", "expires_in": 3600,
                    "refresh_token": refresh, "scope": scope})


@oauth.post("/oauth/revoke")
def revoke():
    db = get_db()
    ensure_tables(db)
    body = request.form if request.form else (request.get_json(silent=True) or {})
    value = str(body.get("token", ""))
    db.execute("DELETE FROM oauth_tokens WHERE token_hash = ?", (digest(value),))
    db.commit()
    return "", 200


@oauth.post("/oauth/introspect")
def introspect():
    if not server_token_ok():
        abort(401)
    db = get_db()
    ensure_tables(db)
    value = request.form.get("token", "") or (request.get_json(silent=True) or {}).get("token", "")
    row = db.execute(
        """SELECT t.user_uuid, t.scope, t.expires_at, u.email, u.display_name, u.role
        FROM oauth_tokens t JOIN users u ON u.uuid = t.user_uuid
        WHERE t.token_hash = ? AND t.token_type = 'access_token'""",
        (digest(str(value)),),
    ).fetchone()
    if row is None or row["expires_at"] < int(time.time()):
        return jsonify({"active": False})
    return jsonify({"active": True, "sub": row["user_uuid"], "scope": row["scope"],
                    "exp": row["expires_at"], "email": row["email"],
                    "name": row["display_name"], "role": row["role"]})


def register_oauth_routes(app):
    app.register_blueprint(oauth)
