import json
import unittest

from backend.school_services import (
    build_analysis_context,
    score_mcq_questions,
    validate_analysis_result,
)


class SchoolServiceTests(unittest.TestCase):
    def test_mcq_scoring_is_deterministic_and_limits_max_score(self):
        questions = [
            {"id": "q1", "question_type": "mcq", "options": ["A", "B"], "answer_key": 1, "points": 2},
            {"id": "q2", "question_type": "subjective", "points": 3},
            {"id": "q3", "question_type": "mcq", "options": ["A", "B"], "answer_key": 0, "points": 1},
        ]

        result = score_mcq_questions(questions, {"q1": 1, "q3": 1})

        self.assertEqual(result["score"], 2)
        self.assertEqual(result["max_score"], 3)
        self.assertEqual([item["correct"] for item in result["question_results"]], [True, False])

    def test_analysis_context_contains_history_metrics_and_answer_key(self):
        payload = json.loads(build_analysis_context(
            {"title": "Quiz", "subject": "Math", "date": "2026-01-01"},
            [{"id": "q1", "question_type": "subjective", "prompt": "Explain", "points": 2, "answer_key": "Expected reasoning"}],
            {"q1": "My reasoning"},
            {"overall_rating": 7},
            {"test_rating": 6},
            {"Math": 7},
            {"show_work": 6},
            [{"id": "show_work", "name": "Show work"}],
            {"score": 1, "max_score": 1},
        ))

        self.assertEqual(payload["questions_and_answers"][0]["answer_key"], "Expected reasoning")
        self.assertEqual(payload["current_student_state"]["overall_rating"], 7)
        self.assertEqual(payload["previous_test_analysis"]["test_rating"], 6)
        self.assertIn("teacher_metrics", payload)

    def test_analysis_result_requires_complete_valid_metric_ratings(self):
        metrics = [{"id": "show_work"}]
        result = {
            "score": 8,
            "test_rating": 8,
            "analysis": "Good work.",
            "strengths": ["Accuracy"],
            "focus_areas": [],
            "advice": "Show each step.",
            "subject_rating": 7.5,
            "metric_ratings": [{"metric_id": "show_work", "rating": 6, "evidence": "Some steps omitted."}],
            "overall_rating": 7,
            "overall_analysis": "Steady progress.",
        }

        self.assertEqual(validate_analysis_result(result, 10, metrics), result)
        with self.assertRaises(ValueError):
            validate_analysis_result({**result, "overall_rating": 11}, 10, metrics)
        with self.assertRaises(ValueError):
            validate_analysis_result({**result, "metric_ratings": []}, 10, metrics)
        with self.assertRaises(ValueError):
            validate_analysis_result({**result, "metric_ratings": [result["metric_ratings"][0]] * 2}, 10, metrics)
        with self.assertRaises(ValueError):
            validate_analysis_result({**result, "strengths": [None]}, 10, metrics)


if __name__ == "__main__":
    unittest.main()