"""Routes for exporting selected questions as HWPX exam sheets."""

import io
import re

from flask import abort, request, send_file

from auth import login_required
from database import get_db
from hwpx_export import build_exam_hwpx


def export_exam_hwpx():
    selected_values = request.form.getlist("question_ids")
    selected_ids = []
    seen = set()
    for value in selected_values:
        try:
            question_id = int(value)
        except (TypeError, ValueError):
            abort(400, description="선택한 문항 번호가 올바르지 않습니다.")
        if question_id < 1:
            abort(400, description="선택한 문항 번호가 올바르지 않습니다.")
        if question_id not in seen:
            selected_ids.append(question_id)
            seen.add(question_id)

    if not selected_ids:
        abort(400, description="시험지에 넣을 문항을 하나 이상 선택해 주세요.")
    if len(selected_ids) > 100:
        abort(400, description="시험지에는 최대 100문항까지 넣을 수 있습니다.")

    placeholders = ", ".join("?" for _ in selected_ids)
    rows = get_db().execute(
        f"""
        SELECT id, subject, grade, title, passage, prompt, examples, choices,
               answer, explanation, points
        FROM questions
        WHERE id IN ({placeholders}) AND deleted_at IS NULL
        """,
        selected_ids,
    ).fetchall()
    questions_by_id = {int(row["id"]): dict(row) for row in rows}
    if len(questions_by_id) != len(selected_ids):
        abort(404, description="선택한 문항 중 삭제되었거나 존재하지 않는 문항이 있습니다.")

    # 공개 문제 은행이므로 작성자와 관계없이 로그인 회원이 선택한 문항을 내보낼 수 있습니다.
    questions = [questions_by_id[question_id] for question_id in selected_ids]
    title = request.form.get("exam_title", "").strip() or "HEXORA 시험지"
    if len(title) > 100:
        abort(400, description="시험지 제목은 100자 이내로 입력해 주세요.")

    include_answers = request.form.get("include_answers") == "1"
    hwpx_bytes = build_exam_hwpx(
        questions,
        title=title,
        include_answers=include_answers,
    )
    filename = re.sub(r"[^\w가-힣 .()-]", "", title, flags=re.UNICODE).strip(" .")
    filename = (filename or "HEXORA_시험지")[:80]

    return send_file(
        io.BytesIO(hwpx_bytes),
        mimetype="application/hwp+zip",
        as_attachment=True,
        download_name=f"{filename}.hwpx",
        max_age=0,
    )


def register_exam_export_routes(app):
    app.add_url_rule(
        "/exams/export",
        endpoint="export_exam_hwpx",
        view_func=login_required(export_exam_hwpx),
        methods=["POST"],
    )
