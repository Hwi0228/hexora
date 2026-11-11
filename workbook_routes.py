from flask import abort, g, redirect, render_template, request, url_for

from auth import login_required
from constants import NAV_ITEMS, SUBJECTS, GRADE_OPTIONS
from database import get_db
from question_constants import COURSE_OPTIONS, SUBJECT_COURSE_OPTIONS
from question_ids import format_question_number, parse_question_number as _parse_question_number


WORKBOOK_SUBJECTS = {
    course
    for course_list in SUBJECT_COURSE_OPTIONS.values()
    for course in course_list
}
WORKBOOK_GRADES = set(GRADE_OPTIONS)



def workbooks():
    connection = get_db()
    if request.method == "POST":
        kind = request.form.get("kind", "commercial").strip()
        title = request.form.get("title", "").strip()
        if kind not in {"commercial", "community"} or not title or len(title) > 200:
            abort(400, description="문제집 종류와 제목을 확인해 주세요.")
        try:
            publication_year = int(request.form.get("publication_year") or 0) or None
        except ValueError:
            abort(400, description="발행 연도를 숫자로 입력해 주세요.")
        if publication_year and not 1 <= publication_year <= 2200:
            abort(400, description="발행 연도는 1~2200 사이여야 합니다.")
        subject = request.form.get("subject", "").strip()
        grade = request.form.get("grade", "").strip()
        curriculum = request.form.get("curriculum", "").strip()
        if subject and subject not in WORKBOOK_SUBJECTS:
            abort(400, description="목록에서 과목을 선택해 주세요.")
        if grade and grade not in WORKBOOK_GRADES:
            abort(400, description="목록에서 대상 학년을 선택해 주세요.")
        if curriculum and curriculum not in COURSE_OPTIONS:
            abort(400, description="목록에서 교육과정을 선택해 주세요.")

        cursor = connection.execute(
            """
            INSERT INTO workbooks (
                kind, title, publisher, authors, isbn, edition, publication_year,
                subject, grade, curriculum, description, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id
            """,
            (
                kind, title, request.form.get("publisher", "").strip()[:200],
                request.form.get("authors", "").strip()[:300],
                request.form.get("isbn", "").strip()[:20],
                request.form.get("edition", "").strip()[:100], publication_year,
                subject[:80], grade[:80], curriculum[:100],
                request.form.get("description", "").strip()[:2000], g.user["uuid"],
            ),
        )
        workbook_id = cursor.fetchone()["id"]
        connection.commit()
        return redirect(url_for("workbook_detail", workbook_id=workbook_id))

    search = request.args.get("q", "").strip()[:100]
    kind = request.args.get("kind", "all")
    query = """
        SELECT workbooks.*, users.display_name AS creator_name,
               COALESCE(entry_counts.entry_count, 0) AS entry_count
        FROM workbooks LEFT JOIN users ON users.uuid = workbooks.created_by
        LEFT JOIN (
            SELECT workbook_id, COUNT(*) AS entry_count
            FROM workbook_entries GROUP BY workbook_id
        ) AS entry_counts ON entry_counts.workbook_id = workbooks.id
        WHERE 1 = 1
    """
    parameters = []
    if kind in {"commercial", "community"}:
        query += " AND workbooks.kind = ?"
        parameters.append(kind)
    if search:
        query += " AND (workbooks.title LIKE ? OR workbooks.publisher LIKE ? OR workbooks.authors LIKE ? OR workbooks.isbn LIKE ?)"
        pattern = f"%{search}%"
        parameters.extend([pattern] * 4)
    query += " ORDER BY LOWER(workbooks.title), workbooks.id DESC"
    rows = connection.execute(query, parameters).fetchall()
    return render_template(
        "workbooks.html", workbooks=rows, search=search, selected_kind=kind,
        subjects=SUBJECTS, subject_course_options=SUBJECT_COURSE_OPTIONS,
        grade_options=GRADE_OPTIONS,
        curriculum_options=list(COURSE_OPTIONS),
        nav_items=NAV_ITEMS, active_page="workbooks",
    )


def workbook_detail(workbook_id):
    connection = get_db()
    workbook = connection.execute(
        "SELECT workbooks.*, users.display_name AS creator_name FROM workbooks "
        "LEFT JOIN users ON users.uuid = workbooks.created_by WHERE workbooks.id = ?",
        (workbook_id,),
    ).fetchone()
    if workbook is None:
        abort(404)

    if request.method == "POST":
        if workbook["kind"] != "community":
            abort(400, description="시중 문제집에는 HEXORA 문항을 수록할 수 없습니다.")
        question_id = _parse_question_number(request.form.get("question_number"))
        if question_id is None or connection.execute(
            "SELECT id FROM questions WHERE id = ?", (question_id,)
        ).fetchone() is None:
            abort(400, description="HEXORA 문항 번호를 확인해 주세요.")
        question = connection.execute(
            "SELECT unit FROM questions WHERE id = ?", (question_id,)
        ).fetchone()
        try:
            connection.execute(
                """INSERT INTO workbook_entries
                   (workbook_id, question_id, unit, created_by)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(workbook_id, question_id) WHERE question_id IS NOT NULL DO NOTHING""",
                (workbook_id, question_id, question["unit"], g.user["uuid"]),
            )
            connection.commit()
        except Exception as error:
            connection.rollback()
            if "UNIQUE" not in str(error).upper() and "DUPLICATE" not in str(error).upper():
                raise
        return redirect(url_for("workbook_detail", workbook_id=workbook_id))

    if workbook["kind"] == "community":
        entries = [dict(row) for row in connection.execute(
            """SELECT workbook_entries.*, questions.title, questions.subject,
                      questions.grade, questions.unit
               FROM workbook_entries JOIN questions ON questions.id = workbook_entries.question_id
               WHERE workbook_entries.workbook_id = ? ORDER BY workbook_entries.id""",
            (workbook_id,),
        ).fetchall()]
        for entry in entries:
            entry["display_id"] = format_question_number(entry["question_id"])
    else:
        entries = connection.execute(
            """SELECT workbook_entries.*, COUNT(question_links.id) AS variant_count
               FROM workbook_entries LEFT JOIN question_links
               ON question_links.workbook_entry_id = workbook_entries.id
              AND question_links.relation_type = 'variant'
               WHERE workbook_entries.workbook_id = ?
               GROUP BY workbook_entries.id ORDER BY workbook_entries.unit,
                        workbook_entries.page, workbook_entries.question_number""",
            (workbook_id,),
        ).fetchall()
    return render_template(
        "workbook_detail.html", workbook=workbook, entries=entries,
        nav_items=NAV_ITEMS, active_page="workbooks",
    )


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


def register_workbook_routes(app):
    app.add_url_rule(
        "/workbooks", endpoint="workbooks", view_func=login_required(workbooks),
        methods=["GET", "POST"],
    )
    app.add_url_rule(
        "/workbooks/<int:workbook_id>", endpoint="workbook_detail",
        view_func=login_required(workbook_detail), methods=["GET", "POST"],
    )
    app.add_url_rule(
        "/questions/<int:question_id>/links", endpoint="question_links",
        view_func=login_required(question_links), methods=["GET", "POST"],
    )
