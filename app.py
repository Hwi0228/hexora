import os
import secrets
from pathlib import Path

from flask import Flask
from markupsafe import Markup

from auth import register_auth_routes
from dashboard_routes import register_dashboard_routes
from changelog_routes import register_changelog_routes
from hwp_routes import register_hwp_routes
from question_routes import register_question_routes
from workbook_routes import register_workbook_routes
from legal_routes import register_legal_routes
from admin_database_routes import register_admin_database_routes
from rich_text import render_rich_html
from sidebar import render_sidebar


def _is_production_environment():
    """Detect production deployments without relying on Flask's removed FLASK_ENV."""
    configured_environment = (
        os.environ.get("HEXORA_ENV")
        or os.environ.get("APP_ENV")
        or os.environ.get("FLASK_ENV")
        or ""
    ).strip().lower()
    render_environment = os.environ.get("RENDER", "").strip().lower() in {
        "1", "true", "yes",
    }
    return configured_environment in {"production", "prod"} or render_environment


def _validate_secret_key(value):
    """Reject short or obviously low-diversity session signing keys."""
    if not isinstance(value, str) or len(value) < 32:
        raise RuntimeError(
            "FLASK_SECRET_KEY must contain at least 32 characters. "
            "Generate a random key and store it as an environment variable."
        )

    frequencies = {}
    for character in value:
        frequencies[character] = frequencies.get(character, 0) + 1
    import math

    entropy_per_character = -sum(
        (count / len(value)) * math.log2(count / len(value))
        for count in frequencies.values()
    )
    if len(frequencies) < 12 or entropy_per_character < 3.5:
        raise RuntimeError(
            "FLASK_SECRET_KEY does not meet the minimum character-diversity "
            "requirement. Use a cryptographically random key."
        )
    return value


def _secret_key(app):
    configured_key = app.config.get("SECRET_KEY")
    if configured_key:
        return _validate_secret_key(configured_key)

    if _is_production_environment():
        raise RuntimeError(
            "FLASK_SECRET_KEY is required in production. "
            "Set a persistent, cryptographically random environment variable."
        )

    key_path = Path(app.instance_path) / ".secret_key"
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if not key_path.exists():
        try:
            with key_path.open("x", encoding="ascii") as key_file:
                key_file.write(secrets.token_hex(32))
        except FileExistsError:
            pass
    return _validate_secret_key(key_path.read_text(encoding="ascii").strip())


def create_app():
    app = Flask(__name__, template_folder="static/templates")
    app.jinja_env.filters["render_rich_html"] = lambda value: Markup(render_rich_html(value))
    app.jinja_env.globals["render_sidebar"] = render_sidebar
    database_type = os.environ.get("DATABASE_TYPE", "sqlite").strip().lower()
    if database_type == "postgres":
        database_type = "postgresql"
    if database_type not in {"sqlite", "postgresql"}:
        raise ValueError("DATABASE_TYPE must be 'sqlite' or 'postgresql'.")

    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_type == "postgresql" and not database_url:
        raise RuntimeError(
            "DATABASE_TYPE=postgresql requires a DATABASE_URL environment variable."
        )

    app.config["DATABASE_TYPE"] = database_type
    app.config["DATABASE_URL"] = database_url
    app.config["DATABASE"] = os.environ.get(
        "DATABASE_PATH",
        os.path.join(app.instance_path, "probocr.sqlite3"),
    )
    app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY")
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = (
        os.environ.get("FLASK_SESSION_COOKIE_SECURE", "").lower() == "true"
    )
    if not app.config["SECRET_KEY"]:
        app.config["SECRET_KEY"] = _secret_key(app)

    app.config["HEXORA_OPERATOR_NAME"] = os.environ.get("HEXORA_OPERATOR_NAME", "[운영자 성명 또는 상호]")
    app.config["HEXORA_OPERATOR_ADDRESS"] = os.environ.get("HEXORA_OPERATOR_ADDRESS", "[운영자 주소]")
    app.config["HEXORA_PRIVACY_CONTACT"] = os.environ.get("HEXORA_PRIVACY_CONTACT", "[개인정보 문의 이메일]")
    app.config["HEXORA_PRIVACY_OFFICER"] = os.environ.get("HEXORA_PRIVACY_OFFICER", "[개인정보 보호책임자 성명]")

    version_path = Path(__file__).resolve().parent / "VERSION"
    try:
        app.config["APP_VERSION"] = version_path.read_text(encoding="utf-8").strip() or "dev"
    except OSError:
        app.config["APP_VERSION"] = "dev"

    @app.context_processor
    def inject_app_version():
        return {
            "app_version": app.config["APP_VERSION"],
            "operator_name": app.config["HEXORA_OPERATOR_NAME"],
            "operator_address": app.config["HEXORA_OPERATOR_ADDRESS"],
            "privacy_contact": app.config["HEXORA_PRIVACY_CONTACT"],
            "privacy_officer": app.config["HEXORA_PRIVACY_OFFICER"],
        }

    register_auth_routes(app)
    register_dashboard_routes(app)
    register_changelog_routes(app)
    register_question_routes(app)
    register_workbook_routes(app)
    register_hwp_routes(app)
    register_legal_routes(app)
    register_admin_database_routes(app)
    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
