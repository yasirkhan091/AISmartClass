import json
import math


def score_mcq_questions(questions: list[dict], answers: dict) -> dict:
    results = []
    score = 0.0
    max_score = 0.0
    for question in questions:
        if question.get("question_type") != "mcq":
            continue
        options = question.get("options", [])
        answer_key = question.get("answer_key")
        points = float(question.get("points", 1))
        selected = answers.get(question["id"])
        try:
            selected_index = int(selected)
        except (TypeError, ValueError):
            selected_index = -1
        correct = selected_index == answer_key
        score += points if correct else 0
        max_score += points
        results.append({
            "question_id": question["id"],
            "correct": correct,
            "score": points if correct else 0,
            "max_score": points,
            "selected_answer": options[selected_index] if 0 <= selected_index < len(options) else "No answer",
            "correct_answer": options[answer_key] if isinstance(answer_key, int) and 0 <= answer_key < len(options) else "",
        })
    return {"score": score, "max_score": max_score, "question_results": results}


def build_analysis_context(
    test: dict,
    questions: list[dict],
    answers: dict,
    current_state: dict,
    previous_test: dict | None,
    subject_ratings: dict,
    metric_ratings: dict,
    metrics: list[dict],
    mcq_results: dict,
) -> str:
    normalized_questions = []
    for question in questions:
        item = {
            "id": question["id"],
            "type": question["question_type"],
            "prompt": question["prompt"],
            "points": question["points"],
            "student_answer": answers.get(question["id"], ""),
        }
        if question["question_type"] == "mcq":
            item["options"] = question.get("options", [])
            item["answer_key"] = question.get("answer_key")
        else:
            item["answer_key"] = question.get("answer_key", "")
        normalized_questions.append(item)
    payload = {
        "test": test,
        "questions_and_answers": normalized_questions,
        "mcq_validation": mcq_results,
        "current_student_state": current_state,
        "previous_test_analysis": previous_test,
        "current_subject_ratings": subject_ratings,
        "current_metric_ratings": metric_ratings,
        "teacher_metrics": metrics,
        "required_output": {
            "subjective_score": "number, between zero and the subjective-question points",
            "test_rating": "number from 0 to 10",
            "analysis": "string",
            "strengths": "array of strings",
            "focus_areas": "array of strings",
            "advice": "string for the student",
            "subject_rating": "number from 0 to 10",
            "metric_ratings": [{"metric_id": "string", "rating": "number from 0 to 10", "evidence": "string"}],
            "overall_rating": "number from 0 to 10",
            "overall_analysis": "string",
        },
    }
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def validate_analysis_result(result: dict, max_score: float, metrics: list[dict]) -> dict:
    if not isinstance(result, dict):
        raise ValueError("Analysis response must be a JSON object")
    score = result.get("subjective_score", result.get("score"))
    if not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= max_score:
        raise ValueError("Analysis response subjective score is outside the test range")
    result["subjective_score"] = score
    for field in ("test_rating", "subject_rating", "overall_rating"):
        value = result.get(field)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 10:
            raise ValueError(f"Analysis response {field} must be between 0 and 10")
    for field in ("analysis", "advice", "overall_analysis"):
        if not isinstance(result.get(field), str) or not result[field].strip():
            raise ValueError(f"Analysis response is missing {field}")
    for field in ("strengths", "focus_areas", "metric_ratings"):
        if not isinstance(result.get(field), list):
            raise ValueError(f"Analysis response {field} must be an array")
    for field in ("strengths", "focus_areas"):
        if any(not isinstance(item, str) or not item.strip() for item in result[field]):
            raise ValueError(f"Analysis response {field} must contain non-empty strings")
    metric_ids = {metric["id"] for metric in metrics}
    returned_metric_ids = set()
    for item in result["metric_ratings"]:
        if not isinstance(item, dict) or item.get("metric_id") not in metric_ids:
            raise ValueError("Analysis response contains an unknown teacher metric")
        if item["metric_id"] in returned_metric_ids:
            raise ValueError("Analysis response must rate every teacher metric exactly once")
        rating = item.get("rating")
        if not isinstance(rating, (int, float)) or not math.isfinite(rating) or not 0 <= rating <= 10:
            raise ValueError("Metric ratings must be between 0 and 10")
        if not isinstance(item.get("evidence"), str) or not item["evidence"].strip():
            raise ValueError("Metric ratings must include evidence")
        returned_metric_ids.add(item["metric_id"])
    if returned_metric_ids != metric_ids:
        raise ValueError("Analysis response must rate every teacher metric exactly once")
    return result