# Structured Assessment AI Sample

The assessment path calls `build_analysis_context` and sends the resulting compact JSON string to OpenRouter's Chat Completions API. It requests `response_format: {"type":"json_object"}` and validates the JSON before storing it. MCQs are scored by the backend; the model scores subjective questions only.

## Sample Prompt

```json
{
  "test": {
    "id": "sample-math-01",
    "title": "Linear Equations Check",
    "subject": "Mathematics",
    "date": "2026-10-19",
    "max_score": 7.5,
    "is_mock": false
  },
  "questions_and_answers": [
    {
      "id": "q1",
      "type": "mcq",
      "prompt": "Solve 3x = 12.",
      "points": 2.5,
      "student_answer": 1,
      "options": ["x=3", "x=4", "x=5"],
      "answer_key": 1
    },
    {
      "id": "q2",
      "type": "subjective",
      "prompt": "Explain how to solve 2x + 5 = 13.",
      "points": 5,
      "student_answer": "I subtract 5 from both sides: 2x=8, then divide both sides by 2, so x=4.",
      "answer_key": "Subtract 5 from both sides, then divide by 2 to get x=4."
    }
  ],
  "mcq_validation": {
    "score": 2.5,
    "max_score": 2.5,
    "question_results": [
      {"question_id": "q1", "correct": true, "score": 2.5, "max_score": 2.5}
    ]
  },
  "current_student_state": {
    "as_of": "2026-10-18",
    "overall_analysis": "Consistent effort; written reasoning is developing.",
    "overall_rating": 6.4,
    "subject_ratings": {"Mathematics": 6.8},
    "metric_ratings": {"metric-math-reasoning": 6.0}
  },
  "previous_test_analysis": {
    "title": "Integer Operations",
    "subject": "Mathematics",
    "date": "2026-10-10",
    "test_rating": 6.0,
    "analysis": "Correct concepts, some sign errors.",
    "advice": "Check each sign.",
    "score": 6
  },
  "current_subject_ratings": {"Mathematics": 6.8},
  "current_metric_ratings": {"metric-math-reasoning": 6.0},
  "teacher_metrics": [
    {"id": "metric-math-reasoning", "name": "Mathematical reasoning", "description": "Shows logical steps", "weight": 1}
  ],
  "required_output": {
    "subjective_score": "number, between 0 and subjective-question points",
    "test_rating": "number from 0 to 10",
    "analysis": "string",
    "strengths": ["string"],
    "focus_areas": ["string"],
    "advice": "string",
    "subject_rating": "number from 0 to 10",
    "metric_ratings": [
      {"metric_id": "string", "rating": "number from 0 to 10", "evidence": "string"}
    ],
    "overall_rating": "number from 0 to 10",
    "overall_analysis": "string"
  }
}
```

## Illustrative Response

This is a schema example, **not an AI-generated response**:

```json
{
  "subjective_score": 4.5,
  "test_rating": 9.3,
  "analysis": "The student used inverse operations correctly and showed a clear sequence of steps.",
  "strengths": ["Accurate algebra", "Clear working"],
  "focus_areas": ["Keep checking the final value in the original equation"],
  "advice": "Your steps are clear. Substitute x=4 back into the equation to check your result.",
  "subject_rating": 7.1,
  "metric_ratings": [
    {"metric_id": "metric-math-reasoning", "rating": 8.0, "evidence": "Both inverse-operation steps are shown."}
  ],
  "overall_rating": 6.6,
  "overall_analysis": "Overall progress is steady, with stronger mathematical reasoning this week."
}
```

The backend merges the 4.5 subjective points with the already validated 2.5 MCQ points, stores the per-test result, and appends the dated cumulative snapshot. Student-facing responses omit cumulative ratings.

## Live Request Status

The OpenRouter catalog authenticated successfully. Paid `openai/gpt-4.1-mini` and several individual free routes returned HTTP 402 or invalid JSON. The dynamic `openrouter/free` route returned synthetic analyses that passed the backend's complete response validator, including score bounds and required metric evidence. This is the configured default. Because routing is dynamic, malformed responses remain rejected and can be retried. The request/response contract is also covered by mocked-response tests.
