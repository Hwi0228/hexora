import json

from flask import abort, g, redirect, render_template, request, url_for

from constants import NAV_ITEMS
from question_constants import QUESTION_CONTENT_FIELDS, QUESTION_FIELD_LABELS
from question_ids import format_question_number
from rich_text import render_rich_html
from database import begin_write_transaction, get_db
from question_revisions import _ensure_initial_question_revision, _insert_question_revision
from question_repository import _question_row


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
