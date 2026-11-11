from flask import abort, g, redirect, render_template, request, url_for

from auth import login_required
from constants import NAV_ITEMS, SUBJECTS, GRADE_OPTIONS
from database import get_db
from question_constants import COURSE_OPTIONS, SUBJECT_COURSE_OPTIONS
from question_ids import format_question_number, parse_question_number as _parse_question_number
from question_link_routes import question_links, register_question_link_routes


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


def register_workbook_routes(app):
    app.add_url_rule(
        "/workbooks", endpoint="workbooks", view_func=login_required(workbooks),
        methods=["GET", "POST"],
    )
    app.add_url_rule(
        "/workbooks/<int:workbook_id>", endpoint="workbook_detail",
        view_func=login_required(workbook_detail), methods=["GET", "POST"],
    )
    register_question_link_routes(app)
