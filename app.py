import os
import click
import secrets
from pathlib import Path

from flask import Flask, current_app
from werkzeug.security import generate_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
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
from mcp_api import mcp_api
from oauth_routes import register_oauth_routes


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
    # Allow the 16 MiB XML limit plus multipart framing; individual formats
    # are checked against their own stricter limits in the upload route.
    app.config["MAX_CONTENT_LENGTH"] = 18 * 1024 * 1024
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
    # Production must never send session cookies over an unencrypted connection.
    # The explicit flag remains available to opt in during local HTTPS development.
    app.config["SESSION_COOKIE_SECURE"] = (
        _is_production_environment()
        or os.environ.get("FLASK_SESSION_COOKIE_SECURE", "").strip().lower()
        in {"1", "true", "yes"}
    )
    if _is_production_environment():
        # Render terminates TLS at one trusted reverse proxy and forwards the
        # original scheme through X-Forwarded-Proto.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1)
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

    @app.errorhandler(413)
    def request_too_large(_error):
        return (
            "요청 크기가 허용 한도(18 MiB)를 초과했습니다. "
            "문서 파일 크기와 업로드 형식을 확인해 주세요.",
            413,
        )

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=()",
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "; ".join(
                (
                    "default-src 'self'",
                    "frame-src 'self' blob:",
                    "base-uri 'self'",
                    "object-src 'none'",
                    "frame-ancestors 'none'",
                    "form-action 'self'",
                    "img-src 'self' data: blob:",
                    "font-src 'self' data: https://cdn.jsdelivr.net",
                    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
                    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
                    "connect-src 'self'",
                )
            ),
        )
        if _is_production_environment():
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response

    register_auth_routes(app)
    register_dashboard_routes(app)
    register_changelog_routes(app)
    register_question_routes(app)
    register_workbook_routes(app)
    register_hwp_routes(app)
    register_legal_routes(app)
    register_admin_database_routes(app)
    app.register_blueprint(mcp_api)
    register_oauth_routes(app)

    @app.cli.command("create-admin")
    @click.option("--email", prompt=True, help="최초 관리자 계정 이메일")
    @click.option("--display-name", prompt=True, help="관리자 표시 이름")
    @click.password_option(confirmation_prompt=True)
    def create_admin(email, display_name, password):
        """명시적으로 최초 관리자 계정을 생성하거나 기존 계정을 승격합니다."""
        normalized_email = email.strip().lower()
        display_name = display_name.strip()
        if (
            len(normalized_email) > 254
            or "@" not in normalized_email
            or "." not in normalized_email.rsplit("@", 1)[-1]
        ):
            raise click.ClickException("올바른 이메일 주소를 입력해 주세요.")
        if not display_name or len(display_name) > 80:
            raise click.ClickException("표시 이름은 1~80자로 입력해 주세요.")
        if len(password) < 12 or len(password) > 256:
            raise click.ClickException("관리자 비밀번호는 12~256자로 입력해 주세요.")

        from database import begin_write_transaction, get_db

        connection = get_db()
        try:
            begin_write_transaction(connection, lock_table="users")
            admin_exists = connection.execute(
                "SELECT 1 FROM users WHERE role = 'admin' LIMIT 1"
            ).fetchone()
            if admin_exists:
                connection.rollback()
                raise click.ClickException(
                    "관리자 계정이 이미 존재합니다. 추가 부트스트랩은 허용되지 않습니다."
                )

            existing = connection.execute(
                "SELECT uuid FROM users WHERE email = ?", (normalized_email,)
            ).fetchone()
            if existing:
                user_uuid = existing["uuid"]
                connection.execute(
                    """
                    UPDATE users
                    SET display_name = ?, password_hash = ?, role = 'admin'
                    WHERE uuid = ?
                    """,
                    (display_name, generate_password_hash(password), user_uuid),
                )
                action = "기존 계정을 관리자 계정으로 승격했습니다."
            else:
                import uuid

                user_uuid = str(uuid.uuid4())
                connection.execute(
                    """
                    INSERT INTO users (uuid, email, display_name, password_hash, role)
                    VALUES (?, ?, ?, ?, 'admin')
                    """,
                    (
                        user_uuid,
                        normalized_email,
                        display_name,
                        generate_password_hash(password),
                    ),
                )
                action = "최초 관리자 계정을 생성했습니다."

            # Preserve legacy unowned content when the first administrator is bootstrapped.
            connection.execute(
                "UPDATE folders SET user_uuid = ? WHERE user_uuid IS NULL",
                (user_uuid,),
            )
            connection.execute(
                "UPDATE questions SET user_uuid = ? WHERE user_uuid IS NULL",
                (user_uuid,),
            )
            connection.commit()
        except click.ClickException:
            raise
        except Exception:
            connection.rollback()
            raise

        click.echo(action)


    @app.cli.command("create-mcp-service-user")
    @click.option("--email", default="hexora-mcp@service.invalid")
    @click.option("--display-name", default="HEXORA MCP")
    def create_mcp_service_user(email, display_name):
        """Create the non-interactive author identity used by the MCP integration."""
        import uuid

        from database import begin_write_transaction, get_db

        normalized_email = email.strip().lower()
        if (
            len(normalized_email) > 254
            or "@" not in normalized_email
            or not display_name.strip()
            or len(display_name.strip()) > 80
        ):
            raise click.ClickException("서비스 계정 이메일 또는 표시 이름이 올바르지 않습니다.")

        connection = get_db()
        existing = connection.execute(
            "SELECT uuid FROM users WHERE email = ?", (normalized_email,)
        ).fetchone()
        if existing:
            click.echo(existing["uuid"])
            return

        service_uuid = str(uuid.uuid4())
        random_password_hash = generate_password_hash(secrets.token_urlsafe(48))
        try:
            begin_write_transaction(connection, lock_table="users")
            connection.execute(
                """
                INSERT INTO users (uuid, email, display_name, password_hash, role)
                VALUES (?, ?, ?, ?, 'user')
                """,
                (service_uuid, normalized_email, display_name.strip(), random_password_hash),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

        click.echo(service_uuid)

    @app.cli.command("db-backup")
    @click.option("--output", type=click.Path(path_type=Path), default=None)
    def db_backup(output):
        """Create a verified SQLite or PostgreSQL backup archive."""
        from backup_restore import create_backup
        from database import get_db

        backend = current_app.config["DATABASE_TYPE"]
        connection = get_db()
        # This is a compatibility marker, not a schema-migration system.
        # Keep it at zero while the application has no explicit schema versioning.
        schema_version = 0
        source = (
            current_app.config["DATABASE"]
            if backend == "sqlite"
            else current_app.config["DATABASE_URL"]
        )
        try:
            destination = create_backup(
                backend,
                source,
                output=output,
                schema_version=schema_version,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(f"백업이 생성되고 검증되었습니다: {destination}")

    @app.cli.command("db-restore")
    @click.option("--backup", "backup_path", required=True, type=click.Path(path_type=Path, exists=True, dir_okay=False))
    @click.option(
        "--confirm-overwrite",
        is_flag=True,
        help="대상 DB의 기존 데이터를 덮어쓰는 작업임을 확인합니다.",
    )
    def db_restore(backup_path, confirm_overwrite):
        """Validate a backup and restore it to the configured database."""
        from backup_restore import restore_backup
        backend = current_app.config["DATABASE_TYPE"]
        target = (
            current_app.config["DATABASE"]
            if backend == "sqlite"
            else current_app.config["DATABASE_URL"]
        )
        supported_version = 0
        try:
            restore_backup(
                backup_path,
                backend,
                target,
                confirm_overwrite=confirm_overwrite,
                supported_schema_version=supported_version,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo("백업 검증 및 복구가 완료되었습니다.")

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
