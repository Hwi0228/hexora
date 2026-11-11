"""Public legal pages and rights-report intake for HEXORA."""

from urllib.parse import urlsplit

from flask import abort, redirect, render_template, request, url_for

from auth import admin_required
from database import get_db


REPORT_CATEGORIES = {
    "명예훼손·사생활 침해",
    "저작권·지식재산권 침해",
    "개인정보 노출",
    "기타 권리침해",
}
REPORT_ACTIONS = {"삭제 요청", "임시조치 검토 요청", "반박 내용 게재 요청"}
REPORTER_ROLES = {"권리자 본인", "권리자의 대리인"}


def _valid_http_url(value):
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
        and not parsed.username
        and not parsed.password
    )


def register_legal_routes(app):
    @app.get("/terms")
    def terms():
        return render_template("legal_page.html", page="terms")

    @app.get("/privacy")
    def privacy():
        return render_template("legal_page.html", page="privacy")

    @app.route("/report/request", methods=["GET", "POST"])
    def report_request():
        form_data = {
            key: request.form.get(key, "").strip()
            for key in (
                "category", "requested_action", "requester_role",
                "requester_name", "requester_email", "target_url", "details",
            )
        }
        errors = []

        if request.method == "POST":
            # Ignore automated submissions that fill the hidden honeypot field.
            if request.form.get("website", "").strip():
                return redirect(url_for("report_request", submitted="1"))

            if form_data["category"] not in REPORT_CATEGORIES:
                errors.append("신고 유형을 선택해 주세요.")
            if form_data["requested_action"] not in REPORT_ACTIONS:
                errors.append("요청 내용을 선택해 주세요.")
            if form_data["requester_role"] not in REPORTER_ROLES:
                errors.append("신청인과 권리자의 관계를 선택해 주세요.")
            if not form_data["requester_name"] or len(form_data["requester_name"]) > 80:
                errors.append("신청인 이름을 1~80자로 입력해 주세요.")
            email = form_data["requester_email"]
            if len(email) > 254 or "@" not in email or "." not in email.rsplit("@", 1)[-1]:
                errors.append("회신받을 이메일 주소를 확인해 주세요.")
            if len(form_data["target_url"]) > 2048 or not _valid_http_url(form_data["target_url"]):
                errors.append("문제가 되는 콘텐츠의 전체 URL을 http 또는 https 형식으로 입력해 주세요.")
            if not form_data["details"] or len(form_data["details"]) > 10000:
                errors.append("권리 침해 내용과 사유를 1~10,000자로 구체적으로 작성해 주세요.")
            if request.form.get("truth_confirmed") != "1":
                errors.append("신청 내용이 사실임을 확인해 주세요.")
            if request.form.get("privacy_agreed") != "1":
                errors.append("신고 처리 목적의 개인정보 수집·이용에 동의해 주세요.")

            if not errors:
                connection = get_db()
                connection.execute(
                    """
                    INSERT INTO rights_reports (
                        category, requested_action, requester_role,
                        requester_name, requester_email, target_url, details
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        form_data["category"], form_data["requested_action"],
                        form_data["requester_role"], form_data["requester_name"],
                        email, form_data["target_url"], form_data["details"],
                    ),
                )
                connection.commit()
                return redirect(url_for("report_request", submitted="1"))

        return render_template(
            "report_request.html",
            form_data=form_data,
            errors=errors,
            submitted=request.args.get("submitted") == "1",
            categories=sorted(REPORT_CATEGORIES),
            actions=sorted(REPORT_ACTIONS),
            reporter_roles=sorted(REPORTER_ROLES),
        ), (400 if errors else 200)

    @app.get("/admin/legal-reports")
    @admin_required
    def admin_legal_reports():
        reports = get_db().execute(
            """
            SELECT id, category, requested_action, requester_role,
                   requester_name, requester_email, target_url, details,
                   status, created_at
            FROM rights_reports
            ORDER BY created_at DESC, id DESC
            LIMIT 200
            """
        ).fetchall()
        return render_template("admin_legal_reports.html", reports=reports)

    @app.post("/admin/legal-reports/<int:report_id>")
    @admin_required
    def update_legal_report(report_id):
        status = request.form.get("status", "")
        if status not in {"접수", "검토 중", "처리 완료", "조치 불가"}:
            abort(400, description="올바르지 않은 처리 상태입니다.")
        connection = get_db()
        cursor = connection.execute(
            "UPDATE rights_reports SET status = ? WHERE id = ?",
            (status, report_id),
        )
        if cursor.rowcount == 0:
            abort(404)
        connection.commit()
        return redirect(url_for("admin_legal_reports"))
