import sqlite3
import tempfile
import unittest
from pathlib import Path

from app import app


class LegalAndRightsReportTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.original_database = app.config["DATABASE"]
        self.original_testing = app.config.get("TESTING", False)
        app.config.update(
            TESTING=True,
            DATABASE=str(Path(self.temp_directory.name) / "legal.sqlite3"),
            SECRET_KEY="legal-test-secret",
        )
        self.client = app.test_client()

    def tearDown(self):
        app.config["DATABASE"] = self.original_database
        app.config["TESTING"] = self.original_testing
        self.temp_directory.cleanup()

    def csrf_token(self, client=None):
        target = client or self.client
        target.get("/report/request")
        with target.session_transaction() as session:
            return session["csrf_token"]

    def test_legal_pages_and_report_form_are_public(self):
        for path in ("/terms", "/privacy", "/report/request"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
        self.assertIn("이용약관".encode(), self.client.get("/terms").data)
        self.assertIn("개인정보처리방침".encode(), self.client.get("/privacy").data)

    def test_rights_report_is_validated_and_saved_for_admin_review(self):
        token = self.csrf_token()
        response = self.client.post(
            "/report/request",
            data={
                "_csrf_token": token,
                "category": "저작권·지식재산권 침해",
                "requested_action": "삭제 요청",
                "requester_role": "권리자 본인",
                "requester_name": "테스트 신청인",
                "requester_email": "reporter@example.com",
                "target_url": "https://hexora.kro.kr/questions",
                "details": "제가 권리를 보유한 콘텐츠가 허락 없이 게시되었습니다.",
                "truth_confirmed": "1",
                "privacy_agreed": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("submitted=1", response.headers["Location"])

        connection = sqlite3.connect(app.config["DATABASE"])
        try:
            row = connection.execute(
                "SELECT category, requester_email, target_url, status FROM rights_reports"
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(
            row,
            ("저작권·지식재산권 침해", "reporter@example.com", "https://hexora.kro.kr/questions", "접수"),
        )

    def test_invalid_target_url_is_rejected(self):
        token = self.csrf_token()
        response = self.client.post(
            "/report/request",
            data={
                "_csrf_token": token,
                "category": "기타 권리침해",
                "requested_action": "임시조치 검토 요청",
                "requester_role": "권리자의 대리인",
                "requester_name": "테스트 신청인",
                "requester_email": "reporter@example.com",
                "target_url": "javascript:alert(1)",
                "details": "권리 침해 사유를 설명합니다.",
                "truth_confirmed": "1",
                "privacy_agreed": "1",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("전체 URL".encode(), response.data)

    def test_admin_report_queue_requires_admin_and_can_update_status(self):
        anonymous = self.client.get("/admin/legal-reports")
        self.assertEqual(anonymous.status_code, 302)

        self.client.get("/signup")
        with self.client.session_transaction() as session:
            token = session["csrf_token"]
        signup = self.client.post(
            "/signup",
            data={
                "_csrf_token": token,
                "email": "legal-admin@example.com",
                "display_name": "법무 관리자",
                "password": "long-test-password",
                "password_confirm": "long-test-password",
                "terms_agreed": "1",
                "privacy_agreed": "1",
            },
        )
        self.assertEqual(signup.status_code, 302)

        report_token = self.csrf_token()
        self.client.post(
            "/report/request",
            data={
                "_csrf_token": report_token,
                "category": "명예훼손·사생활 침해",
                "requested_action": "임시조치 검토 요청",
                "requester_role": "권리자 본인",
                "requester_name": "신청인",
                "requester_email": "person@example.com",
                "target_url": "https://hexora.kro.kr/questions",
                "details": "권리 침해 사유 설명",
                "truth_confirmed": "1",
                "privacy_agreed": "1",
            },
        )
        queue = self.client.get("/admin/legal-reports")
        self.assertEqual(queue.status_code, 200)
        self.assertIn("권리침해 신고 관리".encode(), queue.data)

        with self.client.session_transaction() as session:
            token = session["csrf_token"]
        update = self.client.post(
            "/admin/legal-reports/1",
            data={"_csrf_token": token, "status": "검토 중"},
        )
        self.assertEqual(update.status_code, 302)
        connection = sqlite3.connect(app.config["DATABASE"])
        try:
            status = connection.execute(
                "SELECT status FROM rights_reports WHERE id = 1"
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(status, "검토 중")


if __name__ == "__main__":
    unittest.main()
