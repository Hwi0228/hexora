"""Routes for linking questions to related questions and workbooks."""

from flask import abort, g, redirect, render_template, request, url_for

from auth import login_required
from constants import NAV_ITEMS
from database import get_db
from question_ids import format_question_number, parse_question_number as _parse_question_number


def question_links(question_id):
    connection = get_db()
    question = connection.execute(
        "SELECT * FROM questions WHERE id = ?", (question_id,)
    ).fetchone()
    if question is None:
        abort(404)

    if request.method == "POST":
        relation_type = request.form.get("relation_type", "variant").strip()
        if relation_type not in {"variant", "similar"}:
            abort(400, description="문항 관계 유형을 확인해 주세요.")
        if request.form.get("target_kind") == "question":
            base_id = _parse_question_number(request.form.get("base_question_number"))
            if base_id is None or base_id == question_id or connection.execute(
                "SELECT id FROM questions WHERE id = ?", (base_id,)
            ).fetchone() is None:
                abort(400, description="기준 문항 번호를 확인해 주세요.")
            duplicate = connection.execute(
                """SELECT id FROM question_links WHERE question_id = ?
                   AND related_question_id = ? AND relation_type = ?""",
                (question_id, base_id, relation_type),
            ).fetchone()
            if duplicate is None:
                connection.execute(
                    """INSERT INTO question_links
                       (question_id, related_question_id, relation_type, created_by)
                       VALUES (?, ?, ?, ?)""",
                    (question_id, base_id, relation_type, g.user["uuid"]),
                )
        elif request.form.get("target_kind") == "workbook":
            try:
                workbook_id = int(request.form.get("workbook_id", ""))
                page = int(request.form.get("page") or 0) or None
            except ValueError:
                abort(400, description="문제집 또는 페이지를 확인해 주세요.")
            workbook = connection.execute(
                "SELECT id FROM workbooks WHERE id = ? AND kind = 'commercial'",
                (workbook_id,),
            ).fetchone()
            unit = request.form.get("unit", "").strip()[:120]
            source_number = request.form.get("source_question_number", "").strip()[:50]
            if workbook is None or not (page or source_number) or (page and page < 1):
                abort(400, description="시중 문제집과 문항 위치(페이지 또는 번호)를 입력해 주세요.")
            page_clause = "page IS NULL" if page is None else "page = ?"
            lookup_parameters = [workbook_id, unit]
            if page is not None:
                lookup_parameters.append(page)
            lookup_parameters.append(source_number)
            entry = connection.execute(
                f"""SELECT id FROM workbook_entries WHERE workbook_id = ?
                    AND question_id IS NULL AND unit = ? AND {page_clause}
                    AND question_number = ?""",
                lookup_parameters,
            ).fetchone()
            if entry is None:
                cursor = connection.execute(
                    """INSERT INTO workbook_entries
                       (workbook_id, unit, page, question_number, created_by)
                       VALUES (?, ?, ?, ?, ?) RETURNING id""",
                    (workbook_id, unit, page, source_number, g.user["uuid"]),
                )
                entry_id = cursor.fetchone()["id"]
            else:
                entry_id = entry["id"]
            duplicate = connection.execute(
                """SELECT id FROM question_links WHERE question_id = ?
                   AND workbook_entry_id = ? AND relation_type = ?""",
                (question_id, entry_id, relation_type),
            ).fetchone()
            if duplicate is None:
                connection.execute(
                    """INSERT INTO question_links
                       (question_id, workbook_entry_id, relation_type, created_by)
                       VALUES (?, ?, ?, ?)""",
                    (question_id, entry_id, relation_type, g.user["uuid"]),
                )
        else:
            abort(400, description="연결할 대상 유형을 선택해 주세요.")
        connection.commit()
        return redirect(url_for("question_links", question_id=question_id))

    related = connection.execute(
        """SELECT question_links.*, workbooks.id AS book_id,
                  related.id AS related_id, related.title AS related_title,
                  related.subject AS related_subject, related.prompt AS related_prompt,
                  workbooks.title AS workbook_title, workbooks.publisher,
                  workbook_entries.unit AS source_unit, workbook_entries.page AS source_page,
                  workbook_entries.question_number AS source_number
           FROM question_links
           LEFT JOIN questions AS related ON related.id = question_links.related_question_id
           LEFT JOIN workbook_entries ON workbook_entries.id = question_links.workbook_entry_id
           LEFT JOIN workbooks ON workbooks.id = workbook_entries.workbook_id
           WHERE question_links.question_id = ? ORDER BY question_links.id DESC""",
        (question_id,),
    ).fetchall()
    bases = connection.execute(
        """SELECT question_links.relation_type, questions.id, questions.title,
                  questions.subject FROM question_links
           JOIN questions ON questions.id = question_links.question_id
           WHERE question_links.related_question_id = ? ORDER BY question_links.id DESC""",
        (question_id,),
    ).fetchall()
    books = connection.execute(
        "SELECT id, title, publisher, edition FROM workbooks "
        "WHERE kind = 'commercial' ORDER BY LOWER(title)"
    ).fetchall()
    return render_template(
        "question_links.html", question=question, question_number=format_question_number(question_id),
        related=related, bases=bases, books=books, nav_items=NAV_ITEMS,
        active_page="main", format_question_number=format_question_number,
    )


def register_question_link_routes(app):
    app.add_url_rule(
        "/questions/<int:question_id>/links",
        endpoint="question_links",
        view_func=login_required(question_links),
        methods=["GET", "POST"],
    )
