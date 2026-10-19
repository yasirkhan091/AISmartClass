import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
TEMP_DB = tempfile.TemporaryDirectory()
os.environ["SMARTCLASS_DB"] = str(Path(TEMP_DB.name) / "school-api.db")
for variable in (
    "DATABASE_URL",
    "APP_ENV",
    "DEMO_STUDENT_USERNAME",
    "DEMO_STUDENT_PASSWORD",
    "DEMO_TEACHER_USERNAME",
    "DEMO_TEACHER_PASSWORD",
    "ADMIN_USERNAME",
    "ADMIN_PASSWORD",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "OPEN_ROUTER_API_KEY",
    "OPEN_ROUTER_MODEL",
    "AI_PROVIDER",
):
    os.environ.pop(variable, None)

import main


class SchoolApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with main.closing(main.connect()) as db:
            salt = "school-api-test-salt"
            db.execute("INSERT INTO users(id,name,email,role,username,password_salt,password_hash,is_admin,is_active) VALUES(?,?,?,?,?,?,?,?,1)", ("admin-test", "Test Administrator", None, "teacher", "admin-test", salt, main.password_digest("test-admin-password", salt), 1))
            db.commit()

    def setUp(self):
        self.user = {"id": "teacher01", "name": "Teacher One", "username": "teacher01", "role": "teacher", "is_admin": 0}
        main.app.dependency_overrides[main.authenticated_user] = lambda: self.user
        self.client = TestClient(main.app)

    def tearDown(self):
        self.client.close()
        main.app.dependency_overrides.clear()

    def test_postgres_executemany_wraps_cursor_returned_as_none(self):
        class FakeCursor:
            rowcount = 2

            def executemany(self, query, parameters):
                self.query = query
                self.parameters = parameters

        class FakeConnection:
            def __init__(self):
                self.fake_cursor = FakeCursor()

            def cursor(self):
                return self.fake_cursor

        connection = FakeConnection()
        cursor = main.PostgresConnection(connection).executemany(
            "INSERT INTO records(value) VALUES(?)",
            [(1,), (2,)],
        )

        self.assertEqual(cursor.rowcount, 2)
        self.assertEqual(connection.fake_cursor.query, "INSERT INTO records(value) VALUES(%s)")

    def test_postgres_adapter_escapes_literal_like_percent(self):
        class FakeCursor:
            rowcount = 1

            def execute(self, query, parameters):
                self.query = query
                self.parameters = parameters
                return self

        class FakeConnection:
            def __init__(self):
                self.fake_cursor = FakeCursor()

            def execute(self, query, parameters):
                return self.fake_cursor.execute(query, parameters)

        connection = FakeConnection()
        main.PostgresConnection(connection).execute(
            "SELECT id FROM tests WHERE id LIKE 'test-class9-%' AND subject=?",
            ("Physics",),
        )

        self.assertEqual(connection.fake_cursor.query, "SELECT id FROM tests WHERE id LIKE 'test-class9-%%' AND subject=%s")
        self.assertEqual(connection.fake_cursor.parameters, ("Physics",))

    def _create_test(self, is_mock=False):
        response = self.client.post("/api/tests", json={
            "class_id": "class9-b",
            "title": "Digital Algebra Check",
            "subject": "Mathematics",
            "kind": "Assessment",
            "due_date": "2026-10-19",
            "is_mock": is_mock,
        })
        self.assertEqual(response.status_code, 200, response.text)
        test_id = response.json()["id"]
        questions = [
            {"prompt": "Choose 2 + 2", "points": 2.5, "question_type": "mcq", "options": ["3", "4", "5"], "answer_key": 1},
            {"prompt": "Explain your method", "points": 2.5, "question_type": "subjective", "answer_key": "The answer is four because two plus two is four."},
        ]
        question_ids = []
        for question in questions:
            created = self.client.post(f"/api/tests/{test_id}/questions", json=question)
            self.assertEqual(created.status_code, 200, created.text)
            question_ids.append(created.json()["id"])
        published = self.client.post(f"/api/tests/{test_id}/publish")
        self.assertEqual(published.status_code, 200, published.text)
        return test_id, question_ids

    def _fake_analysis(self):
        with main.closing(main.connect()) as db:
            metrics = [dict(row) for row in db.execute("SELECT id FROM teacher_metrics WHERE class_id=? AND subject=? AND retired_at IS NULL", ("class9-b", "Mathematics"))]
        return {
            "subjective_score": 2,
            "test_rating": 9,
            "analysis": "Strong understanding.",
            "strengths": ["Accuracy"],
            "focus_areas": ["Explain the method"],
            "advice": "Keep showing your steps.",
            "subject_rating": 8,
            "metric_ratings": [{"metric_id": item["id"], "rating": 8, "evidence": "Clear response."} for item in metrics],
            "overall_rating": 7.5,
            "overall_analysis": "Steady improvement.",
        }

    def test_openrouter_prompt_and_json_response_contract(self):
        with main.closing(main.connect()) as db:
            metrics = [dict(row) for row in db.execute("SELECT id FROM teacher_metrics WHERE class_id=? AND subject=? AND retired_at IS NULL", ("class9-b", "Mathematics"))]
        result = self._fake_analysis()
        result["subjective_score"] = 2
        fake_payload = {"choices": [{"message": {"role": "assistant", "content": json.dumps(result)}}]}

        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return json.dumps(fake_payload).encode()

        with patch.dict(os.environ, {"AI_PROVIDER": "openrouter", "OPEN_ROUTER_API_KEY": "unit-test-key", "OPEN_ROUTER_MODEL": "openrouter/free"}):
            with patch("main.urllib.request.urlopen", return_value=FakeResponse()) as request:
                parsed = main.get_structured_test_analysis('{"sample":true}', 5, metrics)
        request_object = request.call_args.args[0]
        body = json.loads(request_object.data)
        self.assertEqual(request_object.full_url, "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(request_object.get_header("Authorization"), "Bearer unit-test-key")
        self.assertEqual(body["model"], "openrouter/free")
        self.assertEqual(body["response_format"]["type"], "json_object")
        self.assertIn("json", body["messages"][1]["content"])
        self.assertIn("required_output", body["messages"][1]["content"])
        self.assertEqual(parsed["subjective_score"], 2)
        self.assertEqual(len(parsed["metric_ratings"]), len(metrics))

    def test_openrouter_content_parser_accepts_model_response_shapes(self):
        expected = {"analysis": "Clear work."}
        encoded = json.dumps(expected)
        self.assertEqual(main.parse_openrouter_analysis_content({"content": expected}), expected)
        self.assertEqual(main.parse_openrouter_analysis_content({"content": {"type": "text", "text": encoded}}), expected)
        self.assertEqual(main.parse_openrouter_analysis_content({"content": [{"type": "text", "text": encoded}]}), expected)
        self.assertEqual(main.parse_openrouter_analysis_content({"content": f"```json\n{encoded}\n```"}), expected)

    def test_openrouter_invalid_output_and_transport_failures_are_retryable(self):
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return b'{"choices":[{"message":{"content":"not valid analysis"}}]}'

        with patch.dict(os.environ, {"AI_PROVIDER": "openrouter", "OPEN_ROUTER_API_KEY": "unit-test-key"}):
            with patch("main.urllib.request.urlopen", return_value=FakeResponse()):
                with self.assertRaises(main.HTTPException) as invalid:
                    main.get_structured_test_analysis("{}", 5, [])
            self.assertEqual(invalid.exception.status_code, 502)

            with patch("main.urllib.request.urlopen", side_effect=main.urllib.error.URLError("offline")):
                with self.assertRaises(main.HTTPException) as unavailable:
                    main.get_structured_test_analysis("{}", 5, [])
            self.assertEqual(unavailable.exception.status_code, 503)

    def test_openrouter_uses_fallback_model_after_invalid_primary_response(self):
        class FakeResponse:
            def __init__(self, content):
                self.content = content

            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return json.dumps({"choices": [{"message": {"content": self.content}}]}).encode()

        with main.closing(main.connect()) as db:
            metrics = [dict(row) for row in db.execute("SELECT id FROM teacher_metrics WHERE class_id=? AND subject=? AND retired_at IS NULL", ("class9-b", "Mathematics"))]
        valid = self._fake_analysis()
        valid["subjective_score"] = 2
        responses = [FakeResponse("not json"), FakeResponse(json.dumps(valid))]
        with patch.dict(os.environ, {"AI_PROVIDER": "openrouter", "OPEN_ROUTER_API_KEY": "unit-test-key", "OPEN_ROUTER_MODEL": "primary-model", "OPEN_ROUTER_FALLBACK_MODEL": "fallback-model"}):
            with patch("main.urllib.request.urlopen", side_effect=responses) as request:
                result = main.get_structured_test_analysis("{}", 5, metrics)
        models = [json.loads(call.args[0].data)["model"] for call in request.call_args_list]
        self.assertEqual(models, ["primary-model", "fallback-model"])
        self.assertEqual(result["subjective_score"], 2)

    def test_failed_mock_analysis_returns_error_without_saving_attempt(self):
        test_id = "mock-general-knowledge-b"
        self.user = {"id": "student9b001", "name": "Student One", "username": "student9b001", "role": "student", "is_admin": 0}
        with main.closing(main.connect()) as db:
            question_ids = [row["id"] for row in db.execute("SELECT id FROM questions WHERE test_id=? ORDER BY position", (test_id,))]
            attempts_before = db.execute("SELECT COUNT(*) FROM test_attempts WHERE is_mock=1").fetchone()[0]
        answers = {question_ids[0]: 1, question_ids[1]: "Four", question_ids[2]: 1, question_ids[3]: "Twelve minus five is seven."}
        with patch.object(main, "get_structured_test_analysis", side_effect=main.HTTPException(503, "unavailable")):
            response = self.client.post(f"/api/tests/{test_id}/attempts", json={"answers": answers, "is_mock": True})
        self.assertEqual(response.status_code, 503)
        with main.closing(main.connect()) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM test_attempts WHERE is_mock=1").fetchone()[0], attempts_before)

    def test_timed_submission_accepts_unanswered_questions(self):
        test_id, question_ids = self._create_test()
        self.user = {"id": "student9b001", "name": "Student One", "username": "student9b001", "role": "student", "is_admin": 0}
        with patch.object(main, "get_structured_test_analysis", return_value=self._fake_analysis()):
            response = self.client.post(f"/api/tests/{test_id}/attempts", json={"answers": {question_ids[0]: 1}})
        self.assertEqual(response.status_code, 200, response.text)
        with main.closing(main.connect()) as db:
            stored = json.loads(db.execute("SELECT answers_json FROM test_attempts WHERE id=?", (response.json()["attempt_id"],)).fetchone()["answers_json"])
        self.assertEqual(stored[question_ids[0]], 1)
        self.assertEqual(stored[question_ids[1]], "")

    def test_student_test_listing_filters_by_subject_and_mock_mode(self):
        self.user = {"id": "teacher01", "name": "Teacher One", "username": "teacher01", "role": "teacher", "is_admin": 0}
        created = self.client.post("/api/tests", json={"class_id": "class9-a", "title": "Newest Algebra", "subject": "Mathematics", "due_date": "2026-10-19"})
        self.assertEqual(created.status_code, 200, created.text)
        test_id = created.json()["id"]
        question = self.client.post(f"/api/tests/{test_id}/questions", json={"prompt": "Explain one method.", "points": 1, "question_type": "subjective", "answer_key": "A valid method."})
        self.assertEqual(question.status_code, 200, question.text)
        self.assertEqual(self.client.post(f"/api/tests/{test_id}/publish").status_code, 200)
        self.user = {"id": "student9a001", "name": "Student One", "username": "student9a001", "role": "student", "is_admin": 0}
        regular = self.client.get("/api/classes/class9-a/tests?subject=Mathematics&is_mock=false")
        self.assertEqual(regular.status_code, 200, regular.text)
        self.assertTrue(regular.json())
        self.assertTrue(all(item["subject"] == "Mathematics" and not item["is_mock"] for item in regular.json()))
        self.assertEqual(regular.json()[0]["id"], test_id)
        self.assertEqual(regular.json()[0]["due_date"], max(item["due_date"] for item in regular.json() if item["due_date"]))
        mock = self.client.get("/api/classes/class9-a/tests?is_mock=true")
        self.assertEqual(len(mock.json()), 1)
        self.assertTrue(mock.json()[0]["is_mock"])

    def test_student_can_review_their_submitted_test(self):
        test_id, question_ids = self._create_test()
        self.user = {"id": "student9b001", "name": "Student One", "username": "student9b001", "role": "student", "is_admin": 0}
        with patch.object(main, "get_structured_test_analysis", return_value=self._fake_analysis()):
            response = self.client.post(f"/api/tests/{test_id}/attempts", json={"answers": {question_ids[0]: 1, question_ids[1]: "My reasoning works."}})
        self.assertEqual(response.status_code, 200, response.text)

        review = self.client.get(f"/api/tests/{test_id}/attempts")
        self.assertEqual(review.status_code, 200, review.text)
        payload = review.json()
        self.assertEqual(payload["student_id"], "student9b001")
        self.assertEqual(payload["answers"][question_ids[0]], 1)
        self.assertEqual(payload["answers"][question_ids[1]], "My reasoning works.")

    def test_teacher_can_review_student_attempt_answers(self):
        test_id, question_ids = self._create_test()
        self.user = {"id": "student9b001", "name": "Student One", "username": "student9b001", "role": "student", "is_admin": 0}
        with patch.object(main, "get_structured_test_analysis", return_value=self._fake_analysis()):
            response = self.client.post(f"/api/tests/{test_id}/attempts", json={"answers": {question_ids[0]: 1, question_ids[1]: "My reasoning works."}})
        self.assertEqual(response.status_code, 200, response.text)

        self.user = {"id": "student9b002", "name": "Student Two", "username": "student9b002", "role": "student", "is_admin": 0}
        with patch.object(main, "get_structured_test_analysis", return_value=self._fake_analysis()):
            second_response = self.client.post(f"/api/tests/{test_id}/attempts", json={"answers": {question_ids[0]: 2, question_ids[1]: "I used a different method."}})
        self.assertEqual(second_response.status_code, 200, second_response.text)

        self.user = {"id": "teacher01", "name": "Teacher One", "username": "teacher01", "role": "teacher", "is_admin": 0}
        review = self.client.get(f"/api/tests/{test_id}/attempts?student_id=student9b001")
        self.assertEqual(review.status_code, 200, review.text)
        payload = review.json()
        self.assertEqual(payload["student_id"], "student9b001")
        self.assertEqual(payload["answers"][question_ids[0]], 1)
        self.assertEqual(payload["answers"][question_ids[1]], "My reasoning works.")
        self.assertEqual(payload["attempts"][0]["student_name"], "Aanya Rao")
        self.assertEqual(payload["attempts"][0]["result"]["analysis"], "Strong understanding.")
        all_attempts = self.client.get(f"/api/tests/{test_id}/attempts")
        self.assertEqual(all_attempts.status_code, 200, all_attempts.text)
        self.assertEqual(len(all_attempts.json()["attempts"]), 2)
        self.assertEqual({item["student_id"] for item in all_attempts.json()["attempts"]}, {"student9b001", "student9b002"})

    def test_test_creator_and_duration_are_returned_and_teacher_scoped(self):
        test_id, _ = self._create_test()
        with main.closing(main.connect()) as db:
            created_by = db.execute("SELECT created_by,duration_minutes FROM tests WHERE id=?", (test_id,)).fetchone()
        self.assertEqual(created_by["created_by"], "teacher01")
        self.assertEqual(created_by["duration_minutes"], 60)

        self.user = {"id": "teacher03", "name": "Teacher Three", "username": "teacher03", "role": "teacher", "is_admin": 0}
        visible = self.client.get("/api/classes/class9-b/tests?subject=English&is_mock=false")
        self.assertEqual(visible.status_code, 200, visible.text)
        self.assertTrue(all(item["subject"] == "English" and not item["is_mock"] for item in visible.json()))
        with main.closing(main.connect()) as db:
            owners = {row["id"]: row["created_by"] for row in db.execute("SELECT id,created_by FROM tests WHERE class_id=? AND subject=? AND is_mock=0", ("class9-b", "English"))}
        self.assertTrue(all(owners[item["id"]] == "teacher03" for item in visible.json()))

    def test_health_reports_configured_openrouter_provider(self):
        with patch.dict(os.environ, {"AI_PROVIDER": "openrouter", "OPEN_ROUTER_API_KEY": "unit-test-key", "OPEN_ROUTER_MODEL": "openrouter/free"}):
            result = main.health()
        self.assertEqual(result, {"status": "ok", "ai_configured": True, "provider": "openrouter", "model": "openrouter/free"})

    def test_login_returns_role_scoped_class_assignment_metadata(self):
        class_teacher = main.login(main.Login(username="teacher01", password=""))
        class_a = next(item for item in class_teacher["classes"] if item["id"] == "class9-a")
        self.assertTrue(class_a["is_class_teacher"])
        self.assertIn("Mathematics", class_a["subjects"])

        subject_teacher = main.login(main.Login(username="teacher07", password=""))
        class_a_subjects = next(item for item in subject_teacher["classes"] if item["id"] == "class9-a")
        self.assertFalse(class_a_subjects["is_class_teacher"])
        self.assertEqual(class_a_subjects["subjects"], ["Physics"])

        student = main.login(main.Login(username="student9a001", password=""))
        self.assertEqual([item["id"] for item in student["classes"]], ["class9-a"])

    def test_persistent_submission_combines_mcq_and_ai_and_hides_cumulative_ratings(self):
        test_id, question_ids = self._create_test()
        student_id = "student9b001"
        self.user = {"id": student_id, "name": "Student One", "username": student_id, "role": "student", "is_admin": 0}
        payload = {"answers": {question_ids[0]: 1, question_ids[1]: "Two plus two equals four."}}
        with patch.object(main, "get_structured_test_analysis", return_value=self._fake_analysis()) as ai:
            response = self.client.post(f"/api/tests/{test_id}/attempts", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["score"], 4.5)
        self.assertNotIn("overall_rating", response.json())
        self.assertNotIn("subject_rating", response.json())
        self.assertNotIn("metric_ratings", response.json())
        ai.assert_called_once()

        with main.closing(main.connect()) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM test_analyses WHERE test_id=? AND student_id=?", (test_id, student_id)).fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM student_analysis_snapshots WHERE source_test_id=? AND student_id=?", (test_id, student_id)).fetchone()[0], 1)

        duplicate_ai = patch.object(main, "get_structured_test_analysis", side_effect=AssertionError("duplicate called AI"))
        with duplicate_ai:
            duplicate = self.client.post(f"/api/tests/{test_id}/attempts", json=payload)
        self.assertEqual(duplicate.status_code, 409)

        self.user = {"id": "teacher01", "name": "Teacher One", "username": "teacher01", "role": "teacher", "is_admin": 0}
        report = self.client.get(f"/api/classes/class9-b/students/{student_id}/analysis")
        self.assertEqual(report.status_code, 200, report.text)
        self.assertIsNone(report.json()["overall"])
        self.assertEqual(set(report.json()["subject_ratings"]), {"Mathematics"})
        metric = next(iter(report.json()["metric_ratings"].values()))
        self.assertEqual(metric["subject"], "Mathematics")
        self.assertTrue(metric["name"])
        self.assertTrue(all("overall_rating" not in item["result"] and "overall_analysis" not in item["result"] for item in report.json()["tests"]))
        unauthorized_subject = self.client.get(f"/api/classes/class9-b/students/{student_id}/analysis?subject=Biology")
        self.assertEqual(unauthorized_subject.status_code, 403)
        subject_report = self.client.get(f"/api/classes/class9-b/students/{student_id}/analysis?subject=Mathematics")
        self.assertEqual(subject_report.status_code, 200, subject_report.text)
        self.assertTrue(all(item["subject"] == "Mathematics" for item in subject_report.json()["tests"]))
        self.assertEqual(set(subject_report.json()["subject_analyses"]), {"Mathematics"})
        self.assertTrue(subject_report.json()["subject_analyses"]["Mathematics"]["analysis"])
        historical = self.client.get(f"/api/classes/class9-b/students/{student_id}/analysis?as_of=2026-01-15")
        self.assertEqual(historical.status_code, 200, historical.text)
        self.assertTrue(historical.json()["as_of"].startswith("2026-01-15"))
        self.user = {"id": "teacher01", "name": "Class Teacher", "username": "teacher01", "role": "teacher", "is_admin": 0}
        class_teacher_report = self.client.get("/api/classes/class9-a/students/student9a001/analysis")
        self.assertEqual(class_teacher_report.status_code, 200, class_teacher_report.text)
        self.assertIsNotNone(class_teacher_report.json()["overall"]["rating"])
        self.assertEqual(len(class_teacher_report.json()["subject_ratings"]), 10)
        self.assertEqual(len(class_teacher_report.json()["subject_analyses"]), 10)
        self.assertEqual(len(class_teacher_report.json()["metric_ratings"]), 5)

    def test_teacher_tests_report_counts_and_cannot_be_edited_after_attempt(self):
        test_id, _ = self._create_test()
        listing = self.client.get("/api/classes/class9-b/tests?subject=Mathematics&is_mock=false")
        test = next(item for item in listing.json() if item["id"] == test_id)
        self.assertEqual(test["students_taken"], 0)
        edited = self.client.put(f"/api/tests/{test_id}", json={
            "title": "Updated Algebra Check",
            "subject": "Mathematics",
            "kind": "Assessment",
            "due_date": "2026-10-20",
            "duration_minutes": 30,
            "questions": [{"prompt": "What is 3 + 3?", "points": 2, "question_type": "mcq", "options": ["5", "6"], "answer_key": 1}],
        })
        self.assertEqual(edited.status_code, 200, edited.text)
        question = self.client.get(f"/api/tests/{test_id}").json()["questions"][0]
        self.assertEqual(question["prompt"], "What is 3 + 3?")
        self.user = {"id": "student9b002", "name": "Student Two", "username": "student9b002", "role": "student", "is_admin": 0}
        with patch.object(main, "get_structured_test_analysis", return_value=self._fake_analysis()):
            submitted = self.client.post(f"/api/tests/{test_id}/attempts", json={"answers": {question["id"]: 1}})
        self.assertEqual(submitted.status_code, 200, submitted.text)
        self.user = {"id": "teacher01", "name": "Teacher One", "username": "teacher01", "role": "teacher", "is_admin": 0}
        blocked = self.client.put(f"/api/tests/{test_id}", json={
            "title": "Too late", "subject": "Mathematics", "kind": "Assessment", "duration_minutes": 30,
            "questions": [{"prompt": "Edit after attempt?", "points": 1, "question_type": "subjective", "answer_key": "No"}],
        })
        self.assertEqual(blocked.status_code, 409)
        updated_listing = self.client.get("/api/classes/class9-b/tests?subject=Mathematics&is_mock=false")
        self.assertEqual(next(item for item in updated_listing.json() if item["id"] == test_id)["students_taken"], 1)
        deleted = self.client.delete(f"/api/tests/{test_id}")
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertFalse(any(item["id"] == test_id for item in self.client.get("/api/classes/class9-b/tests?subject=Mathematics&is_mock=false").json()))

    def test_teacher_cannot_create_mock_test(self):
        response = self.client.post("/api/tests", json={"class_id": "class9-b", "title": "Teacher mock", "subject": "Mathematics", "is_mock": True})
        self.assertEqual(response.status_code, 400)

    def test_mock_submission_is_not_saved_and_other_subject_teacher_is_denied(self):
        test_id = "mock-general-knowledge-b"
        with main.closing(main.connect()) as db:
            question_ids = [row["id"] for row in db.execute("SELECT id FROM questions WHERE test_id=? ORDER BY position", (test_id,))]
        self.user = {"id": "student9b001", "name": "Student One", "username": "student9b001", "role": "student", "is_admin": 0}
        payload = {"answers": {question_ids[0]: 1, question_ids[1]: "Four, by adding two and two."}, "is_mock": True}
        with main.closing(main.connect()) as db:
            attempts_before = db.execute("SELECT COUNT(*) FROM test_attempts WHERE is_mock=1").fetchone()[0]
            snapshots_before = db.execute("SELECT COUNT(*) FROM student_analysis_snapshots").fetchone()[0]
        with patch.object(main, "get_structured_test_analysis", return_value=self._fake_analysis()):
            response = self.client.post(f"/api/tests/{test_id}/attempts", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["is_mock"])
        self.assertNotIn("overall_rating", response.json())
        with main.closing(main.connect()) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM test_attempts WHERE is_mock=1").fetchone()[0], attempts_before)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM student_analysis_snapshots").fetchone()[0], snapshots_before)

        self.user = {"id": "teacher03", "name": "Teacher Three", "username": "teacher03", "role": "teacher", "is_admin": 0}
        denied = self.client.post("/api/tests", json={"class_id": "class9-b", "title": "Wrong subject", "subject": "Mathematics"})
        self.assertEqual(denied.status_code, 403)

    def test_answers_survive_ai_failure_and_can_be_retried(self):
        test_id, question_ids = self._create_test()
        self.user = {"id": "student9b002", "name": "Student Two", "username": "student9b002", "role": "student", "is_admin": 0}
        payload = {"answers": {question_ids[0]: 1, question_ids[1]: "Two plus two makes four."}}
        with patch.object(main, "get_structured_test_analysis", side_effect=main.HTTPException(402, "No credits")):
            failed = self.client.post(f"/api/tests/{test_id}/attempts", json=payload)
        self.assertEqual(failed.status_code, 402)
        with main.closing(main.connect()) as db:
            pending = db.execute("SELECT id,status,answers_json FROM test_attempts WHERE test_id=? AND student_id=?", (test_id, self.user["id"])).fetchone()
            self.assertEqual(pending["status"], "submitted")
            self.assertEqual(json.loads(pending["answers_json"]), payload["answers"])
        reopened = self.client.get(f"/api/tests/{test_id}")
        self.assertEqual(reopened.status_code, 200, reopened.text)
        self.assertEqual(reopened.json()["my_attempt"]["answers"], payload["answers"])

        with patch.object(main, "get_structured_test_analysis", return_value=self._fake_analysis()):
            retried = self.client.post(f"/api/tests/{test_id}/attempts", json=payload)
        self.assertEqual(retried.status_code, 200, retried.text)
        self.assertEqual(retried.json()["attempt_id"], pending["id"])

    def test_admin_can_manage_account_and_assignment_but_subject_teacher_cannot(self):
        self.user = {"id": "teacher01", "name": "Teacher One", "username": "teacher01", "role": "teacher", "is_admin": 0}
        denied = self.client.get("/api/admin/classes")
        self.assertEqual(denied.status_code, 403)
        self.user = {"id": "admin-test", "name": "Administrator", "username": "admin-test", "role": "teacher", "is_admin": 1}
        classes = self.client.get("/api/admin/classes")
        self.assertEqual(classes.status_code, 200, classes.text)
        self.assertEqual(len(classes.json()), 4)
        directory = self.client.get("/api/admin/users")
        self.assertEqual(directory.status_code, 200, directory.text)
        self.assertTrue(all(item["role"] in {"student", "teacher"} and not item["is_admin"] for item in directory.json()))
        created_class = self.client.post("/api/admin/classes", json={"name": "Class 8 Section A", "year": "2026 / 27"})
        self.assertEqual(created_class.status_code, 200, created_class.text)
        duplicate_class = self.client.post("/api/admin/classes", json={"name": "class 8 section a", "year": "2026 / 27"})
        self.assertEqual(duplicate_class.status_code, 409)
        admin_ratings = self.client.get("/api/classes/class9-a/ratings")
        self.assertEqual(admin_ratings.status_code, 403)
        self.assertEqual(self.client.get("/api/classes/class9-a/students/student9a001/analysis").status_code, 403)
        student = self.client.post("/api/admin/students", json={"username": "newstudent", "name": "New Student", "password": "long-enough-test-password", "class_id": "class9-a"})
        self.assertEqual(student.status_code, 200, student.text)
        updated_student = self.client.patch(f"/api/admin/users/{student.json()['id']}", json={"name": "Updated Student", "password": "another-long-test-password", "class_id": "class9-d"})
        self.assertEqual(updated_student.status_code, 200, updated_student.text)
        with main.closing(main.connect()) as db:
            self.assertEqual(db.execute("SELECT name FROM users WHERE id=?", (student.json()["id"],)).fetchone()["name"], "Updated Student")
            self.assertEqual(db.execute("SELECT class_id FROM enrollments WHERE student_id=?", (student.json()["id"],)).fetchone()["class_id"], "class9-d")
        deleted_student = self.client.delete(f"/api/admin/users/{student.json()['id']}")
        self.assertEqual(deleted_student.status_code, 200, deleted_student.text)
        self.assertEqual(self.client.delete("/api/admin/users/admin-test").status_code, 404)
        teacher = self.client.post("/api/admin/teachers", json={"username": "newteacher", "name": "New Teacher", "password": "long-enough-test-password", "assignments": [{"teacher_id": "newteacher", "class_id": "class9-a", "assignment_type": "subject", "subject": "Biology"}]})
        self.assertEqual(teacher.status_code, 200, teacher.text)
        assignment = self.client.post("/api/admin/assignments", json={"teacher_id": "newteacher", "class_id": "class9-c", "assignment_type": "class", "subject": None})
        self.assertEqual(assignment.status_code, 200, assignment.text)
        profile = next(item for item in self.client.get("/api/admin/users?role=teacher").json() if item["id"] == "newteacher")
        self.assertEqual({item["class_id"] for item in profile["assignments"]}, {"class9-a", "class9-c"})
        updated_assignments = self.client.put("/api/admin/teachers/newteacher/assignments", json={"assignments": [{"class_id": "class9-a", "assignment_type": "subject", "subject": "Physics"}]})
        self.assertEqual(updated_assignments.status_code, 200, updated_assignments.text)
        profile = next(item for item in self.client.get("/api/admin/users?role=teacher").json() if item["id"] == "newteacher")
        self.assertEqual([(item["class_id"], item["subject"]) for item in profile["assignments"]], [("class9-a", "Physics")])
        with main.closing(main.connect()) as db:
            subject_assignment_id = db.execute("SELECT id FROM teacher_assignments WHERE teacher_id=? AND class_id=? AND assignment_type='subject'", ("newteacher", "class9-a")).fetchone()["id"]
        revoked = self.client.delete(f"/api/admin/assignments/{subject_assignment_id}")
        self.assertEqual(revoked.status_code, 200, revoked.text)
        assignment_id = assignment.json()["id"]
        self.assertEqual(self.client.delete(f"/api/admin/assignments/{assignment_id}").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/admin/users/{teacher.json()['id']}").status_code, 200)
        self.user = {"id": "newteacher", "name": "New Teacher", "username": "newteacher", "role": "teacher", "is_admin": 0}
        self.assertEqual(self.client.get("/api/classes/class9-a/tests").status_code, 403)

    def test_demo_seed_has_requested_roster_and_history(self):
        with main.closing(main.connect()) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM classes WHERE id LIKE 'class9-%'").fetchone()[0], 4)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM users WHERE role='student' AND username LIKE 'student9%' ").fetchone()[0], 40)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM users WHERE role='teacher' AND username LIKE 'teacher%' ").fetchone()[0], 20)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tests WHERE is_mock=0 AND id LIKE 'test-class9-%'").fetchone()[0], 160)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM test_analyses WHERE test_id LIKE 'test-class9-%'").fetchone()[0], 1600)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM student_analysis_snapshots WHERE source_test_id LIKE 'test-class9-%'").fetchone()[0], 1600)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM teacher_assignments WHERE assignment_type='class' AND id LIKE 'class-teacher-class9-%'").fetchone()[0], 4)
            january = db.execute("SELECT subject_ratings_json FROM student_analysis_snapshots WHERE student_id=? AND snapshot_at LIKE '2026-01-15%' ORDER BY id DESC LIMIT 1", ("student9a001",)).fetchone()
            self.assertEqual(len(json.loads(january["subject_ratings_json"])), 10)
            january_analyses = db.execute("SELECT subject_analyses_json FROM student_analysis_snapshots WHERE student_id=? AND snapshot_at LIKE '2026-01-15%' ORDER BY id DESC LIMIT 1", ("student9a001",)).fetchone()
            self.assertEqual(len(json.loads(january_analyses["subject_analyses_json"])), 10)
            student_names = [row["name"] for row in db.execute("SELECT name FROM users WHERE role='student' AND username LIKE 'student9%'")]
            self.assertEqual(len(set(student_names)), 40)
            self.assertFalse(any(any(character.isdigit() for character in name) for name in student_names))
            teacher_names = [row["name"] for row in db.execute("SELECT name FROM users WHERE role='teacher' AND username LIKE 'teacher%'")]
            self.assertEqual(len(set(teacher_names)), 20)
            self.assertFalse(any(any(character.isdigit() for character in name) for name in teacher_names))
            metric_names = {row["name"] for row in db.execute("SELECT DISTINCT name FROM teacher_metrics WHERE class_id LIKE 'class9-%'")}
            self.assertEqual(metric_names, {"Precision", "Time management", "Critical thinking", "Concept application", "Communication"})
            mock_question = db.execute("""SELECT q.prompt,q.options_json FROM questions q JOIN tests t ON t.id=q.test_id
                WHERE t.id=? ORDER BY q.position LIMIT 1""", ("mock-general-knowledge-a",)).fetchone()
            self.assertIn("planet", mock_question["prompt"].lower())
            self.assertGreaterEqual(len(json.loads(mock_question["options_json"])), 2)

    def test_seed_refresh_removes_stale_class_enrollment(self):
        with main.closing(main.connect()) as db:
            db.execute("INSERT INTO classes(id,name,year,teacher_id) VALUES(?,?,?,NULL)", ("class9-algebra", "Class 9 - Algebra", "2026"))
            db.execute("INSERT INTO enrollments(class_id,student_id) VALUES(?,?)", ("class9-algebra", "student9a001"))
            db.execute("INSERT INTO users(id,name,role,username,is_admin,is_active) VALUES(?,?,?,?,0,1)", ("student9a011", "Aanya Sharma", "student", "student9a011"))
            db.execute("INSERT INTO enrollments(class_id,student_id) VALUES(?,?)", ("class9-a", "student9a011"))
            db.execute("INSERT INTO test_attempts(id,test_id,student_id,answers_json,status,submitted_at,is_mock) VALUES(?,?,?,?,?,?,0)", ("extra-attempt", "test-class9-a-0-1", "student9a011", "{}", "analysed", "2026-01-15T08:00:00+00:00"))
            db.execute("INSERT INTO test_analyses(id,attempt_id,test_id,student_id,result_json,created_at) VALUES(?,?,?,?,?,?)", ("extra-analysis", "extra-attempt", "test-class9-a-0-1", "student9a011", "{}", "2026-01-15T08:00:00+00:00"))
            db.execute("INSERT INTO student_analysis_snapshots(id,student_id,class_id,source_test_id,snapshot_at,overall_analysis,overall_rating,subject_ratings_json,metric_ratings_json,subject_analyses_json) VALUES(?,?,?,?,?,?,?,?,?,?)", ("extra-snapshot", "student9a011", "class9-a", "test-class9-a-0-1", "2026-01-15T08:00:00+00:00", "Sample", 5, "{}", "{}", "{}"))
            db.execute("UPDATE users SET name=? WHERE id=?", ("Sample Student A-001", "student9a001"))
            db.execute("UPDATE test_analyses SET result_json=? WHERE test_id=? AND student_id=?", (json.dumps({"test_rating": 8, "analysis": "The student demonstrated mathematics knowledge with improving accuracy."}), "test-class9-a-0-1", "student9a001"))
            db.execute("UPDATE questions SET prompt=? WHERE id=?", ("Choose the correct response for Mathematics: question 1.", "test-class9-a-0-1-q1"))
            main.seed_school_data(db, main.password_digest, "", "", "schooladmin", "")
            class_ids = [row["class_id"] for row in db.execute("SELECT class_id FROM enrollments WHERE student_id=?", ("student9a001",))]
            student_name = db.execute("SELECT name FROM users WHERE id=?", ("student9a001",)).fetchone()["name"]
            question_prompt = db.execute("SELECT prompt FROM questions WHERE id=?", ("test-class9-a-0-1-q1",)).fetchone()["prompt"]
            refreshed_analysis = json.loads(db.execute("SELECT result_json FROM test_analyses WHERE test_id=? AND student_id=?", ("test-class9-a-0-1", "student9a001")).fetchone()["result_json"])
            metric_count = db.execute("SELECT COUNT(*) FROM teacher_metrics WHERE class_id=? AND retired_at IS NULL", ("class9-a",)).fetchone()[0]
            removed_student = db.execute("SELECT COUNT(*) FROM users WHERE id=?", ("student9a011",)).fetchone()[0]
            removed_attempt = db.execute("SELECT COUNT(*) FROM test_attempts WHERE id=?", ("extra-attempt",)).fetchone()[0]
            legacy_class = db.execute("SELECT COUNT(*) FROM classes WHERE id=?", ("class9-algebra",)).fetchone()[0]
            db.commit()
        self.assertEqual(class_ids, ["class9-a"])
        self.assertFalse(any(character.isdigit() for character in student_name))
        self.assertEqual(question_prompt, "Solve 3x = 12.")
        self.assertIn("Mathematics", refreshed_analysis["analysis"])
        self.assertNotIn("improving accuracy", refreshed_analysis["analysis"])
        self.assertTrue(refreshed_analysis["advice"])
        self.assertTrue(refreshed_analysis["strengths"])
        self.assertEqual(metric_count, 50)
        self.assertEqual(removed_student, 0)
        self.assertEqual(removed_attempt, 0)
        self.assertEqual(legacy_class, 0)

    def test_admin_can_be_bootstrapped_after_demo_seed_marker(self):
        with main.closing(main.connect()) as db:
            result = main.seed_school_data(db, main.password_digest, "", "", "schooladmin", "secure-test-admin-password")
            admin = db.execute("SELECT is_admin,password_salt,password_hash FROM users WHERE username=?", ("schooladmin",)).fetchone()
        self.assertFalse(result["seeded"])
        self.assertTrue(result["admin_seeded"])
        self.assertTrue(admin["is_admin"])
        self.assertEqual(main.password_digest("secure-test-admin-password", admin["password_salt"]), admin["password_hash"])


if __name__ == "__main__":
    unittest.main()