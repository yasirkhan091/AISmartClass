import base64
import json
import logging
import os
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import closing
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("smartclass")

ROOT = Path(__file__).parent
DB_PATH = Path(os.getenv("SMARTCLASS_DB", ROOT / "smartclass.db"))
UPLOADS = Path(os.getenv("SMARTCLASS_UPLOADS", ROOT / "uploads"))
UPLOADS.mkdir(parents=True, exist_ok=True)
app = FastAPI(title="AI Smartclass API", version="1.0")


def connect():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def initialize():
    with closing(connect()) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE, role TEXT NOT NULL CHECK(role IN ('teacher','student')));
        CREATE TABLE IF NOT EXISTS classes(id TEXT PRIMARY KEY, name TEXT NOT NULL, year TEXT NOT NULL, teacher_id TEXT REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS enrollments(class_id TEXT REFERENCES classes(id), student_id TEXT REFERENCES users(id), PRIMARY KEY(class_id, student_id));
        CREATE TABLE IF NOT EXISTS plans(id TEXT PRIMARY KEY, class_id TEXT REFERENCES classes(id), week TEXT NOT NULL, title TEXT NOT NULL, target TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS tests(id TEXT PRIMARY KEY, class_id TEXT REFERENCES classes(id), title TEXT NOT NULL, subject TEXT NOT NULL, kind TEXT NOT NULL, due_date TEXT, paper_path TEXT);
        CREATE TABLE IF NOT EXISTS questions(id TEXT PRIMARY KEY, test_id TEXT REFERENCES tests(id), prompt TEXT NOT NULL, points REAL NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS criteria(id TEXT PRIMARY KEY, test_id TEXT REFERENCES tests(id), name TEXT NOT NULL, weight REAL NOT NULL, guidance TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS submissions(id TEXT PRIMARY KEY, test_id TEXT REFERENCES tests(id), student_id TEXT REFERENCES users(id), pdf_path TEXT NOT NULL, extracted_text TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'submitted', UNIQUE(test_id, student_id));
        CREATE TABLE IF NOT EXISTS evaluations(id TEXT PRIMARY KEY, submission_id TEXT UNIQUE REFERENCES submissions(id), score REAL NOT NULL, max_score REAL NOT NULL, feedback_json TEXT NOT NULL, teacher_advice TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS profiles(student_id TEXT PRIMARY KEY REFERENCES users(id), context_json TEXT NOT NULL DEFAULT '{}');
        """)
        db.commit()


initialize()
logger.info("Smartclass database initialized")


class Login(BaseModel):
    name: str
    role: str
    email: str | None = None


class PlanInput(BaseModel):
    week: str
    title: str
    target: str


class TestInput(BaseModel):
    class_id: str
    title: str
    subject: str
    kind: str
    due_date: str | None = None


class QuestionInput(BaseModel):
    prompt: str
    points: float = 1


class CriteriaInput(BaseModel):
    name: str
    weight: float
    guidance: str = ""


@app.get("/api/health")
def health():
    return {"status": "ok", "ai_configured": bool(os.getenv("AI_API_KEY"))}


@app.post("/api/login")
def login(data: Login):
    if data.role not in {"teacher", "student"}:
        raise HTTPException(400, "Role must be teacher or student")
    user_id = data.email or str(uuid.uuid4())
    with closing(connect()) as db:
        db.execute("INSERT INTO users(id,name,email,role) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, role=excluded.role", (user_id, data.name, data.email, data.role))
        db.execute("INSERT OR IGNORE INTO profiles(student_id,context_json) VALUES(?,?)", (user_id, json.dumps({"name": data.name, "strengths": [], "focus_areas": [], "assessment_history": []})))
        db.commit()
        row = db.execute("SELECT id,name,email,role FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row)


@app.post("/api/classes")
def create_class(name: str = Form(...), year: str = Form(...), teacher_id: str = Form(...)):
    class_id = str(uuid.uuid4())
    with closing(connect()) as db:
        db.execute("INSERT INTO classes VALUES(?,?,?,?)", (class_id, name, year, teacher_id))
        db.commit()
    return {"id": class_id, "name": name, "year": year}


@app.post("/api/classes/{class_id}/plans")
def add_plan(class_id: str, data: PlanInput):
    plan_id = str(uuid.uuid4())
    with closing(connect()) as db:
        db.execute("INSERT INTO plans VALUES(?,?,?,?,?)", (plan_id, class_id, data.week, data.title, data.target))
        db.commit()
    return {"id": plan_id, **data.model_dump()}


@app.get("/api/classes/{class_id}/plans")
def list_plans(class_id: str):
    with closing(connect()) as db:
        return [dict(row) for row in db.execute("SELECT * FROM plans WHERE class_id=? ORDER BY week", (class_id,))]


@app.post("/api/tests")
def create_test(data: TestInput):
    test_id = str(uuid.uuid4())
    with closing(connect()) as db:
        db.execute("INSERT INTO tests(id,class_id,title,subject,kind,due_date) VALUES(?,?,?,?,?,?)", (test_id, data.class_id, data.title, data.subject, data.kind, data.due_date))
        db.commit()
    return {"id": test_id, **data.model_dump()}


@app.post("/api/tests/{test_id}/paper")
async def upload_test_paper(test_id: str, paper: UploadFile = File(...)):
    if paper.content_type != "application/pdf":
        logger.warning("Rejected non-PDF test paper")
        raise HTTPException(415, "Upload a PDF")
    path = UPLOADS / f"{uuid.uuid4()}.pdf"
    path.write_bytes(await paper.read())
    with closing(connect()) as db:
        updated = db.execute("UPDATE tests SET paper_path=? WHERE id=?", (str(path), test_id)).rowcount
        db.commit()
    if not updated:
        path.unlink(missing_ok=True)
        logger.warning("Could not attach test paper: test not found")
        raise HTTPException(404, "Test not found")
    logger.info("Test paper uploaded")
    return {"test_id": test_id, "paper": paper.filename, "stored": True}


@app.post("/api/tests/{test_id}/questions")
def add_question(test_id: str, data: QuestionInput):
    question_id = str(uuid.uuid4())
    with closing(connect()) as db:
        db.execute("INSERT INTO questions VALUES(?,?,?,?)", (question_id, test_id, data.prompt, data.points))
        db.commit()
    return {"id": question_id, "test_id": test_id, **data.model_dump()}


@app.post("/api/tests/{test_id}/criteria")
def add_criteria(test_id: str, data: CriteriaInput):
    criteria_id = str(uuid.uuid4())
    with closing(connect()) as db:
        db.execute("INSERT INTO criteria VALUES(?,?,?,?,?)", (criteria_id, test_id, data.name, data.weight, data.guidance))
        db.commit()
    return {"id": criteria_id, "test_id": test_id, **data.model_dump()}


@app.post("/api/tests/{test_id}/submissions")
async def submit_answers(test_id: str, student_id: str = Form(...), answer_sheet: UploadFile = File(...)):
    if answer_sheet.content_type != "application/pdf":
        logger.warning("Rejected non-PDF answer sheet")
        raise HTTPException(415, "Upload a PDF answer sheet")
    path = UPLOADS / f"{uuid.uuid4()}.pdf"
    pdf_bytes = await answer_sheet.read()
    if not pdf_bytes.startswith(b"%PDF-"):
        logger.warning("Rejected malformed answer-sheet PDF")
        raise HTTPException(422, "The uploaded file is not a readable PDF")
    path.write_bytes(pdf_bytes)
    submission_id = str(uuid.uuid4())
    with closing(connect()) as db:
        if not db.execute("SELECT 1 FROM tests WHERE id=?", (test_id,)).fetchone():
            path.unlink(missing_ok=True)
            logger.warning("Could not save answer sheet: test not found")
            raise HTTPException(404, "Test not found")
        db.execute("INSERT INTO submissions(id,test_id,student_id,pdf_path) VALUES(?,?,?,?)", (submission_id, test_id, student_id, str(path)))
        db.commit()
    logger.info("Answer-sheet PDF received and stored for evaluation")
    return {"id": submission_id, "status": "submitted", "bytes": len(pdf_bytes)}


def get_ai_evaluation(prompt: str, pdf_path: str):
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("AI_API_KEY")
    if not api_key:
        logger.error("AI evaluation requested but no Gemini API key is configured")
        raise HTTPException(503, "Set GEMINI_API_KEY on the backend to enable evaluation")
    model = os.getenv("AI_MODEL", "gemini-2.5-flash")
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(model, safe='-_.')}:generateContent"
    with open(pdf_path, "rb") as pdf_file:
        pdf_data = base64.b64encode(pdf_file.read()).decode("ascii")
    request_body = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": "Evaluate this student's answer-sheet PDF using the supplied questions, rubric, and learning profile. Inspect handwriting and page images, not just selectable text. Be fair, cite specific visible mistakes, and return only JSON with numeric score and max_score, feedback (an array of specific errors and improvement actions), and teacher_advice. Context: " + prompt},
                {"inlineData": {"mimeType": "application/pdf", "data": pdf_data}},
            ],
        }],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1},
    }
    request = urllib.request.Request(endpoint, data=json.dumps(request_body).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": api_key}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read())
        content = "".join(part.get("text", "") for part in payload["candidates"][0]["content"]["parts"])
        result = json.loads(content)
        if not isinstance(result.get("score"), (int, float)) or not isinstance(result.get("max_score"), (int, float)):
            raise ValueError("AI response is missing numeric score fields")
        return result
    except urllib.error.HTTPError as error:
        logger.error("Gemini evaluation failed with HTTP status %s", error.code)
        raise HTTPException(502, "Gemini request failed; check backend logs and model/key configuration") from error
    except (urllib.error.URLError, TimeoutError) as error:
        logger.error("Gemini connection failed (%s)", type(error).__name__)
        raise HTTPException(502, "Could not connect to Gemini; check backend logs and network access") from error
    except (KeyError, ValueError, json.JSONDecodeError) as error:
        logger.error("Gemini returned an unusable evaluation (%s)", type(error).__name__)
        raise HTTPException(502, "Gemini returned an unusable evaluation; check backend logs") from error
    except OSError as error:
        logger.error("Could not read stored answer-sheet PDF (%s)", type(error).__name__)
        raise HTTPException(500, "Stored answer-sheet PDF could not be read; check backend logs") from error


@app.post("/api/submissions/{submission_id}/evaluate")
def evaluate_submission(submission_id: str):
    with closing(connect()) as db:
        row = db.execute("""SELECT s.*,t.title,t.subject FROM submissions s JOIN tests t ON t.id=s.test_id WHERE s.id=?""", (submission_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Submission not found")
        questions = [dict(item) for item in db.execute("SELECT prompt,points FROM questions WHERE test_id=?", (row["test_id"],))]
        criteria = [dict(item) for item in db.execute("SELECT name,weight,guidance FROM criteria WHERE test_id=?", (row["test_id"],))]
        profile_row = db.execute("SELECT context_json FROM profiles WHERE student_id=?", (row["student_id"],)).fetchone()
        context = profile_row["context_json"] if profile_row else "{}"
        result = get_ai_evaluation(json.dumps({"test": row["title"], "subject": row["subject"], "questions": questions, "rubric": criteria, "student_profile": context}), row["pdf_path"])
        evaluation_id = str(uuid.uuid4())
        db.execute("INSERT OR REPLACE INTO evaluations(id,submission_id,score,max_score,feedback_json,teacher_advice) VALUES(?,?,?,?,?,?)", (evaluation_id, submission_id, result["score"], result["max_score"], json.dumps(result.get("feedback", [])), result.get("teacher_advice", "")))
        db.execute("UPDATE submissions SET status='evaluated' WHERE id=?", (submission_id,))
        history = json.loads(context)
        history.setdefault("assessment_history", []).append({"test": row["title"], "score": result["score"], "max_score": result["max_score"], "feedback": result.get("feedback", [])})
        db.execute("INSERT INTO profiles(student_id,context_json) VALUES(?,?) ON CONFLICT(student_id) DO UPDATE SET context_json=excluded.context_json", (row["student_id"], json.dumps(history)))
        db.commit()
    logger.info("AI evaluation completed successfully")
    return {"id": evaluation_id, **result}


@app.get("/api/students/{student_id}/profile")
def student_profile(student_id: str):
    with closing(connect()) as db:
        profile = db.execute("SELECT context_json FROM profiles WHERE student_id=?", (student_id,)).fetchone()
        if not profile:
            raise HTTPException(404, "Student profile not found")
        evaluations = [dict(row) for row in db.execute("""SELECT e.score,e.max_score,e.feedback_json,e.teacher_advice,e.created_at,t.title,t.subject FROM evaluations e JOIN submissions s ON e.submission_id=s.id JOIN tests t ON s.test_id=t.id WHERE s.student_id=? ORDER BY e.created_at DESC""", (student_id,))]
        return {"profile": json.loads(profile["context_json"]), "evaluations": evaluations}


@app.get("/api/classes/{class_id}/students")
def class_students(class_id: str):
    with closing(connect()) as db:
        return [dict(row) for row in db.execute("SELECT u.id,u.name,u.email FROM users u JOIN enrollments e ON e.student_id=u.id WHERE e.class_id=?", (class_id,))]