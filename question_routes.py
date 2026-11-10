import json
import uuid

from pathlib import Path

from flask import abort, current_app, g, jsonify, redirect, render_template, request, url_for

from auth import admin_required, login_required
from constants import NAV_ITEMS, SUBJECTS, LICENSE_CHOICES, SOURCE_TYPES
from question_constants import (
    QUESTION_CONTENT_FIELDS, QUESTION_FIELD_LABELS, QUESTION_TYPES, DIFFICULTIES,
    COURSE_OPTIONS, SUBJECT_COURSE_OPTIONS,
    CURRICULUM_STANDARDS,
)
from question_ids import BASE36_ALPHABET, BASE36_WIDTH, format_question_number, parse_question_number
from rich_text import sanitize_rich_html, _rich_text_has_content, render_rich_html
from database import begin_write_transaction, get_db
from question_drafts import _delete_question_draft, _load_question_draft, _save_question_draft
from question_revisions import _ensure_initial_question_revision, _insert_question_revision, _question_snapshot
from question_repository import _question_form_values, _question_row
from question_validation import _collect_question_data, _form_values_from_data
from folder_service import get_folder_data
from parse_hwp import normalize_katex_markup, strip_choice_label
from hmleq_converter import HmleqConversionError, HmleqUnavailable, convert_hancom_to_latex as run_hmleq
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

def render_question_form(
    form_data=None, errors=None, status=200, *, mode="create",
    question=None, base_revision=None, draft_saved=False,
    draft_updated_at=None, draft_conflict=False,
):
    _, folder_options = get_folder_data("수학", g.user["uuid"])
    form_data = dict(form_data or {})
    return (
        render_template(
            "question_form.html",
            nav_items=NAV_ITEMS,
            subjects=SUBJECTS,
            folder_options=folder_options,
            form_data=form_data,
            errors=errors or [],
            mode=mode,
            question=question,
            question_number=(
                format_question_number(question["id"]) if question is not None else None
            ),
            base_revision=base_revision,
            question_types=QUESTION_TYPES,
            difficulties=DIFFICULTIES,
            source_types=SOURCE_TYPES,
            license_choices=LICENSE_CHOICES,
            curriculum_options=list(COURSE_OPTIONS.keys()),
            course_options=COURSE_OPTIONS,
            subject_course_options=SUBJECT_COURSE_OPTIONS,
            draft_saved=draft_saved,
            draft_updated_at=draft_updated_at or form_data.get("draft_updated_at"),
            draft_conflict=draft_conflict,
        ),
        status,
    )

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

def new_folder():
    name = request.form.get("name", "").strip()
    parent_value = request.form.get("parent_uuid", "").strip()
    if not name or len(name) > 100:
        abort(400, description="폴더 이름은 1자 이상 100자 이내로 입력해 주세요.")

    parent_uuid = parent_value or None
    if parent_uuid and get_db().execute(
        "SELECT 1 FROM folders WHERE uuid = ? AND user_uuid = ?",
        (parent_uuid, g.user["uuid"]),
    ).fetchone() is None:
        abort(400, description="선택한 상위 폴더가 없습니다.")

    if parent_uuid is None:
        duplicate = get_db().execute(
            "SELECT 1 FROM folders WHERE user_uuid = ? AND parent_uuid IS NULL AND name = ?",
            (g.user["uuid"], name),
        ).fetchone()
    else:
        duplicate = get_db().execute(
            """
            SELECT 1 FROM folders
            WHERE user_uuid = ? AND parent_uuid = ? AND name = ?
            """,
            (g.user["uuid"], parent_uuid, name),
        ).fetchone()
    if duplicate:
        return redirect(
            url_for(
                "main",
                subject=request.form.get("subject", "수학"),
                folder=request.form.get("current_folder") or None,
                folder_error="duplicate",
            )
        )

    folder_uuid = str(uuid.uuid4())
    get_db().execute(
        """
        INSERT INTO folders (uuid, user_uuid, name, parent_uuid)
        VALUES (?, ?, ?, ?)
        """,
        (folder_uuid, g.user["uuid"], name, parent_uuid),
    )
    get_db().commit()
    return redirect(
        url_for(
            "main",
            subject=request.form.get("subject", "수학"),
            folder=folder_uuid,
            folder_added=1,
        )
    )



def new_question():
    if request.method == "GET":
        if request.args.get("discard_draft") == "1":
            _delete_question_draft()
            get_db().commit()
        draft = _load_question_draft()
        return render_question_form(
            draft or {}, draft_saved=request.args.get("draft_saved") == "1",
            draft_updated_at=(draft or {}).get("draft_updated_at"),
        )

    data, errors = _collect_question_data(request.form)
    # Personal folders are managed after publication from the question's
    # "문제 더보기" menu, not from the authoring form.
    data["folder_uuid"] = None
    if request.form.get("form_action") == "draft":
        _save_question_draft(data)
        return redirect(url_for("new_question", draft_saved=1))

    if errors:
        return render_question_form(
            _form_values_from_data(data), errors, 400
        )

    connection = get_db()
    try:
        begin_write_transaction(connection)
        cursor = connection.execute(
            """
            INSERT INTO questions (
                user_uuid, folder_uuid, subject, grade, unit, passage, prompt,
                examples, choices, answer, explanation, source, year, page,
                difficulty, question_type, points, course, curriculum,
                achievement_standard, source_type, exam, original_question_number,
                source_url, license, title
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                g.user["uuid"], data["folder_uuid"], data["subject"], data["grade"],
                data["unit"], data["passage"], data["prompt"], data["examples"],
                json.dumps(data["choices"], ensure_ascii=False), data["answer"],
                data["explanation"], data["source"], data["year"], data["page"],
                data["difficulty"], data["question_type"], data["points"],
                data["course"], data["curriculum"], data["achievement_standard"],
                data["source_type"], data["exam"], data["original_question_number"],
                data["source_url"], data["license"], data["title"],
            ),
        )
        question_id = cursor.fetchone()["id"]
        question = connection.execute(
            "SELECT * FROM questions WHERE id = ?", (question_id,)
        ).fetchone()
        _insert_question_revision(
            connection, question_id, 1, g.user["uuid"], "최초 등록",
            _question_snapshot(question),
        )
        if data["base_question_id"] is not None:
            connection.execute(
                "INSERT INTO question_links (question_id, related_question_id, relation_type, created_by) "
                "VALUES (?, ?, 'variant', ?)",
                (question_id, data["base_question_id"], g.user["uuid"]),
            )
        _delete_question_draft()
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return redirect(url_for("main", added=1, subject=data["subject"]))


def edit_question(question_id):
    question = _question_row(question_id)
    if question["deleted_at"] is not None:
        abort(404)
    connection = get_db()
    if request.method == "GET":
        begin_write_transaction(connection)
        question = _question_row(question_id)
        _ensure_initial_question_revision(connection, question)
        connection.commit()
        latest = connection.execute(
            "SELECT MAX(revision_number) FROM question_revisions WHERE question_id = ?",
            (question_id,),
        ).fetchone()[0]
        if request.args.get("discard_draft") == "1":
            _delete_question_draft(question_id)
            connection.commit()
        draft = _load_question_draft(question_id)
        conflict = bool(
            draft is not None
            and draft.get("draft_base_revision") is not None
            and draft["draft_base_revision"] != latest
        )
        values = draft if draft is not None else _question_form_values(question)
        form_base_revision = (
            draft.get("draft_base_revision") or latest
            if draft is not None else latest
        )
        return render_question_form(
            values, mode="edit", question=question, base_revision=form_base_revision,
            draft_saved=request.args.get("draft_saved") == "1",
            draft_updated_at=(draft or {}).get("draft_updated_at"),
            draft_conflict=conflict,
        )

    data, errors = _collect_question_data(request.form)
    if data["base_question_id"] == question_id:
        errors.append("현재 문항 자신을 변형문제 기준으로 지정할 수 없습니다.")
    try:
        base_revision = int(request.form.get("base_revision", ""))
    except (TypeError, ValueError):
        abort(400, description="수정 기준 버전이 올바르지 않습니다.")

    if request.form.get("form_action") == "draft":
        _save_question_draft(data, question_id, base_revision)
        return redirect(url_for("edit_question", question_id=question_id, draft_saved=1))

    if errors:
        return render_question_form(
            _form_values_from_data(data), errors, 400, mode="edit",
            question=question, base_revision=base_revision,
        )

    try:
        begin_write_transaction(connection)
        current = _question_row(question_id)
        _ensure_initial_question_revision(connection, current)
        latest = connection.execute(
            "SELECT MAX(revision_number) FROM question_revisions WHERE question_id = ?",
            (question_id,),
        ).fetchone()[0]
        if latest != base_revision:
            connection.rollback()
            errors.append(
                f"다른 사용자가 먼저 수정했습니다. 최신 버전은 v{latest}입니다. "
                "수정 이력을 확인한 뒤 최신 문서를 다시 열어 주세요."
            )
            return render_question_form(
                _form_values_from_data(data), errors, 409, mode="edit",
                question=current, base_revision=base_revision,
            )

        next_revision = latest + 1
        connection.execute(
            """
            UPDATE questions
            SET subject = ?, grade = ?, unit = ?, passage = ?, prompt = ?,
                examples = ?, choices = ?, answer = ?, explanation = ?,
                source = ?, year = ?, page = ?, difficulty = ?, question_type = ?,
                points = ?, course = ?, curriculum = ?, achievement_standard = ?,
                source_type = ?, exam = ?, original_question_number = ?,
                source_url = ?, license = ?, title = ?
            WHERE id = ?
            """,
            (
                data["subject"], data["grade"], data["unit"], data["passage"],
                data["prompt"], data["examples"],
                json.dumps(data["choices"], ensure_ascii=False),
                data["answer"], data["explanation"], data["source"],
                data["year"], data["page"], data["difficulty"],
                data["question_type"], data["points"], data["course"],
                data["curriculum"], data["achievement_standard"],
                data["source_type"], data["exam"], data["original_question_number"],
                data["source_url"], data["license"], data["title"], question_id,
            ),
        )
        snapshot = {field: data[field] for field in QUESTION_CONTENT_FIELDS}
        connection.execute(
            "DELETE FROM question_links WHERE question_id = ? AND relation_type = 'variant' "
            "AND related_question_id IS NOT NULL", (question_id,),
        )
        if data["base_question_id"] is not None:
            connection.execute(
                "INSERT INTO question_links (question_id, related_question_id, relation_type, created_by) "
                "VALUES (?, ?, 'variant', ?)",
                (question_id, data["base_question_id"], g.user["uuid"]),
            )
        _insert_question_revision(
            connection, question_id, next_revision, g.user["uuid"],
            data["summary"], snapshot,
        )
        _delete_question_draft(question_id)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return redirect(url_for("question_history", question_id=question_id, saved=1))

def question_history(question_id):
    question = _question_row(question_id)
    connection = get_db()
    _ensure_initial_question_revision(connection, question)
    connection.commit()
    revisions = connection.execute(
        """
        SELECT question_revisions.revision_number, question_revisions.summary,
               question_revisions.created_at, users.display_name AS editor_name
        FROM question_revisions
        LEFT JOIN users ON users.uuid = question_revisions.editor_uuid
        WHERE question_revisions.question_id = ?
        ORDER BY question_revisions.revision_number DESC
        """,
        (question_id,),
    ).fetchall()

    compare_from = request.args.get("from", type=int)
    compare_to = request.args.get("to", type=int)
    if compare_from is None or compare_to is None:
        if len(revisions) >= 2:
            compare_from = revisions[1]["revision_number"]
            compare_to = revisions[0]["revision_number"]
        else:
            compare_from = compare_to = revisions[0]["revision_number"]

    comparison = []
    if compare_from != compare_to:
        rows = connection.execute(
            """
            SELECT revision_number, snapshot_json
            FROM question_revisions
            WHERE question_id = ? AND revision_number IN (?, ?)
            """,
            (question_id, compare_from, compare_to),
        ).fetchall()
        snapshots = {
            row["revision_number"]: json.loads(row["snapshot_json"])
            for row in rows
        }
        if compare_from not in snapshots or compare_to not in snapshots:
            abort(404)
        for field in QUESTION_CONTENT_FIELDS:
            before = snapshots[compare_from].get(field)
            after = snapshots[compare_to].get(field)
            if field == "choices":
                before = "\n".join(before or [])
                after = "\n".join(after or [])
            if before != after:
                before_value = "" if before is None else str(before)
                after_value = "" if after is None else str(after)
                comparison.append({
                    "field": QUESTION_FIELD_LABELS[field],
                    # Only sanitizer-produced markup reaches the template's safe renderer.
                    "before_html": render_rich_html(before_value),
                    "after_html": render_rich_html(after_value),
                })

    return render_template(
        "question_history.html", nav_items=NAV_ITEMS, question=question,
        question_number=format_question_number(question["id"]),
        revisions=revisions, compare_from=compare_from, compare_to=compare_to,
        comparison=comparison, latest_revision=revisions[0]["revision_number"],
        saved=request.args.get("saved") == "1",
        restored=request.args.get("restored") == "1",
    )


def restore_question(question_id, revision_number):
    question = _question_row(question_id)
    connection = get_db()
    try:
        begin_write_transaction(connection)
        question = _question_row(question_id)
        _ensure_initial_question_revision(connection, question)
        target = connection.execute(
            """
            SELECT snapshot_json FROM question_revisions
            WHERE question_id = ? AND revision_number = ?
            """,
            (question_id, revision_number),
        ).fetchone()
        latest = connection.execute(
            "SELECT MAX(revision_number) FROM question_revisions WHERE question_id = ?",
            (question_id,),
        ).fetchone()[0]
        if target is None:
            connection.rollback()
            abort(404)
        snapshot = json.loads(target["snapshot_json"])
        defaults = {
            "title": "",
            "course": "",
            "curriculum": "2015 개정 교육과정",
            "achievement_standard": "",
            "difficulty": "중",
            "question_type": "단답형",
            "points": 4,
            "source_type": "기타",
            "exam": "",
            "original_question_number": "",
            "source_url": "",
            "license": "",
        }
        for field, default in defaults.items():
            snapshot.setdefault(field, default)
        next_revision = latest + 1
        connection.execute(
            """
            UPDATE questions
            SET subject = ?, grade = ?, unit = ?, passage = ?, prompt = ?,
                examples = ?, choices = ?, answer = ?, explanation = ?,
                source = ?, year = ?, page = ?, difficulty = ?, question_type = ?,
                points = ?, course = ?, curriculum = ?, achievement_standard = ?,
                source_type = ?, exam = ?, original_question_number = ?,
                source_url = ?, license = ?, title = ?
            WHERE id = ?
            """,
            (
                snapshot["subject"], snapshot["grade"], snapshot["unit"],
                snapshot["passage"], snapshot["prompt"], snapshot["examples"],
                json.dumps(snapshot["choices"], ensure_ascii=False),
                snapshot["answer"], snapshot["explanation"], snapshot["source"],
                snapshot["year"], snapshot["page"], snapshot.get("difficulty", "중"),
                snapshot.get("question_type", "단답형"), snapshot.get("points", 4), snapshot.get("course", ""),
                snapshot.get("curriculum", "2015 개정 교육과정"), snapshot.get("achievement_standard", ""),
                snapshot.get("source_type", "기타"), snapshot.get("exam", ""),
                snapshot.get("original_question_number", ""), snapshot.get("source_url", ""),
                snapshot.get("license", ""), snapshot.get("title", ""), question_id,
            ),
        )
        _insert_question_revision(
            connection, question_id, next_revision, g.user["uuid"],
            f"이전 버전 v{revision_number} 복원", snapshot,
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return redirect(url_for("question_history", question_id=question_id, restored=1))


def save_question_note(question_id):
    _question_row(question_id)
    note = request.form.get("personal_note", "").strip()
    if len(note) > 5000:
        abort(400, description="개인 메모는 5,000자 이내로 입력해 주세요.")
    get_db().execute(
        """
        INSERT INTO question_notes (user_uuid, question_id, note, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_uuid, question_id) DO UPDATE SET
            note = excluded.note,
            updated_at = CURRENT_TIMESTAMP
        """,
        (g.user["uuid"], question_id, note),
    )
    get_db().commit()
    return redirect(url_for("main", subject=request.form.get("subject", "수학")))


def move_question(question_id):
    question = get_db().execute(
        "SELECT id FROM questions WHERE id = ? AND user_uuid = ?",
        (question_id, g.user["uuid"]),
    ).fetchone()
    if question is None:
        abort(404)

    folder_uuid = request.form.get("folder_uuid", "").strip() or None
    if folder_uuid and get_db().execute(
        "SELECT 1 FROM folders WHERE uuid = ? AND user_uuid = ?",
        (folder_uuid, g.user["uuid"]),
    ).fetchone() is None:
        abort(400, description="선택한 폴더가 없습니다.")

    get_db().execute(
        "UPDATE questions SET folder_uuid = ? WHERE id = ? AND user_uuid = ?",
        (folder_uuid, question_id, g.user["uuid"]),
    )
    get_db().commit()
    return redirect(
        url_for(
            "main",
            subject=request.form.get("subject", "수학"),
            folder=request.form.get("current_folder") or None,
            folder_moved=1,
        )
    )

def hancom_to_latex():
    payload = request.get_json(silent=True)
    script = payload.get("script") if isinstance(payload, dict) else None
    try:
        latex = run_hmleq(script)
    except HmleqConversionError as exc:
        return jsonify(error=str(exc)), 422
    except HmleqUnavailable as exc:
        return jsonify(error=str(exc)), 503
    return jsonify(latex=latex)


def convert_hancom_math():
    payload = request.get_json(silent=True) or {}
    expression = str(payload.get("expression", "")).strip()
    if not expression:
        return jsonify(error="수식 코드를 입력해 주세요."), 400
    if len(expression) > 5000:
        return jsonify(error="수식 코드는 5,000자 이내로 입력해 주세요."), 400
    try:
        latex = run_hmleq(expression)
    except HmleqConversionError as error:
        return jsonify(error=f"한컴 수식을 변환하지 못했습니다: {error}"), 400
    except HmleqUnavailable as error:
        return jsonify(error=f"수식 변환기를 사용할 수 없습니다: {error}"), 503
    return jsonify(latex=latex)


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


def register_question_routes(app):
    app.add_url_rule(
        "/api/math/hancom-to-latex",
        endpoint="hancom_to_latex",
        view_func=login_required(hancom_to_latex),
        methods=["POST"],
    )
    app.add_url_rule(
        "/questions/math/convert-hancom",
        endpoint="convert_hancom_math",
        view_func=login_required(convert_hancom_math),
        methods=["POST"],
    )
    app.add_url_rule(
        "/curriculum/standards",
        endpoint="curriculum_standards",
        view_func=login_required(curriculum_standards),
        methods=["GET"],
    )
    app.add_url_rule(
        "/questions", endpoint="main", view_func=login_required(main), methods=["GET"]
    )
    app.add_url_rule(
        "/questions/code", endpoint="question_by_code",
        view_func=login_required(question_by_code), methods=["GET"],
    )
    app.add_url_rule(
        "/questions/<int:question_id>/delete", endpoint="delete_question",
        view_func=login_required(delete_question), methods=["POST"],
    )
    app.add_url_rule(
        "/questions/<int:question_id>/undelete", endpoint="restore_deleted_question",
        view_func=login_required(restore_deleted_question), methods=["POST"],
    )
    app.add_url_rule(
        "/admin/users",
        endpoint="admin_users",
        view_func=admin_required(admin_users),
        methods=["GET"],
    )
    app.add_url_rule(
        "/folders/new",
        endpoint="new_folder",
        view_func=login_required(new_folder),
        methods=["POST"],
    )
    app.add_url_rule(
        "/questions/new",
        endpoint="new_question",
        view_func=login_required(new_question),
        methods=["GET", "POST"],
    )
    app.add_url_rule(
        "/questions/<int:question_id>/notes",
        endpoint="save_question_note",
        view_func=login_required(save_question_note),
        methods=["POST"],
    )
    app.add_url_rule(
        "/questions/<int:question_id>/folder",
        endpoint="move_question",
        view_func=login_required(move_question),
        methods=["POST"],
    )
    app.add_url_rule(
        "/questions/<int:question_id>/edit",
        endpoint="edit_question",
        view_func=login_required(edit_question),
        methods=["GET", "POST"],
    )
    app.add_url_rule(
        "/questions/<int:question_id>/history",
        endpoint="question_history",
        view_func=login_required(question_history),
        methods=["GET"],
    )
    app.add_url_rule(
        "/questions/<int:question_id>/restore/<int:revision_number>",
        endpoint="restore_question",
        view_func=login_required(restore_question),
        methods=["POST"],
    )
