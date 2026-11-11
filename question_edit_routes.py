import json

from flask import abort, g, redirect, render_template, request, url_for

from constants import NAV_ITEMS, SUBJECTS, LICENSE_CHOICES, SOURCE_TYPES
from question_constants import QUESTION_CONTENT_FIELDS, QUESTION_TYPES, DIFFICULTIES, COURSE_OPTIONS, SUBJECT_COURSE_OPTIONS
from question_ids import format_question_number
from database import begin_write_transaction, get_db
from question_drafts import _delete_question_draft, _load_question_draft, _save_question_draft
from question_revisions import _ensure_initial_question_revision, _insert_question_revision, _question_snapshot
from question_repository import _question_form_values, _question_row
from question_validation import _collect_question_data, _form_values_from_data
from folder_service import get_folder_data


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
