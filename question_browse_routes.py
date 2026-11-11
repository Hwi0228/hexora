import json
from pathlib import Path

from flask import abort, current_app, g, jsonify, redirect, render_template, request, url_for

from constants import NAV_ITEMS, SUBJECTS
from question_constants import QUESTION_CONTENT_FIELDS, QUESTION_FIELD_LABELS, CURRICULUM_STANDARDS
from question_ids import format_question_number, parse_question_number
from rich_text import render_rich_html
from database import get_db
from folder_service import get_folder_data
from parse_hwp import strip_choice_label
from curriculum_data import (
    DATASET_URL as CURRICULUM_DATASET_URL,
    DATASET_VERSION as CURRICULUM_DATASET_VERSION,
    CurriculumDataError,
    load_2022_standards,
    select_2022_standards,
)


def curriculum_standards():
    curriculum = request.args.get("curriculum", "2015 개정 교육과정")
    course = request.args.get("course", "").strip()
    unit = request.args.get("unit", "").strip()

    if curriculum == "2022 개정 교육과정":
        cache_path = (
            Path(current_app.instance_path)
            / "curriculum"
            / f"standards-{CURRICULUM_DATASET_VERSION}.json"
        )
        try:
            records = load_2022_standards(cache_path)
        except (CurriculumDataError, OSError):
            current_app.logger.exception("2022 curriculum dataset could not be loaded")
            return jsonify({
                "standards": [],
                "courses": [],
                "areas": [],
                "matched": False,
                "error": (
                    "2022 개정 교육과정 데이터를 불러오지 못했습니다. "
                    "잠시 후 다시 시도하거나 성취기준을 직접 입력해 주세요."
                ),
            }), 503

        result = select_2022_standards(
            records,
            subject=request.args.get("subject", "").strip(),
            grade=request.args.get("grade", "").strip(),
            course=course,
            area=request.args.get("area", "").strip(),
        )
        return jsonify({
            **result,
            "units": [],
            "dataset": {
                "version": CURRICULUM_DATASET_VERSION,
                "url": CURRICULUM_DATASET_URL,
            },
        })

    course_data = CURRICULUM_STANDARDS.get(curriculum, {}).get(course, {})
    if unit:
        standards = course_data.get(unit, [])
    else:
        standards = [
            standard
            for unit_standards in course_data.values()
            for standard in unit_standards
        ]
    return jsonify({
        "standards": standards,
        "units": list(course_data.keys()),
        "matched": bool(standards),
    })


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
    query += " ORDER BY questions.id DESC"
    rows = get_db().execute(query, parameters).fetchall()
    questions = []
    for row in rows:
        question = dict(row)
        question["choices"] = [
            render_rich_html(strip_choice_label(choice))
            for choice in json.loads(question["choices"] or "[]")
        ]
        for field in ("prompt", "answer", "explanation"):
            question[field] = render_rich_html(question[field])
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

    question = dict(_question_row(question_id))
    try:
        question["choices"] = json.loads(question.get("choices") or "[]")
    except (TypeError, json.JSONDecodeError):
        question["choices"] = []
    question["choices"] = [
        render_rich_html(strip_choice_label(str(choice or "")))
        for choice in question["choices"]
    ]
    for field in ("passage", "prompt", "examples", "answer", "explanation"):
        question[field] = render_rich_html(question.get(field, ""))
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
