import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
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
            paper_path = ROOT / "demo_papers" / paper_name
            key_path = ROOT / "demo_papers" / key_name
            if not paper_path.is_file() or not key_path.is_file():
                raise RuntimeError("Demo PDFs are missing; run python generate_demo_pdfs.py in backend/")
            db.execute("""INSERT OR IGNORE INTO tests(id,class_id,title,subject,kind,due_date,paper_path)
                VALUES(?,?,?,?,?,?,?)""", (test_id, CLASS_ID, title, subject, kind, due_date, str(paper_path)))
            db.execute("""CREATE TABLE IF NOT EXISTS answer_keys(test_id TEXT PRIMARY KEY REFERENCES tests(id), pdf_path TEXT NOT NULL)""")
            db.execute("INSERT OR IGNORE INTO answer_keys(test_id,pdf_path) VALUES(?,?)", (test_id, str(key_path)))
            db.execute("INSERT OR IGNORE INTO criteria(id,test_id,name,weight,guidance) VALUES(?,?,?,?,?)", (f"{test_id}-criteria", test_id, "Method and accuracy", 1.0, "Award partial credit for correct working; explain arithmetic and algebra errors."))
            for question_number in range(1, 11):
                db.execute("INSERT OR IGNORE INTO questions(id,test_id,prompt,points) VALUES(?,?,?,?)", (f"{test_id}-q{question_number}", test_id, f"Question {question_number} from the attached test paper", 2))
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


class QuestionInput(BaseModel):
    prompt: str
    points: float = 1


class CriteriaInput(BaseModel):
    name: str
    weight: float
    guidance: str = ""


def test_payload(row):
    return {"id": row["id"], "class_id": row["class_id"], "title": row["title"], "subject": row["subject"], "kind": row["kind"], "due_date": row["due_date"], "question_count": row["question_count"], "has_paper": bool(row["paper_path"])}


@app.get("/api/health")
def health():
    provider = os.getenv("AI_PROVIDER", "gemini").strip().lower()
    if provider == "openai":
        api_configured = bool(os.getenv("OPENAI_API_KEY") or os.getenv("AI_API_KEY"))
    else:
        api_configured = bool(os.getenv("GEMINI_API_KEY") or os.getenv("AI_API_KEY"))
    return {"status": "ok", "ai_configured": api_configured, "provider": provider, "model": os.getenv("AI_MODEL", "")}


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


@app.post("/api/tests/{test_id}/paper")
async def upload_test_paper(test_id: str, paper: UploadFile = File(...), user: dict = Depends(authenticated_user)):
    if paper.content_type != "application/pdf":
        logger.warning("Rejected non-PDF test paper")
        raise HTTPException(415, "Upload a PDF")
    with closing(connect()) as db:
        test = db.execute("SELECT class_id FROM tests WHERE id=?", (test_id,)).fetchone()
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
    model = os.getenv("AI_MODEL", "gpt-4.1-mini")
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
    provider = os.getenv("AI_PROVIDER", "gemini").strip().lower()
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("AI_API_KEY")
        if not api_key:
            logger.error("OpenAI evaluation requested but OPENAI_API_KEY is not configured")
            raise HTTPException(503, "Set OPENAI_API_KEY in the backend environment to enable evaluation")
        return get_openai_evaluation(prompt, answer_pdf_path, question_pdf_path, answer_key_path, api_key)
    if provider != "gemini":
        raise HTTPException(500, "AI_PROVIDER must be either openai or gemini")
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("AI_API_KEY")
    if not api_key:
        logger.error("AI evaluation requested but no Gemini API key is configured")
        raise HTTPException(503, "Set GEMINI_API_KEY on the backend to enable evaluation")
    model = os.getenv("AI_MODEL", "gemini-3.8-flash")
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