import os
import tempfile
import unittest
import uuid
from pathlib import Path
from urllib.parse import urlencode
from unittest.mock import patch

from app import create_app
from database import close_db, get_db


class QuestionSearchBackendParityTests(unittest.TestCase):
    def _exercise_backend(self, backend, database_url=None):
        with tempfile.TemporaryDirectory() as directory:
            environment = {
                "DATABASE_TYPE": backend,
                "FLASK_SECRET_KEY": "question-search-parity-test-secret",
            }
            if backend == "sqlite":
                environment["DATABASE_PATH"] = str(Path(directory) / "search.sqlite3")
            else:
                environment["DATABASE_URL"] = database_url

            with patch.dict(os.environ, environment, clear=False):
                application = create_app()
            application.config.update(
                TESTING=True,
                SECRET_KEY="question-search-parity-test-secret",
            )
            if backend == "sqlite":
                application.config["DATABASE"] = environment["DATABASE_PATH"]
            else:
                application.config.update(
                    DATABASE_TYPE="postgresql",
                    DATABASE_URL=database_url,
                )

            client = application.test_client()
            email = f"search-{uuid.uuid4().hex}@example.test"
            try:
                signup_page = client.get("/signup")
                self.assertEqual(signup_page.status_code, 200)
                with client.session_transaction() as session:
                    csrf_token = session["csrf_token"]
                signup = client.post(
                    "/signup",
                    data={
                        "_csrf_token": csrf_token,
                        "email": email,
                        "display_name": "Search test",
                        "password": "long-search-test-password",
                        "password_confirm": "long-search-test-password",
                        "terms_agreed": "1",
                        "privacy_agreed": "1",
                    },
                )
                self.assertEqual(signup.status_code, 302)

                client.get("/questions/new")
                with client.session_transaction() as session:
                    csrf_token = session["csrf_token"]

                def create_question(title, **overrides):
                    form = {
                        "_csrf_token": csrf_token,
                        "title": title,
                        "subject": "수학",
                        "grade": "고2",
                        "course": "수학Ⅱ",
                        "curriculum": "2015 개정 교육과정",
                        "achievement_standard": "[12수학Ⅱ02-01] 미분계수의 뜻을 알고, 그 값을 구할 수 있다.",
                        "unit": "미분",
                        "difficulty": "중",
                        "question_type": "단답형",
                        "license": "ORIGINAL",
                        "source_type": "학교 시험",
                        "prompt": "<p>미분계수와 도함수</p>",
                        "choices": "첫 번째\n두 번째",
                        "answer": "2",
                        "explanation": "도함수의 정의를 이용한다.",
                        "source": "학교 시험",
                        "year": "2024",
                        "page": "2",
                    }
                    form.update(overrides)
                    response = client.post("/questions/new", data=form)
                    self.assertEqual(response.status_code, 302)

                create_question("미분 기본 문항")
                create_question(
                    "다항식 응용 문항",
                    grade="고1",
                    course="대수",
                    curriculum="2022 개정 교육과정",
                    source_type="수능 및 모의평가",
                    year="2025",
                    achievement_standard="[10수학01-01] 다항식의 연산을 할 수 있다.",
                    prompt="<p>다항식의 연산</p>",
                    license="CC-BY-4.0",
                )

                with application.app_context():
                    stored = get_db().execute(
                        """
                        SELECT curriculum, course, grade, source_type, year,
                               license, achievement_standard
                        FROM questions WHERE title = ?
                        """,
                        ("미분 기본 문항",),
                    ).fetchone()
                    self.assertIsNotNone(stored)
                    self.assertEqual(stored["curriculum"], "2015 개정 교육과정")
                    self.assertEqual(stored["course"], "수학Ⅱ")
                    self.assertEqual(stored["grade"], "고2")
                    self.assertEqual(stored["source_type"], "학교 시험")
                    self.assertEqual(int(stored["year"]), 2024)
                    self.assertEqual(stored["license"], "ORIGINAL")
                    self.assertIn("12수학Ⅱ02-01", stored["achievement_standard"])

                individual_filters = {
                    "q": "미분",
                    "curriculum": "2015 개정 교육과정",
                    "course": "수학Ⅱ",
                    "grade": "고2",
                    "source_type": "학교 시험",
                    "year": "2024",
                    "license": "ORIGINAL",
                    "achievement_standard": "12수학Ⅱ02-01",
                }
                for key, value in individual_filters.items():
                    response = client.get(
                        "/questions?" + urlencode({"subject": "수학", key: value})
                    )
                    self.assertIn(
                        "검색 결과 1개".encode(),
                        response.data,
                        msg=f"single filter failed: {key}={value}",
                    )

                query = urlencode({
                    "subject": "수학",
                    "q": "미분",
                    "curriculum": "2015 개정 교육과정",
                    "course": "수학Ⅱ",
                    "grade": "고2",
                    "source_type": "학교 시험",
                    "year": "2024",
                    "license": "ORIGINAL",
                    "achievement_standard": "12수학Ⅱ02-01",
                    "sort": "relevance",
                })
                all_questions = client.get("/questions?subject=수학")
                self.assertEqual(all_questions.status_code, 200)
                self.assertIn("미분계수와 도함수".encode(), all_questions.data)

                filtered = client.get("/questions?" + query)
                self.assertEqual(filtered.status_code, 200)
                self.assertIn("검색 결과 1개".encode(), filtered.data)
                self.assertIn("미분계수와 도함수".encode(), filtered.data)
                self.assertNotIn("다항식의 연산".encode(), filtered.data)
                self.assertIn('name="q" maxlength="120" value="미분"'.encode(), filtered.data)

                no_results = client.get("/questions?" + urlencode({
                    "subject": "수학",
                    "q": "존재하지않는문항검색어",
                }))
                self.assertEqual(no_results.status_code, 200)
                self.assertIn("조건에 맞는 문항이 없습니다.".encode(), no_results.data)

                for sort in ("latest", "modified", "relevance"):
                    sorted_response = client.get(
                        "/questions?" + urlencode({"subject": "수학", "q": "미분", "sort": sort})
                    )
                    self.assertEqual(sorted_response.status_code, 200)
                    self.assertIn(f'<option value="{sort}" selected>'.encode(), sorted_response.data)
            finally:
                with application.app_context():
                    try:
                        connection = get_db()
                        connection.execute("DELETE FROM users WHERE email = ?", (email,))
                        connection.commit()
                    finally:
                        close_db()

    def test_same_filters_and_sort_modes_on_sqlite_and_postgresql(self):
        self._exercise_backend("sqlite")
        postgres_url = os.environ.get("HEXORA_TEST_POSTGRES_URL", "").strip()
        if not postgres_url:
            self.skipTest("HEXORA_TEST_POSTGRES_URL is not configured")
        self._exercise_backend("postgresql", postgres_url)


if __name__ == "__main__":
    unittest.main()
