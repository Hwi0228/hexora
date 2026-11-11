"""Admin-only database reset workflow for HEXORA."""

from flask import current_app, flash, g, redirect, render_template, request, url_for

from auth import admin_required
from database import begin_write_transaction, get_db


CONFIRMATION_PHRASE = "초기화 실행"


def _database_counts(connection):
    tables = ("users", "questions", "folders", "workbooks", "rights_reports")
    counts = {}
    for table in tables:
        counts[table] = connection.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
    counts["admins"] = connection.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'admin'"
    ).fetchone()[0]
    counts["members"] = counts["users"] - counts["admins"]
    return counts


def _reset_database(connection):
    """Delete service data and non-admin accounts in one transaction."""
    begin_write_transaction(connection)

    if getattr(connection, "backend", "sqlite") == "postgresql":
        connection.execute(
            "LOCK TABLE users, folders, questions, workbooks, rights_reports "
            "IN ACCESS EXCLUSIVE MODE"
        )

    before = _database_counts(connection)

    connection.execute("DELETE FROM workbooks")
    connection.execute("DELETE FROM questions")

    # folders.parent_uuid is RESTRICT; detach the hierarchy before deletion.
    connection.execute("UPDATE folders SET parent_uuid = NULL")
    connection.execute("DELETE FROM folders")

    connection.execute("DELETE FROM rights_reports")
    connection.execute("DELETE FROM users WHERE role <> 'admin'")
    connection.commit()
    return before


def register_admin_database_routes(app):
    @app.route("/admin/database-reset", methods=["GET", "POST"])
    @admin_required
    def admin_database_reset():
        connection = get_db()
        counts = _database_counts(connection)

        if request.method == "POST":
            phrase = request.form.get("confirmation", "")
            acknowledged = request.form.get("acknowledge_irreversible") == "1"
            if phrase != CONFIRMATION_PHRASE or not acknowledged:
                return render_template(
                    "admin_database_reset.html",
                    counts=counts,
                    confirmation_phrase=CONFIRMATION_PHRASE,
                    error="확인 문구와 최종 확인 항목을 모두 정확히 입력해 주세요.",
                    completed=False,
                ), 400

            try:
                deleted_counts = _reset_database(connection)
            except Exception:
                connection.rollback()
                current_app.logger.exception("HEXORA administrator database reset failed")
                raise

            current_app.logger.warning(
                "HEXORA database reset completed by admin_uuid=%s backend=%s counts=%s",
                g.user["uuid"],
                getattr(connection, "backend", "sqlite"),
                deleted_counts,
            )
            flash("DB 초기화가 완료되었습니다. 관리자 계정은 유지되었습니다.", "success")
            return redirect(url_for("admin_database_reset", completed="1"))

        return render_template(
            "admin_database_reset.html",
            counts=counts,
            confirmation_phrase=CONFIRMATION_PHRASE,
            error=None,
            completed=request.args.get("completed") == "1",
        )
