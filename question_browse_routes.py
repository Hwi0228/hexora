
from flask import abort, current_app, g, redirect, render_template, request, url_for

from constants import NAV_ITEMS, SUBJECTS, LICENSE_CHOICES, SOURCE_TYPES, GRADE_OPTIONS
from question_constants import QUESTION_TYPES, COURSE_OPTIONS, SUBJECT_COURSE_OPTIONS
from question_ids import format_question_number, parse_question_number
from question_presentation import prepare_question_for_display
from question_repository import _question_row
from database import get_db
from folder_service import get_folder_data


def get_selected_owner():
    requested_uuid = request.args.get("user_uuid")
    if requested_uuid and g.user["role"] == "admin":
        selected_user = get_db().execute(
            "SELECT uuid, email, display_name, role FROM users WHERE uuid = ?",
            (requested_uuid,),
        ).fetchone()
        if selected_user is None:
            abort(404)
        return selected_user
    if requested_uuid and requested_uuid != g.user["uuid"]:
        abort(403)
    return g.user


def get_question_page_data():
    selected_subject = request.args.get("subject", "수학")
    if selected_subject not in SUBJECTS:
        selected_subject = "수학"
    selected_user = get_selected_owner()
    selected_user_uuid = selected_user["uuid"]
    selected_folder_uuid = request.args.get("folder")
    selected_folder = None
    if selected_folder_uuid:
        selected_folder = get_db().execute(
            "SELECT uuid, name FROM folders WHERE uuid = ? AND user_uuid = ?",
            (selected_folder_uuid, selected_user_uuid),
        ).fetchone()
        if selected_folder is None:
            abort(404)

    query = """
        SELECT questions.id, questions.user_uuid, questions.folder_uuid,
               questions.subject, questions.grade, questions.unit, questions.title,
               questions.course, questions.curriculum, questions.achievement_standard,
               questions.difficulty, questions.question_type, questions.points,
               questions.source_type, questions.exam, questions.original_question_number,
               questions.source_url, questions.license,
               questions.passage, questions.prompt, questions.examples,
               questions.choices, questions.answer, questions.explanation,
               questions.source, questions.year, questions.page, questions.created_at,
               COALESCE(question_notes.note, '') AS personal_note,
               users.display_name AS author_name,
               COALESCE(revisions.latest_revision, 1) AS revision_number
        FROM questions
        LEFT JOIN question_notes
          ON question_notes.question_id = questions.id
         AND question_notes.user_uuid = ?
        LEFT JOIN users ON users.uuid = questions.user_uuid
        LEFT JOIN (
            SELECT question_id, MAX(revision_number) AS latest_revision
            FROM question_revisions
            GROUP BY question_id
        ) AS revisions ON revisions.question_id = questions.id
        LEFT JOIN (
            SELECT question_id, MAX(created_at) AS last_modified
            FROM question_revisions GROUP BY question_id
        ) AS revision_dates ON revision_dates.question_id = questions.id
        WHERE questions.subject = ? AND questions.deleted_at IS NULL
    """
    parameters = [g.user["uuid"], selected_subject]
    if request.args.get("user_uuid"):
        query += " AND questions.user_uuid = ?"
        parameters.append(selected_user_uuid)
    if selected_folder_uuid:
        query += """
          AND folder_uuid IN (
              WITH RECURSIVE folder_descendants(uuid) AS (
                  SELECT uuid FROM folders WHERE uuid = ? AND user_uuid = ?
                  UNION ALL
                  SELECT folders.uuid
                  FROM folders
                  JOIN folder_descendants ON folders.parent_uuid = folder_descendants.uuid
                  WHERE folders.user_uuid = ?
              )
              SELECT uuid FROM folder_descendants
          )
        """
        parameters.extend(
            [selected_folder_uuid, selected_user_uuid, selected_user_uuid]
        )
    filter_values = {
        "q": request.args.get("q", "").strip()[:120],
        "curriculum": request.args.get("curriculum", "").strip(),
        "course": request.args.get("course", "").strip(),
        "grade": request.args.get("grade", "").strip(),
        "question_type": request.args.get("question_type", "").strip(),
        "source_type": request.args.get("source_type", "").strip(),
        "year": request.args.get("year", "").strip(),
        "license": request.args.get("license", "").strip(),
        "achievement_standard": request.args.get("achievement_standard", "").strip()[:120],
        "sort": request.args.get("sort", "latest").strip(),
    }
    exact_filters = (
        ("curriculum", "questions.curriculum", set(COURSE_OPTIONS)),
        ("course", "questions.course", None),
        ("grade", "questions.grade", set(GRADE_OPTIONS)),
        ("question_type", "questions.question_type", set(QUESTION_TYPES)),
        ("source_type", "questions.source_type", set(SOURCE_TYPES)),
        ("license", "questions.license", set(LICENSE_CHOICES)),
    )
    for key, column, allowed_values in exact_filters:
        value = filter_values[key]
        if value and (allowed_values is None or value in allowed_values):
            query += f" AND {column} = ?"
            parameters.append(value)
        elif value:
            filter_values[key] = ""

    if filter_values["year"]:
        try:
            year = int(filter_values["year"])
            if not 1 <= year <= 2200:
                raise ValueError
        except ValueError:
            filter_values["year"] = ""
        else:
            query += " AND questions.year = ?"
            parameters.append(year)

    like_operator = (
        "ILIKE"
        if current_app.config.get("DATABASE_TYPE") in {"postgres", "postgresql"}
        else "LIKE"
    )
    if filter_values["achievement_standard"]:
        query += (
            " AND COALESCE(questions.achievement_standard, '') "
            f"{like_operator} ?"
        )
        parameters.append(f"%{filter_values['achievement_standard']}%")

    if filter_values["q"]:
        query += f"""
          AND (
            COALESCE(questions.title, '') {like_operator} ? OR
            COALESCE(questions.passage, '') {like_operator} ? OR
            COALESCE(questions.prompt, '') {like_operator} ? OR
            COALESCE(questions.examples, '') {like_operator} ? OR
            COALESCE(questions.answer, '') {like_operator} ? OR
            COALESCE(questions.explanation, '') {like_operator} ?
          )
        """
        pattern = f"%{filter_values['q']}%"
        parameters.extend([pattern] * 6)

    if filter_values["sort"] not in {"latest", "modified", "relevance"}:
        filter_values["sort"] = "latest"
    if filter_values["sort"] == "modified":
        query += " ORDER BY COALESCE(revision_dates.last_modified, questions.created_at) DESC, questions.id DESC"
    elif filter_values["sort"] == "relevance" and filter_values["q"]:
        pattern = f"%{filter_values['q'].lower()}%"
        query += """
          ORDER BY CASE
            WHEN LOWER(COALESCE(questions.title, '')) = ? THEN 0
            WHEN LOWER(COALESCE(questions.title, '')) LIKE ? THEN 1
            WHEN LOWER(COALESCE(questions.prompt, '')) LIKE ? THEN 2
            ELSE 3 END, questions.id DESC
        """
        parameters.extend([filter_values["q"].lower(), pattern, pattern])
    else:
        query += " ORDER BY questions.id DESC"
    rows = get_db().execute(query, parameters).fetchall()
    questions = []
    for row in rows:
        question = prepare_question_for_display(
            row, rich_fields=("prompt", "answer", "explanation")
        )
        question["display_id"] = format_question_number(question["id"])
        questions.append(question)

    folder_tree, folder_options = get_folder_data(
        selected_subject, selected_user_uuid
    )
    folder_names = {option["uuid"]: option["name"] for option in folder_options}
    for question in questions:
        question["folder_name"] = folder_names.get(question["folder_uuid"])
    for question in questions:
        question["can_manage_folder"] = question["user_uuid"] == g.user["uuid"]
        question["can_delete_question"] = (
            question["user_uuid"] == g.user["uuid"] or g.user["role"] == "admin"
        )
    return {
        "nav_items": NAV_ITEMS,
        "subjects": SUBJECTS,
        "selected_subject": selected_subject,
        "questions": questions,
        "added": request.args.get("added") == "1",
        "folder_tree": folder_tree,
        "folder_options": folder_options,
        "selected_folder_uuid": selected_folder_uuid,
        "selected_folder_name": selected_folder["name"] if selected_folder else None,
        "folder_added": request.args.get("folder_added") == "1",
        "folder_moved": request.args.get("folder_moved") == "1",
        "folder_error": request.args.get("folder_error"),
        "selected_user": selected_user,
        "can_manage_questions": True,
        "can_manage_folders": selected_user_uuid == g.user["uuid"],
        "selected_user_uuid": selected_user_uuid,
        "filters": filter_values,
        "filter_options": {
            "curricula": list(COURSE_OPTIONS),
            "courses": sorted(set(SUBJECT_COURSE_OPTIONS.get(selected_subject, [])) | {
                course for courses in COURSE_OPTIONS.values() for course in courses
            }),
            "grades": list(GRADE_OPTIONS),
            "question_types": list(QUESTION_TYPES),
            "source_types": list(SOURCE_TYPES),
            "licenses": LICENSE_CHOICES,
        },
        "result_count": len(questions),
    }


def main():
    return render_template(
        "main.html", **get_question_page_data(), active_page="main"
    )


def admin_users():
    users = get_db().execute(
        """
        SELECT users.uuid, users.email, users.display_name, users.role,
               users.created_at, COUNT(questions.id) AS question_count
        FROM users
        LEFT JOIN questions ON questions.user_uuid = users.uuid
        GROUP BY users.uuid
        ORDER BY users.created_at, users.email
        """
    ).fetchall()
    return render_template(
        "admin_users.html",
        users=users,
        nav_items=NAV_ITEMS,
        active_page="admin_users",
    )


def question_by_code():
    code = request.args.get("code", "").strip().upper()
    question_id = parse_question_number(code)
    if question_id is None:
        abort(404)

    question = prepare_question_for_display(
        _question_row(question_id),
        rich_fields=("passage", "prompt", "examples", "answer", "explanation"),
    )
    question["display_id"] = format_question_number(question_id)
    question["can_manage_question"] = (
        question["user_uuid"] == g.user["uuid"] or g.user["role"] == "admin"
    )
    return render_template(
        "question_code.html", nav_items=NAV_ITEMS,
        question=question, active_page="main",
    )


def delete_question(question_id):
    question = _question_row(question_id)
    if question["user_uuid"] != g.user["uuid"] and g.user["role"] != "admin":
        abort(403)
    connection = get_db()
    connection.execute(
        "UPDATE questions SET deleted_at = CURRENT_TIMESTAMP "
        "WHERE id = ? AND deleted_at IS NULL",
        (question_id,),
    )
    connection.commit()
    return redirect(url_for("main", subject=question["subject"]))


def restore_deleted_question(question_id):
    question = _question_row(question_id)
    if question["user_uuid"] != g.user["uuid"] and g.user["role"] != "admin":
        abort(403)
    connection = get_db()
    connection.execute(
        "UPDATE questions SET deleted_at = NULL WHERE id = ?",
        (question_id,),
    )
    connection.commit()
    return redirect(url_for("question_by_code", code=format_question_number(question_id)))
