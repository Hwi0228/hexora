
from flask import g, render_template

from auth import login_required
from constants import NAV_ITEMS
from database import get_db
from question_ids import format_question_number
from question_presentation import prepare_question_for_display


def dashboard():
    connection = get_db()
    user_uuid = g.user["uuid"]

    summary = connection.execute(
        """
        SELECT
            COUNT(*) AS question_count,
            COUNT(DISTINCT subject) AS subject_count,
            COUNT(DISTINCT CASE
                WHEN unit <> '' THEN subject || '|' || grade || '|' || unit
            END) AS unit_count
        FROM questions
        WHERE deleted_at IS NULL
        """
    ).fetchone()
    folder_count = connection.execute(
        "SELECT COUNT(*) FROM folders WHERE user_uuid = ?",
        (user_uuid,),
    ).fetchone()[0]

    subject_stats = connection.execute(
        """
        SELECT subject, COUNT(*) AS count
        FROM questions
        WHERE deleted_at IS NULL
        GROUP BY subject
        ORDER BY count DESC, LOWER(subject)
        """
    ).fetchall()

    recent_questions = connection.execute(
        """
        SELECT id, title, subject, grade, unit, passage, prompt, examples,
               choices, source, year, page
        FROM questions
        WHERE deleted_at IS NULL
        ORDER BY id DESC
        LIMIT 6
        """
    ).fetchall()
    questions = []
    for row in recent_questions:
        question = prepare_question_for_display(
            row, rich_fields=("passage", "prompt", "examples")
        )
        question["display_id"] = format_question_number(question["id"])
        questions.append(question)

    return render_template(
        "dashboard.html",
        question_count=summary["question_count"],
        subject_count=summary["subject_count"],
        unit_count=summary["unit_count"],
        folder_count=folder_count,
        subject_stats=subject_stats,
        recent_questions=questions,
        nav_items=NAV_ITEMS,
        active_page="dashboard",
    )


def register_dashboard_routes(app):
    app.add_url_rule(
        "/", endpoint="dashboard", view_func=login_required(dashboard), methods=["GET"]
    )
