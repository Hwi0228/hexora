"""Per-user encrypted Groq API credentials (BYOK)."""
import os

from cryptography.fernet import Fernet, InvalidToken
from flask import abort, g, redirect, render_template, request, url_for

from auth import login_required
from database import get_db
from hwp_engine.groq_segmenter import GroqSegmentationError


def _ensure_credentials_table():
    """Create the additive credentials table without a migration framework."""
    get_db().execute(
        """
        CREATE TABLE IF NOT EXISTS user_api_credentials (
            user_uuid TEXT PRIMARY KEY REFERENCES users(uuid) ON DELETE CASCADE,
            groq_api_key_encrypted TEXT NOT NULL,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _fernet():
    key = os.environ.get("GROQ_KEY_ENCRYPTION_KEY", "").strip()
    if not key:
        return None
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        raise RuntimeError(
            "GROQ_KEY_ENCRYPTION_KEY 형식이 올바르지 않습니다. Fernet 키를 설정해 주세요."
        ) from None


def get_user_groq_api_key(user_uuid):
    """Return the current user's decrypted key, never exposing it to templates."""
    _ensure_credentials_table()
    row = get_db().execute(
        "SELECT groq_api_key_encrypted FROM user_api_credentials WHERE user_uuid = ?",
        (user_uuid,),
    ).fetchone()
    if row is None:
        return None

    cipher = _fernet()
    if cipher is None:
        raise GroqSegmentationError(
            "저장된 API 키를 복호화할 수 없습니다. 서버의 GROQ_KEY_ENCRYPTION_KEY 설정을 확인해 주세요."
        )
    try:
        return cipher.decrypt(row["groq_api_key_encrypted"].encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, ValueError):
        raise GroqSegmentationError(
            "저장된 Groq API 키를 복호화하지 못했습니다. 암호화 키 설정을 확인해 주세요."
        ) from None


def groq_api_settings():
    _ensure_credentials_table()
    error = None
    saved = request.args.get("saved") == "1"
    deleted = request.args.get("deleted") == "1"
    try:
        encryption_ready = _fernet() is not None
    except RuntimeError as exc:
        encryption_ready = False
        error = str(exc)

    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "save":
            api_key = request.form.get("groq_api_key", "").strip()
            if not encryption_ready:
                error = error or "서버 암호화 키가 설정되지 않아 API 키를 저장할 수 없습니다."
            elif not api_key or len(api_key) > 512 or any(ord(char) < 32 for char in api_key):
                error = "Groq API 키를 확인해 주세요. 키는 1~512자이며 줄바꿈을 포함할 수 없습니다."
            else:
                cipher = _fernet()
                encrypted = cipher.encrypt(api_key.encode("utf-8")).decode("ascii")
                get_db().execute(
                    """
                    INSERT INTO user_api_credentials (user_uuid, groq_api_key_encrypted, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_uuid) DO UPDATE SET
                        groq_api_key_encrypted = excluded.groq_api_key_encrypted,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (g.user["uuid"], encrypted),
                )
                get_db().commit()
                return redirect(url_for("groq_api_settings", saved=1))
        elif action == "delete":
            get_db().execute(
                "DELETE FROM user_api_credentials WHERE user_uuid = ?",
                (g.user["uuid"],),
            )
            get_db().commit()
            return redirect(url_for("groq_api_settings", deleted=1))
        else:
            abort(400)

    configured = get_db().execute(
        "SELECT 1 FROM user_api_credentials WHERE user_uuid = ?",
        (g.user["uuid"],),
    ).fetchone() is not None
    return render_template(
        "groq_api_settings.html",
        nav_items=[],
        encryption_ready=encryption_ready,
        configured=configured,
        saved=saved,
        deleted=deleted,
        error=error,
    )


def register_groq_api_routes(app):
    app.add_url_rule(
        "/settings/api-keys",
        endpoint="groq_api_settings",
        view_func=login_required(groq_api_settings),
        methods=["GET", "POST"],
    )
