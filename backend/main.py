import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import shutil
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import closing
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
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
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), expires_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS mock_tests(id TEXT PRIMARY KEY, class_id TEXT NOT NULL REFERENCES classes(id), title TEXT NOT NULL, subject TEXT NOT NULL, description TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS mock_questions(id TEXT PRIMARY KEY, test_id TEXT NOT NULL REFERENCES mock_tests(id), prompt TEXT NOT NULL, options_json TEXT NOT NULL, correct_index INTEGER NOT NULL, explanation TEXT NOT NULL, topic TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS mock_attempts(id TEXT PRIMARY KEY, test_id TEXT NOT NULL REFERENCES mock_tests(id), student_id TEXT NOT NULL REFERENCES users(id), answers_json TEXT NOT NULL, score REAL NOT NULL, max_score REAL NOT NULL, submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS mock_advice(student_id TEXT NOT NULL REFERENCES users(id), test_id TEXT NOT NULL REFERENCES mock_tests(id), attempt_id TEXT NOT NULL REFERENCES mock_attempts(id), advice_json TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(student_id,test_id));
        CREATE TABLE IF NOT EXISTS deleted_demo_tests(test_id TEXT PRIMARY KEY);
        """)
        user_columns = {row["name"] for row in db.execute("PRAGMA table_info(users)")}
        for column, declaration in (("username", "TEXT"), ("password_salt", "TEXT"), ("password_hash", "TEXT")):
            if column not in user_columns:
                db.execute(f"ALTER TABLE users ADD COLUMN {column} {declaration}")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        db.commit()


initialize()
logger.info("Smartclass database initialized")


DEMO_PASSWORD = ""
CLASS_ID = "class9-algebra"


def password_digest(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 180_000).hex()


def seed_demo_data():
    accounts = (("naruto", "Naruto", "student"), ("sasuke", "Sasuke", "student"), ("kakashi", "Kakashi", "teacher"))
    with closing(connect()) as db:
        for username, name, role in accounts:
            salt = hashlib.sha256(f"smartclass:{username}".encode()).hexdigest()[:32]
            db.execute("""INSERT INTO users(id,name,email,role,username,password_salt,password_hash)
                VALUES(?,?,NULL,?,?,?,?) ON CONFLICT(username) DO UPDATE SET
                name=excluded.name, role=excluded.role, password_salt=excluded.password_salt,
                password_hash=excluded.password_hash""", (username, name, role, username, salt, password_digest(DEMO_PASSWORD, salt)))
            db.execute("INSERT OR IGNORE INTO profiles(student_id,context_json) VALUES(?,?)", (username, json.dumps({"name": name, "class": "Class 9 - Algebra", "strengths": [], "focus_areas": [], "assessment_history": []})))
        db.execute("INSERT OR IGNORE INTO classes(id,name,year,teacher_id) VALUES(?,?,?,?)", (CLASS_ID, "Class 9 - Algebra", "2026 / 27", "kakashi"))
        for student_id in ("naruto", "sasuke"):
            db.execute("INSERT OR IGNORE INTO enrollments(class_id,student_id) VALUES(?,?)", (CLASS_ID, student_id))
        papers = (
            ("demo-linear-equations", "Linear Equations Check-in", "Mathematics", "Lecture test", "Fri, 17 Oct", "linear_equations.pdf", "linear_equations_key.pdf"),
            ("demo-polynomials", "Polynomials and Factorisation", "Mathematics", "Cumulative", "Mon, 20 Oct", "polynomials.pdf", "polynomials_key.pdf"),
        )
        for test_id, title, subject, kind, due_date, paper_name, key_name in papers:
            if db.execute("SELECT 1 FROM deleted_demo_tests WHERE test_id=?", (test_id,)).fetchone():
                continue
            source_paper = ROOT / "demo_papers" / paper_name
            source_key = ROOT / "demo_papers" / key_name
            if not source_paper.is_file() or not source_key.is_file():
                raise RuntimeError("Demo PDFs are missing; run python generate_demo_pdfs.py in backend/")
            paper_path = UPLOADS / f"seed-{test_id}-paper.pdf"
            key_path = UPLOADS / f"seed-{test_id}-answer-key.pdf"
            if not paper_path.exists():
                shutil.copyfile(source_paper, paper_path)
            if not key_path.exists():
                shutil.copyfile(source_key, key_path)
            db.execute("""INSERT OR IGNORE INTO tests(id,class_id,title,subject,kind,due_date,paper_path)
                VALUES(?,?,?,?,?,?,?)""", (test_id, CLASS_ID, title, subject, kind, due_date, str(paper_path)))
            db.execute("""CREATE TABLE IF NOT EXISTS answer_keys(test_id TEXT PRIMARY KEY REFERENCES tests(id), pdf_path TEXT NOT NULL)""")
            db.execute("INSERT OR IGNORE INTO answer_keys(test_id,pdf_path) VALUES(?,?)", (test_id, str(key_path)))
            current_paper = db.execute("SELECT paper_path FROM tests WHERE id=?", (test_id,)).fetchone()
            source_directory = (ROOT / "demo_papers").resolve()
            if current_paper and current_paper["paper_path"] and Path(current_paper["paper_path"]).resolve().parent == source_directory:
                db.execute("UPDATE tests SET paper_path=? WHERE id=?", (str(paper_path), test_id))
            current_key = db.execute("SELECT pdf_path FROM answer_keys WHERE test_id=?", (test_id,)).fetchone()
            if current_key and Path(current_key["pdf_path"]).resolve().parent == source_directory:
                db.execute("UPDATE answer_keys SET pdf_path=? WHERE test_id=?", (str(key_path), test_id))
            db.execute("INSERT OR IGNORE INTO criteria(id,test_id,name,weight,guidance) VALUES(?,?,?,?,?)", (f"{test_id}-criteria", test_id, "Method and accuracy", 1.0, "Award partial credit for correct working; explain arithmetic and algebra errors."))
            for question_number in range(1, 11):
                db.execute("INSERT OR IGNORE INTO questions(id,test_id,prompt,points) VALUES(?,?,?,?)", (f"{test_id}-q{question_number}", test_id, f"Question {question_number} from the attached test paper", 2))
        mock_test_id = "mock-class9-algebra"
        db.execute("INSERT OR IGNORE INTO mock_tests(id,class_id,title,subject,description) VALUES(?,?,?,?,?)", (mock_test_id, CLASS_ID, "Algebra Quick Check", "Mathematics", "Ten multiple-choice questions. Take it any time and retake it to practise."))
        mock_questions = (
            ("Solve: 2x + 3 = 13.", ["x = 3", "x = 4", "x = 5", "x = 6"], 2, "Subtract 3 to get 2x = 10, then divide by 2.", "Linear equations"),
            ("Solve: 4y = 28.", ["y = 6", "y = 7", "y = 8", "y = 9"], 1, "Divide both sides by 4.", "Inverse operations"),
            ("Simplify: 5x - 2x + 7.", ["7x + 7", "3x - 7", "3x + 7", "3x + 5"], 2, "Combine like terms: 5x - 2x = 3x.", "Collecting like terms"),
            ("Expand: 3(a + 4).", ["3a + 4", "3a + 12", "a + 12", "7a"], 1, "Multiply both terms inside the brackets by 3.", "Expansion"),
            ("Factorise: x^2 + 5x + 6.", ["(x + 2)(x + 3)", "(x + 1)(x + 6)", "(x - 2)(x - 3)", "x(x + 5) + 6"], 0, "Find two numbers with product 6 and sum 5: 2 and 3.", "Factorisation"),
            ("Solve: 3x - 4 = 11.", ["x = 3", "x = 4", "x = 5", "x = 7"], 2, "Add 4 to get 3x = 15, then divide by 3.", "Linear equations"),
            ("Evaluate 2a^2 when a = -3.", ["-18", "-6", "6", "18"], 3, "Square first: (-3)^2 = 9, then multiply by 2.", "Substitution"),
            ("A rectangle has width x and length x + 2. Its perimeter is 20. What is its width?", ["3", "4", "5", "6"], 1, "2x + 2(x + 2) = 20, so 4x = 16 and x = 4.", "Forming equations"),
            ("Solve: 2(x + 3) = 18.", ["x = 3", "x = 6", "x = 9", "x = 12"], 1, "Divide by 2 to get x + 3 = 9, then subtract 3.", "Brackets and equations"),
            ("Expand: 5(2x - 1).", ["10x - 1", "7x - 5", "10x - 5", "10x + 5"], 2, "Multiply both 2x and -1 by 5.", "Expansion"),
        )
        for question_number, (prompt, options, correct_index, explanation, topic) in enumerate(mock_questions, start=1):
            db.execute("INSERT OR IGNORE INTO mock_questions(id,test_id,prompt,options_json,correct_index,explanation,topic) VALUES(?,?,?,?,?,?,?)", (f"{mock_test_id}-q{question_number}", mock_test_id, prompt, json.dumps(options), correct_index, explanation, topic))
        db.commit()


seed_demo_data()
logger.info("Demo users, Class 9, and algebra tests are ready")


class Login(BaseModel):
    username: str
    password: str


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


class TestUpdate(BaseModel):
    title: str | None = None
    subject: str | None = None
    kind: str | None = None
    due_date: str | None = None


class MockAttemptInput(BaseModel):
    answers: dict[str, int]


class QuestionInput(BaseModel):
    prompt: str
    points: float = 1


class CriteriaInput(BaseModel):
    name: str
    weight: float
    guidance: str = ""


def test_payload(row):
    return {"id": row["id"], "class_id": row["class_id"], "title": row["title"], "subject": row["subject"], "kind": row["kind"], "due_date": row["due_date"], "question_count": row["question_count"], "has_paper": bool(row["paper_path"])}


def configured_provider() -> str:
    provider = os.getenv("AI_PROVIDER", "auto").strip().lower()
    if provider != "auto":
        return provider
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return "gemini"


def model_for_provider(provider: str) -> str:
    if provider == "openai":
        return os.getenv("OPENAI_MODEL") or (os.getenv("AI_MODEL") if os.getenv("AI_MODEL", "").startswith(("gpt-", "o")) else None) or "gpt-4.1-mini"
    return os.getenv("GEMINI_MODEL") or (os.getenv("AI_MODEL") if os.getenv("AI_MODEL", "").startswith("gemini-") else None) or "gemini-3.8-flash"


@app.get("/api/health")
def health():
    provider = configured_provider()
    if provider == "openai":
        api_configured = bool(os.getenv("OPENAI_API_KEY") or os.getenv("AI_API_KEY"))
    elif provider == "gemini":
        api_configured = bool(os.getenv("GEMINI_API_KEY") or os.getenv("AI_API_KEY"))
    else:
        api_configured = False
    return {"status": "ok", "ai_configured": api_configured, "provider": provider, "model": model_for_provider(provider)}


@app.post("/api/login")
def login(data: Login):
    with closing(connect()) as db:
        row = db.execute("SELECT id,name,username,role,password_salt,password_hash FROM users WHERE username=?", (data.username.strip().lower(),)).fetchone()
        if not row or not hmac.compare_digest(password_digest(data.password, row["password_salt"]), row["password_hash"]):
            logger.warning("Rejected login attempt")
            raise HTTPException(401, "Incorrect username or password")
        token = secrets.token_urlsafe(32)
        db.execute("INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), row["id"], time.time() + 60 * 60 * 24 * 14))
        db.commit()
        logger.info("User authenticated")
        return {"access_token": token, "user": {"id": row["id"], "name": row["name"], "username": row["username"], "role": row["role"]}, "class": {"id": CLASS_ID, "name": "Class 9 - Algebra", "year": "2026 / 27"}}


def authenticated_user(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sign in to continue")
    token_hash = hashlib.sha256(authorization[7:].encode()).hexdigest()
    with closing(connect()) as db:
        row = db.execute("""SELECT u.id,u.name,u.username,u.role FROM sessions s JOIN users u ON u.id=s.user_id
            WHERE s.token_hash=? AND s.expires_at>?""", (token_hash, time.time())).fetchone()
        if not row:
            raise HTTPException(401, "Session expired. Please sign in again.")
        return dict(row)


def require_class_access(class_id: str, user: dict, teacher_only: bool = False):
    with closing(connect()) as db:
        if user["role"] == "teacher":
            row = db.execute("SELECT 1 FROM classes WHERE id=? AND teacher_id=?", (class_id, user["id"])).fetchone()
        else:
            row = db.execute("SELECT 1 FROM enrollments WHERE class_id=? AND student_id=?", (class_id, user["id"])).fetchone()
    if not row or (teacher_only and user["role"] != "teacher"):
        raise HTTPException(403, "You do not have access to this class")


@app.post("/api/classes")
def create_class(name: str = Form(...), year: str = Form(...), teacher_id: str = Form(...), user: dict = Depends(authenticated_user)):
    if user["role"] != "teacher" or user["id"] != teacher_id:
        raise HTTPException(403, "Only the signed-in teacher can create a class")
    class_id = str(uuid.uuid4())
    with closing(connect()) as db:
        db.execute("INSERT INTO classes VALUES(?,?,?,?)", (class_id, name, year, teacher_id))
        db.commit()
    return {"id": class_id, "name": name, "year": year}


@app.post("/api/classes/{class_id}/plans")
def add_plan(class_id: str, data: PlanInput, user: dict = Depends(authenticated_user)):
    require_class_access(class_id, user, teacher_only=True)
    plan_id = str(uuid.uuid4())
    with closing(connect()) as db:
        db.execute("INSERT INTO plans VALUES(?,?,?,?,?)", (plan_id, class_id, data.week, data.title, data.target))
        db.commit()
    return {"id": plan_id, **data.model_dump()}


@app.get("/api/classes/{class_id}/plans")
def list_plans(class_id: str, user: dict = Depends(authenticated_user)):
    require_class_access(class_id, user)
    with closing(connect()) as db:
        return [dict(row) for row in db.execute("SELECT * FROM plans WHERE class_id=? ORDER BY week", (class_id,))]


@app.get("/api/classes/{class_id}/tests")
def list_tests(class_id: str, user: dict = Depends(authenticated_user)):
    require_class_access(class_id, user)
    with closing(connect()) as db:
        published_filter = "AND t.paper_path IS NOT NULL" if user["role"] == "student" else ""
        rows = db.execute("""SELECT t.*,COUNT(q.id) AS question_count FROM tests t LEFT JOIN questions q ON q.test_id=t.id
            WHERE t.class_id=? """ + published_filter + " GROUP BY t.id ORDER BY t.due_date,t.title", (class_id,)).fetchall()
        return [test_payload(row) for row in rows]


@app.post("/api/tests")
def create_test(data: TestInput, user: dict = Depends(authenticated_user)):
    require_class_access(data.class_id, user, teacher_only=True)
    test_id = str(uuid.uuid4())
    with closing(connect()) as db:
        db.execute("INSERT INTO tests(id,class_id,title,subject,kind,due_date) VALUES(?,?,?,?,?,?)", (test_id, data.class_id, data.title, data.subject, data.kind, data.due_date))
        db.commit()
    return {"id": test_id, **data.model_dump()}


@app.patch("/api/tests/{test_id}")
def update_test(test_id: str, data: TestUpdate, user: dict = Depends(authenticated_user)):
    values = data.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(400, "Provide at least one test field to update")
    allowed_fields = {"title", "subject", "kind", "due_date"}
    if any(field not in allowed_fields for field in values):
        raise HTTPException(400, "Unsupported test field")
    with closing(connect()) as db:
        row = db.execute("SELECT class_id FROM tests WHERE id=?", (test_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Test not found")
        require_class_access(row["class_id"], user, teacher_only=True)
        assignments = ",".join(f"{field}=?" for field in values)
        db.execute(f"UPDATE tests SET {assignments} WHERE id=?", (*values.values(), test_id))
        db.commit()
        updated = db.execute("""SELECT t.*,COUNT(q.id) AS question_count FROM tests t
            LEFT JOIN questions q ON q.test_id=t.id WHERE t.id=? GROUP BY t.id""", (test_id,)).fetchone()
    logger.info("Teacher updated class test")
    return test_payload(updated)


@app.delete("/api/tests/{test_id}")
def delete_test(test_id: str, user: dict = Depends(authenticated_user)):
    with closing(connect()) as db:
        test = db.execute("SELECT class_id,paper_path FROM tests WHERE id=?", (test_id,)).fetchone()
        if not test:
            raise HTTPException(404, "Test not found")
        require_class_access(test["class_id"], user, teacher_only=True)
        files = [test["paper_path"]] if test["paper_path"] else []
        answer_key = db.execute("SELECT pdf_path FROM answer_keys WHERE test_id=?", (test_id,)).fetchone()
        if answer_key:
            files.append(answer_key["pdf_path"])
        files.extend(row["pdf_path"] for row in db.execute("SELECT pdf_path FROM submissions WHERE test_id=?", (test_id,)))
        if test_id in {"demo-linear-equations", "demo-polynomials"}:
            db.execute("INSERT OR IGNORE INTO deleted_demo_tests(test_id) VALUES(?)", (test_id,))
        db.execute("DELETE FROM evaluations WHERE submission_id IN (SELECT id FROM submissions WHERE test_id=?)", (test_id,))
        db.execute("DELETE FROM submissions WHERE test_id=?", (test_id,))
        db.execute("DELETE FROM questions WHERE test_id=?", (test_id,))
        db.execute("DELETE FROM criteria WHERE test_id=?", (test_id,))
        db.execute("DELETE FROM answer_keys WHERE test_id=?", (test_id,))
        db.execute("DELETE FROM tests WHERE id=?", (test_id,))
        db.commit()
    for filename in files:
        if filename:
            Path(filename).unlink(missing_ok=True)
    logger.info("Teacher deleted class test and related PDFs")
    return {"deleted": True, "test_id": test_id}


@app.get("/api/classes/{class_id}/mock-tests")
def list_mock_tests(class_id: str, user: dict = Depends(authenticated_user)):
    require_class_access(class_id, user)
    with closing(connect()) as db:
        rows = db.execute("""SELECT m.*,COUNT(q.id) AS question_count FROM mock_tests m
            LEFT JOIN mock_questions q ON q.test_id=m.id WHERE m.class_id=? GROUP BY m.id ORDER BY m.title""", (class_id,)).fetchall()
        return [{"id": row["id"], "class_id": row["class_id"], "title": row["title"], "subject": row["subject"], "description": row["description"], "question_count": row["question_count"]} for row in rows]


@app.get("/api/mock-tests/{test_id}/questions")
def mock_test_questions(test_id: str, user: dict = Depends(authenticated_user)):
    with closing(connect()) as db:
        test = db.execute("SELECT class_id FROM mock_tests WHERE id=?", (test_id,)).fetchone()
        if not test:
            raise HTTPException(404, "Mock test not found")
        require_class_access(test["class_id"], user)
        rows = db.execute("SELECT id,prompt,options_json FROM mock_questions WHERE test_id=? ORDER BY rowid", (test_id,)).fetchall()
        return [{"id": row["id"], "prompt": row["prompt"], "options": json.loads(row["options_json"])} for row in rows]


@app.get("/api/mock-tests/{test_id}/my-latest-attempt")
def latest_mock_attempt(test_id: str, user: dict = Depends(authenticated_user)):
    if user["role"] != "student":
        raise HTTPException(403, "Student account required")
    with closing(connect()) as db:
        test = db.execute("SELECT class_id FROM mock_tests WHERE id=?", (test_id,)).fetchone()
        if not test:
            raise HTTPException(404, "Mock test not found")
        require_class_access(test["class_id"], user)
        row = db.execute("""SELECT a.*,COUNT(q.id) AS total_questions,d.advice_json FROM mock_attempts a
            LEFT JOIN mock_questions q ON q.test_id=a.test_id
            LEFT JOIN mock_advice d ON d.student_id=a.student_id AND d.test_id=a.test_id AND d.attempt_id=a.id
            WHERE a.test_id=? AND a.student_id=? GROUP BY a.id ORDER BY a.rowid DESC LIMIT 1""", (test_id, user["id"])).fetchone()
        if not row:
            return {"attempt": None}
        return {"attempt": {"id": row["id"], "test_id": row["test_id"], "score": row["score"], "max_score": row["max_score"], "total_questions": row["total_questions"], "answers": json.loads(row["answers_json"]), "submitted_at": row["submitted_at"], "last_advice": json.loads(row["advice_json"]) if row["advice_json"] else None}}


@app.post("/api/mock-tests/{test_id}/attempts")
def submit_mock_attempt(test_id: str, data: MockAttemptInput, user: dict = Depends(authenticated_user)):
    if user["role"] != "student":
        raise HTTPException(403, "Only students can take the mock test")
    with closing(connect()) as db:
        test = db.execute("SELECT class_id,title,subject FROM mock_tests WHERE id=?", (test_id,)).fetchone()
        if not test:
            raise HTTPException(404, "Mock test not found")
        require_class_access(test["class_id"], user)
        questions = db.execute("SELECT id,correct_index,topic FROM mock_questions WHERE test_id=? ORDER BY rowid", (test_id,)).fetchall()
        if not questions:
            raise HTTPException(409, "This mock test has no questions")
        expected_ids = {question["id"] for question in questions}
        if set(data.answers) != expected_ids:
            raise HTTPException(422, "Answer every question before submitting")
        for question in questions:
            selected = data.answers[question["id"]]
            option_count = db.execute("SELECT json_array_length(options_json) FROM mock_questions WHERE id=?", (question["id"],)).fetchone()[0]
            if selected < 0 or selected >= option_count:
                raise HTTPException(422, "An answer choice is invalid")
        score = sum(data.answers[question["id"]] == question["correct_index"] for question in questions)
        attempt_id = str(uuid.uuid4())
        db.execute("INSERT INTO mock_attempts(id,test_id,student_id,answers_json,score,max_score) VALUES(?,?,?,?,?,?)", (attempt_id, test_id, user["id"], json.dumps(data.answers), score, len(questions)))
        db.execute("DELETE FROM mock_advice WHERE student_id=? AND test_id=?", (user["id"], test_id))
        profile = db.execute("SELECT context_json FROM profiles WHERE student_id=?", (user["id"],)).fetchone()
        if profile:
            context = json.loads(profile["context_json"])
            context.setdefault("assessment_history", []).append({"test": test["title"], "source": "mock", "score": score, "max_score": len(questions), "focus_areas": [question["topic"] for question in questions if data.answers[question["id"]] != question["correct_index"]]})
            db.execute("UPDATE profiles SET context_json=? WHERE student_id=?", (json.dumps(context), user["id"]))
        attempts = db.execute("SELECT COUNT(*) FROM mock_attempts WHERE test_id=? AND student_id=?", (test_id, user["id"])).fetchone()[0]
        db.commit()
    logger.info("Student submitted mock algebra test")
    return {"id": attempt_id, "test_id": test_id, "score": score, "max_score": len(questions), "correct_count": score, "total_questions": len(questions), "attempt_number": attempts}


@app.post("/api/tests/{test_id}/paper")
async def upload_test_paper(test_id: str, paper: UploadFile = File(...), user: dict = Depends(authenticated_user)):
    if paper.content_type != "application/pdf":
        logger.warning("Rejected non-PDF test paper")
        raise HTTPException(415, "Upload a PDF")
    with closing(connect()) as db:
        test = db.execute("SELECT class_id,paper_path FROM tests WHERE id=?", (test_id,)).fetchone()
    if not test:
        raise HTTPException(404, "Test not found")
    require_class_access(test["class_id"], user, teacher_only=True)
    pdf_bytes = await paper.read(50 * 1024 * 1024 + 1)
    if len(pdf_bytes) > 50 * 1024 * 1024:
        raise HTTPException(413, "PDF exceeds the 50 MB limit")
    if not pdf_bytes.startswith(b"%PDF-"):
        logger.warning("Rejected malformed test paper")
        raise HTTPException(422, "The uploaded file is not a readable PDF")
    path = UPLOADS / f"{uuid.uuid4()}.pdf"
    path.write_bytes(pdf_bytes)
    with closing(connect()) as db:
        updated = db.execute("UPDATE tests SET paper_path=? WHERE id=?", (str(path), test_id)).rowcount
        db.commit()
    if not updated:
        path.unlink(missing_ok=True)
        logger.warning("Could not attach test paper: test not found")
        raise HTTPException(404, "Test not found")
    old_path = Path(test["paper_path"]) if test["paper_path"] else None
    if old_path and old_path != path and old_path.resolve().is_relative_to(UPLOADS.resolve()):
        old_path.unlink(missing_ok=True)
    logger.info("Test paper uploaded")
    return {"test_id": test_id, "paper": paper.filename, "stored": True}


@app.get("/api/tests/{test_id}/paper")
def download_test_paper(test_id: str, user: dict = Depends(authenticated_user)):
    with closing(connect()) as db:
        row = db.execute("SELECT class_id,title,paper_path FROM tests WHERE id=?", (test_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Test not found")
    require_class_access(row["class_id"], user)
    if not row["paper_path"] or not Path(row["paper_path"]).is_file():
        raise HTTPException(404, "Question paper is not available")
    return FileResponse(row["paper_path"], media_type="application/pdf", filename=f"{row['title']}-question-paper.pdf")


@app.post("/api/tests/{test_id}/questions")
def add_question(test_id: str, data: QuestionInput, user: dict = Depends(authenticated_user)):
    question_id = str(uuid.uuid4())
    with closing(connect()) as db:
        test = db.execute("SELECT class_id FROM tests WHERE id=?", (test_id,)).fetchone()
        if not test:
            raise HTTPException(404, "Test not found")
        require_class_access(test["class_id"], user, teacher_only=True)
        db.execute("INSERT INTO questions VALUES(?,?,?,?)", (question_id, test_id, data.prompt, data.points))
        db.commit()
    return {"id": question_id, "test_id": test_id, **data.model_dump()}


@app.post("/api/tests/{test_id}/criteria")
def add_criteria(test_id: str, data: CriteriaInput, user: dict = Depends(authenticated_user)):
    criteria_id = str(uuid.uuid4())
    with closing(connect()) as db:
        test = db.execute("SELECT class_id FROM tests WHERE id=?", (test_id,)).fetchone()
        if not test:
            raise HTTPException(404, "Test not found")
        require_class_access(test["class_id"], user, teacher_only=True)
        db.execute("INSERT INTO criteria VALUES(?,?,?,?,?)", (criteria_id, test_id, data.name, data.weight, data.guidance))
        db.commit()
    return {"id": criteria_id, "test_id": test_id, **data.model_dump()}


@app.post("/api/tests/{test_id}/submissions")
async def submit_answers(test_id: str, answer_sheet: UploadFile = File(...), user: dict = Depends(authenticated_user)):
    if user["role"] != "student":
        raise HTTPException(403, "Only students can submit answer sheets")
    if answer_sheet.content_type != "application/pdf":
        logger.warning("Rejected non-PDF answer sheet")
        raise HTTPException(415, "Upload a PDF answer sheet")
    with closing(connect()) as db:
        test = db.execute("SELECT class_id FROM tests WHERE id=?", (test_id,)).fetchone()
    if not test:
        raise HTTPException(404, "Test not found")
    require_class_access(test["class_id"], user)
    pdf_bytes = await answer_sheet.read(50 * 1024 * 1024 + 1)
    if len(pdf_bytes) > 50 * 1024 * 1024:
        raise HTTPException(413, "PDF exceeds the 50 MB limit")
    if not pdf_bytes.startswith(b"%PDF-"):
        logger.warning("Rejected malformed answer-sheet PDF")
        raise HTTPException(422, "The uploaded file is not a readable PDF")
    path = UPLOADS / f"{uuid.uuid4()}.pdf"
    path.write_bytes(pdf_bytes)
    submission_id = str(uuid.uuid4())
    with closing(connect()) as db:
        try:
            db.execute("INSERT INTO submissions(id,test_id,student_id,pdf_path) VALUES(?,?,?,?)", (submission_id, test_id, user["id"], str(path)))
        except sqlite3.IntegrityError as error:
            path.unlink(missing_ok=True)
            raise HTTPException(409, "You already submitted work for this test") from error
        db.commit()
    logger.info("Answer-sheet PDF received and stored for evaluation")
    return {"id": submission_id, "test_id": test_id, "status": "submitted", "bytes": len(pdf_bytes)}


@app.get("/api/classes/{class_id}/submissions")
def list_class_submissions(class_id: str, user: dict = Depends(authenticated_user)):
    require_class_access(class_id, user, teacher_only=True)
    with closing(connect()) as db:
        rows = db.execute("""SELECT s.id,s.test_id,s.student_id,s.status,t.title,u.name AS student_name,
            e.score,e.max_score,e.feedback_json,e.teacher_advice FROM submissions s
            JOIN tests t ON t.id=s.test_id JOIN users u ON u.id=s.student_id
            LEFT JOIN evaluations e ON e.submission_id=s.id WHERE t.class_id=? ORDER BY s.rowid DESC""", (class_id,)).fetchall()
        return [{**dict(row), "feedback": json.loads(row["feedback_json"]) if row["feedback_json"] else None} for row in rows]


@app.get("/api/students/me/submissions")
def list_my_submissions(user: dict = Depends(authenticated_user)):
    if user["role"] != "student":
        raise HTTPException(403, "Student account required")
    with closing(connect()) as db:
        rows = db.execute("""SELECT s.id,s.test_id,s.status,t.title,t.subject,
            e.score,e.max_score,e.feedback_json,e.teacher_advice FROM submissions s JOIN tests t ON t.id=s.test_id
            LEFT JOIN evaluations e ON e.submission_id=s.id WHERE s.student_id=? ORDER BY s.rowid DESC""", (user["id"],)).fetchall()
        return [{**dict(row), "feedback": json.loads(row["feedback_json"]) if row["feedback_json"] else None} for row in rows]


@app.get("/api/submissions/{submission_id}/answer")
def download_answer_sheet(submission_id: str, user: dict = Depends(authenticated_user)):
    with closing(connect()) as db:
        row = db.execute("""SELECT s.pdf_path,s.student_id,t.class_id FROM submissions s JOIN tests t ON t.id=s.test_id WHERE s.id=?""", (submission_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Submission not found")
    if user["role"] == "student" and user["id"] != row["student_id"]:
        raise HTTPException(403, "You can only view your own answer sheet")
    if user["role"] == "teacher":
        require_class_access(row["class_id"], user, teacher_only=True)
    if not Path(row["pdf_path"]).is_file():
        raise HTTPException(404, "Answer-sheet file not found")
    return FileResponse(row["pdf_path"], media_type="application/pdf", filename="answer-sheet.pdf")


def get_openai_evaluation(prompt: str, answer_pdf_path: str, question_pdf_path: str, answer_key_path: str | None, api_key: str):
    files = [("Teacher question paper", question_pdf_path)]
    if answer_key_path and Path(answer_key_path).is_file():
        files.append(("Teacher worked answer reference; use only to verify grading", answer_key_path))
    files.append(("Student answer sheet to evaluate", answer_pdf_path))
    parts = [{"type": "input_text", "text": "Grade the student's answer sheet against the teacher question paper. Use the rubric and student profile in the context. Inspect the PDF pages visually, including handwriting. Award partial credit fairly. Return a JSON object with numeric score and max_score, feedback as an array of specific mistakes and actionable improvements, and teacher_advice.\nContext: " + prompt}]
    total_pdf_bytes = 0
    for label, pdf_path in files:
        pdf_bytes = Path(pdf_path).read_bytes()
        total_pdf_bytes += len(pdf_bytes)
        parts.append({"type": "input_text", "text": label})
        parts.append({
            "type": "input_file",
            "filename": Path(pdf_path).name,
            "file_data": "data:application/pdf;base64," + base64.b64encode(pdf_bytes).decode("ascii"),
            "detail": "high",
        })
    if total_pdf_bytes > 50 * 1024 * 1024:
        raise HTTPException(413, "Combined test paper, answer key, and answer sheet exceed OpenAI's 50 MB request limit")
    model = model_for_provider("openai")
    request_body = {
        "model": model,
        "instructions": "You are a careful school mathematics marker. Treat the teacher's answer key as private grading reference, never as student work. Do not invent unreadable answers. Return only the requested JSON.",
        "input": [{"role": "user", "content": parts}],
        "text": {"format": {"type": "json_object"}},
        "temperature": 0.1,
        "store": False,
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(request_body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=150) as response:
            payload = json.loads(response.read())
        text_parts = [
            part["text"]
            for item in payload.get("output", []) if item.get("type") == "message"
            for part in item.get("content", []) if part.get("type") == "output_text" and part.get("text")
        ]
        content = "\n".join(text_parts) or payload.get("output_text", "")
        result = json.loads(content)
        if not isinstance(result.get("score"), (int, float)) or not isinstance(result.get("max_score"), (int, float)):
            raise ValueError("OpenAI response is missing numeric score fields")
        logger.info("OpenAI evaluation completed successfully using model %s", model)
        return result
    except urllib.error.HTTPError as error:
        try:
            provider_error = json.loads(error.read()).get("error", {})
            provider_code = provider_error.get("code") or provider_error.get("type") or "unknown"
            provider_message = provider_error.get("message", "No provider message")
        except (json.JSONDecodeError, AttributeError):
            provider_code = "unknown"
            provider_message = "Provider returned a non-JSON error"
        if api_key in provider_message:
            provider_message = provider_message.replace(api_key, "[redacted]")
        logger.error("OpenAI evaluation failed: HTTP %s, %s: %s", error.code, provider_code, provider_message)
        if error.code == 429:
            if provider_code in {"credit_balance_exhausted", "insufficient_quota"}:
                raise HTTPException(402, "OpenAI API account has no credits. Add API billing credits at platform.openai.com, then retry this saved submission.") from error
            raise HTTPException(429, "OpenAI API quota or rate limit reached. The submission is saved; check your API billing and usage, then retry.") from error
        if error.code == 401:
            raise HTTPException(503, "OpenAI rejected the configured API key. Check OPENAI_API_KEY in backend/.env and restart the backend.") from error
        if error.code >= 500:
            raise HTTPException(503, "OpenAI is temporarily unavailable. The submission is saved; retry the AI review later.") from error
        raise HTTPException(502, "OpenAI request failed. Check the backend logs for provider details.") from error
    except (urllib.error.URLError, TimeoutError) as error:
        logger.error("OpenAI connection failed (%s)", type(error).__name__)
        raise HTTPException(502, "Could not connect to OpenAI; check backend logs and network access") from error
    except (KeyError, ValueError, json.JSONDecodeError) as error:
        logger.error("OpenAI returned an unusable evaluation (%s)", type(error).__name__)
        raise HTTPException(502, "OpenAI returned an unusable evaluation; check backend logs") from error
    except OSError as error:
        logger.error("Could not read evaluation PDF (%s)", type(error).__name__)
        raise HTTPException(500, "An evaluation PDF could not be read; check backend logs") from error


def get_ai_evaluation(prompt: str, answer_pdf_path: str, question_pdf_path: str, answer_key_path: str | None = None):
    requested_provider = os.getenv("AI_PROVIDER", "auto").strip().lower()
    if requested_provider not in {"auto", "openai", "gemini"}:
        raise HTTPException(500, "AI_PROVIDER must be auto, openai, or gemini")
    if requested_provider == "auto":
        providers = [provider for provider, key in (("gemini", os.getenv("GEMINI_API_KEY")), ("openai", os.getenv("OPENAI_API_KEY"))) if key]
    else:
        providers = [requested_provider]
    if not providers:
        raise HTTPException(503, "Configure GEMINI_API_KEY or OPENAI_API_KEY in backend/.env")
    failures = []
    for provider in providers:
        try:
            if provider == "openai":
                api_key = os.getenv("OPENAI_API_KEY") or (os.getenv("AI_API_KEY") if requested_provider == "openai" else None)
                if not api_key:
                    raise HTTPException(503, "Set OPENAI_API_KEY in the backend environment to enable evaluation")
                return get_openai_evaluation(prompt, answer_pdf_path, question_pdf_path, answer_key_path, api_key)
            api_key = os.getenv("GEMINI_API_KEY") or (os.getenv("AI_API_KEY") if requested_provider == "gemini" else None)
            if not api_key:
                raise HTTPException(503, "Set GEMINI_API_KEY on the backend to enable evaluation")
            return get_gemini_evaluation(prompt, answer_pdf_path, question_pdf_path, answer_key_path, api_key)
        except HTTPException as error:
            failures.append((provider, error))
            if provider != providers[-1] and error.status_code in {401, 402, 429, 500, 502, 503}:
                logger.warning("%s unavailable (HTTP %s); auto mode will try the next configured provider", provider, error.status_code)
                continue
            if requested_provider != "auto":
                raise
    if len(failures) == 1:
        raise failures[0][1]
    summary = "; ".join(f"{provider}: {error.detail}" for provider, error in failures)
    raise HTTPException(failures[-1][1].status_code, f"All configured AI providers failed. {summary}")


def get_gemini_evaluation(prompt: str, answer_pdf_path: str, question_pdf_path: str, answer_key_path: str | None, api_key: str):
    model = model_for_provider("gemini")
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(model, safe='-_.')}:generateContent"
    with open(question_pdf_path, "rb") as pdf_file:
        question_pdf_data = base64.b64encode(pdf_file.read()).decode("ascii")
    with open(answer_pdf_path, "rb") as pdf_file:
        answer_pdf_data = base64.b64encode(pdf_file.read()).decode("ascii")
    parts = [
        {"text": "Grade the student answer sheet against the attached teacher question paper. Use the supplied rubric and learning profile. Inspect handwriting and page images, not just selectable text. Be fair, award partial credit where appropriate, cite specific mistakes, and return only JSON with numeric score and max_score, feedback (an array of specific errors and improvement actions), and teacher_advice. Context: " + prompt},
        {"text": "Teacher question paper:"},
        {"inlineData": {"mimeType": "application/pdf", "data": question_pdf_data}},
    ]
    if answer_key_path and Path(answer_key_path).is_file():
        with open(answer_key_path, "rb") as pdf_file:
            answer_key_data = base64.b64encode(pdf_file.read()).decode("ascii")
        parts.extend([
            {"text": "Teacher's worked answer reference (use to check correctness; never treat it as student work):"},
            {"inlineData": {"mimeType": "application/pdf", "data": answer_key_data}},
        ])
    parts.extend([
        {"text": "Student answer sheet to evaluate:"},
        {"inlineData": {"mimeType": "application/pdf", "data": answer_pdf_data}},
    ])
    request_body = {
        "contents": [{"role": "user", "parts": parts}],
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
        try:
            provider_error = json.loads(error.read()).get("error", {})
            provider_status = provider_error.get("status", "unknown")
            provider_message = provider_error.get("message", "No provider message")
        except (json.JSONDecodeError, AttributeError):
            provider_status = "unknown"
            provider_message = "Provider returned a non-JSON error"
        if api_key in provider_message:
            provider_message = provider_message.replace(api_key, "[redacted]")
        logger.error("Gemini evaluation failed: HTTP %s, %s: %s", error.code, provider_status, provider_message)
        if error.code == 503:
            raise HTTPException(503, "Gemini is temporarily overloaded. Your submission is saved; retry the AI review in a little while.") from error
        if error.code == 429:
            raise HTTPException(429, "Gemini's rate limit or free-tier quota was reached. Your submission is saved; check AI Studio usage and retry later.") from error
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


def get_mock_advice(prompt: str):
    requested_provider = os.getenv("AI_PROVIDER", "auto").strip().lower()
    if requested_provider == "auto":
        providers = [provider for provider, key in (("gemini", os.getenv("GEMINI_API_KEY")), ("openai", os.getenv("OPENAI_API_KEY"))) if key]
    elif requested_provider in {"gemini", "openai"}:
        providers = [requested_provider]
    else:
        raise HTTPException(500, "AI_PROVIDER must be auto, openai, or gemini")
    if not providers:
        raise HTTPException(503, "Configure GEMINI_API_KEY or OPENAI_API_KEY to request mock-test advice")

    failures = []
    for provider in providers:
        api_key = os.getenv("GEMINI_API_KEY" if provider == "gemini" else "OPENAI_API_KEY")
        model = model_for_provider(provider)
        try:
            if provider == "openai":
                body = {
                    "model": model,
                    "instructions": "You are a supportive Class 9 algebra tutor. Use the student's answer pattern to give concise, specific, encouraging advice. Return JSON with one string field named advice.",
                    "input": prompt,
                    "text": {"format": {"type": "json_object"}},
                    "temperature": 0.2,
                    "store": False,
                }
                request = urllib.request.Request("https://api.openai.com/v1/responses", data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}, method="POST")
                with urllib.request.urlopen(request, timeout=90) as response:
                    payload = json.loads(response.read())
                text = "\n".join(part["text"] for item in payload.get("output", []) if item.get("type") == "message" for part in item.get("content", []) if part.get("type") == "output_text" and part.get("text"))
            else:
                body = {"contents": [{"role": "user", "parts": [{"text": "You are a supportive Class 9 algebra tutor. Use the student's answer pattern to give concise, specific, encouraging advice. Return JSON with one string field named advice. Context: " + prompt}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}}
                endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(model, safe='-_.')}:generateContent"
                request = urllib.request.Request(endpoint, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": api_key}, method="POST")
                with urllib.request.urlopen(request, timeout=90) as response:
                    payload = json.loads(response.read())
                text = "".join(part.get("text", "") for part in payload.get("candidates", [{}])[0].get("content", {}).get("parts", []))
            result = json.loads(text)
            advice = result.get("advice")
            if not isinstance(advice, str) or not advice.strip():
                raise ValueError("AI response did not include advice text")
            logger.info("Mock-test advice generated using %s model %s", provider, model)
            return {"provider": provider, "model": model, "advice": advice.strip()}
        except urllib.error.HTTPError as error:
            try:
                provider_error = json.loads(error.read()).get("error", {})
                provider_code = provider_error.get("code") or provider_error.get("status") or "unknown"
                provider_message = str(provider_error.get("message", "No provider message"))
            except (json.JSONDecodeError, AttributeError):
                provider_code, provider_message = "unknown", "Provider returned a non-JSON error"
            if api_key and api_key in provider_message:
                provider_message = provider_message.replace(api_key, "[redacted]")
            logger.error("%s mock advice failed: HTTP %s, %s: %s", provider, error.code, provider_code, provider_message)
            if error.code == 429 and provider_code in {"credit_balance_exhausted", "insufficient_quota"} and provider == "openai":
                failure = HTTPException(402, "OpenAI API account has no credits. Add API billing credits, then retry the advice.")
            elif error.code == 429:
                failure = HTTPException(429, f"{provider.title()} quota or rate limit reached; retry later.")
            elif error.code == 503 or error.code >= 500:
                failure = HTTPException(503, f"{provider.title()} is temporarily unavailable; retry the advice later.")
            elif error.code == 401:
                failure = HTTPException(503, f"{provider.title()} rejected its API key; check backend/.env and restart the server.")
            else:
                failure = HTTPException(502, f"{provider.title()} advice request failed; check backend logs.")
            failures.append((provider, failure))
            if requested_provider == "auto" and provider != providers[-1]:
                logger.warning("%s unavailable; auto mode will try the next provider", provider)
                continue
            raise failure from error
        except (urllib.error.URLError, TimeoutError) as error:
            logger.error("%s mock advice connection failed (%s)", provider, type(error).__name__)
            failure = HTTPException(502, f"Could not connect to {provider.title()}; check network access and retry.")
            failures.append((provider, failure))
            if requested_provider == "auto" and provider != providers[-1]:
                continue
            raise failure from error
        except (KeyError, ValueError, json.JSONDecodeError) as error:
            logger.error("%s returned unusable mock advice (%s)", provider, type(error).__name__)
            failure = HTTPException(502, f"{provider.title()} returned unusable advice; check backend logs.")
            failures.append((provider, failure))
            if requested_provider == "auto" and provider != providers[-1]:
                continue
            raise failure from error
    raise failures[-1][1]


@app.post("/api/mock-attempts/{attempt_id}/advice")
def view_mock_advice(attempt_id: str, user: dict = Depends(authenticated_user)):
    if user["role"] != "student":
        raise HTTPException(403, "Student account required")
    with closing(connect()) as db:
        attempt = db.execute("""SELECT a.*,m.title,m.subject,m.class_id FROM mock_attempts a
            JOIN mock_tests m ON m.id=a.test_id WHERE a.id=?""", (attempt_id,)).fetchone()
        if not attempt:
            raise HTTPException(404, "Mock test attempt not found")
        if attempt["student_id"] != user["id"]:
            raise HTTPException(403, "You can only view advice for your own attempt")
        questions = db.execute("SELECT prompt,options_json,correct_index,explanation,topic FROM mock_questions WHERE test_id=? ORDER BY rowid", (attempt["test_id"],)).fetchall()
        profile_row = db.execute("SELECT context_json FROM profiles WHERE student_id=?", (user["id"],)).fetchone()
        profile = json.loads(profile_row["context_json"]) if profile_row else {}
        answers = json.loads(attempt["answers_json"])
        response_pattern = []
        for question in questions:
            options = json.loads(question["options_json"])
            selected_index = answers[question["prompt"]] if question["prompt"] in answers else None
            response_pattern.append({
                "question": question["prompt"],
                "topic": question["topic"],
                "selected_answer": options[selected_index] if selected_index is not None else "No answer",
                "correct_answer": options[question["correct_index"]],
                "correct": selected_index == question["correct_index"],
                "explanation": question["explanation"],
            })
        prompt = json.dumps({
            "mock_test": attempt["title"],
            "subject": attempt["subject"],
            "score": attempt["score"],
            "max_score": attempt["max_score"],
            "answer_pattern": response_pattern,
            "previous_strengths": profile.get("strengths", []),
            "previous_focus_areas": profile.get("focus_areas", []),
        })
    advice = get_mock_advice(prompt)
    with closing(connect()) as db:
        db.execute("""INSERT INTO mock_advice(student_id,test_id,attempt_id,advice_json)
            VALUES(?,?,?,?) ON CONFLICT(student_id,test_id) DO UPDATE SET
            attempt_id=excluded.attempt_id,advice_json=excluded.advice_json,updated_at=CURRENT_TIMESTAMP""", (user["id"], attempt["test_id"], attempt_id, json.dumps(advice)))
        db.commit()
    logger.info("Student explicitly requested updated mock-test advice")
    return {"attempt_id": attempt_id, **advice}


@app.post("/api/submissions/{submission_id}/evaluate")
def evaluate_submission(submission_id: str, user: dict = Depends(authenticated_user)):
    with closing(connect()) as db:
        row = db.execute("""SELECT s.*,t.title,t.subject,t.class_id,t.paper_path FROM submissions s
            JOIN tests t ON t.id=s.test_id WHERE s.id=?""", (submission_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Submission not found")
        if user["role"] == "student" and user["id"] != row["student_id"]:
            raise HTTPException(403, "You can only evaluate your own answer sheet")
        if user["role"] == "teacher":
            require_class_access(row["class_id"], user, teacher_only=True)
        if not row["paper_path"] or not Path(row["paper_path"]).is_file():
            raise HTTPException(409, "The teacher has not uploaded a question paper for this test")
        questions = [dict(item) for item in db.execute("SELECT prompt,points FROM questions WHERE test_id=?", (row["test_id"],))]
        criteria = [dict(item) for item in db.execute("SELECT name,weight,guidance FROM criteria WHERE test_id=?", (row["test_id"],))]
        answer_key = db.execute("SELECT pdf_path FROM answer_keys WHERE test_id=?", (row["test_id"],)).fetchone()
        profile_row = db.execute("SELECT context_json FROM profiles WHERE student_id=?", (row["student_id"],)).fetchone()
        context = profile_row["context_json"] if profile_row else "{}"
        evaluation_prompt = {"test": row["title"], "subject": row["subject"], "questions": questions, "rubric": criteria, "student_profile": context}
        if answer_key and Path(answer_key["pdf_path"]).is_file():
            evaluation_prompt["teacher_answer_key"] = "An attached internal answer-key PDF is available for grading accuracy."
        answer_key_path = answer_key["pdf_path"] if answer_key else None
        result = get_ai_evaluation(json.dumps(evaluation_prompt), row["pdf_path"], row["paper_path"], answer_key_path)
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
def class_students(class_id: str, user: dict = Depends(authenticated_user)):
    require_class_access(class_id, user, teacher_only=True)
    with closing(connect()) as db:
        return [dict(row) for row in db.execute("SELECT u.id,u.name,u.email FROM users u JOIN enrollments e ON e.student_id=u.id WHERE e.class_id=?", (class_id,))]