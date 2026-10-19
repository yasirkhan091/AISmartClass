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
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Header, HTTPException
from pydantic import BaseModel
from school_services import build_analysis_context, score_mcq_questions, validate_analysis_result
from school_seed import seed_school_data

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("smartclass")

ROOT = Path(__file__).parent
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
DATABASE_URL = os.getenv("DATABASE_URL")
DEMO_STUDENT_USERNAME = os.getenv("DEMO_STUDENT_USERNAME", "student9a001").strip()
DEMO_TEACHER_USERNAME = os.getenv("DEMO_TEACHER_USERNAME", "teacher01").strip()
DEMO_STUDENT_PASSWORD = os.getenv("DEMO_STUDENT_PASSWORD", "")
DEMO_TEACHER_PASSWORD = os.getenv("DEMO_TEACHER_PASSWORD", "")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "schooladmin").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
if APP_ENV == "production":
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is required when APP_ENV=production")
    if min(len(DEMO_STUDENT_PASSWORD), len(DEMO_TEACHER_PASSWORD)) < 10:
        raise RuntimeError("Set separate DEMO_STUDENT_PASSWORD and DEMO_TEACHER_PASSWORD values of at least 10 characters in production")
    if DEMO_STUDENT_PASSWORD == DEMO_TEACHER_PASSWORD:
        raise RuntimeError("Student and teacher demo passwords must be different")
    if len(ADMIN_PASSWORD) < 10 or not ADMIN_USERNAME:
        raise RuntimeError("Set a private ADMIN_PASSWORD of at least 10 characters and ADMIN_USERNAME in production")
DB_PATH = Path(os.getenv("SMARTCLASS_DB", ROOT / "smartclass.db"))
app = FastAPI(title="AI Smartclass API", version="1.0")


class DatabaseRow(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            key = tuple(self.keys())[key]
        return super().__getitem__(key)


class DatabaseCursor:
    def __init__(self, cursor):
        self.cursor = cursor
        self.rowcount = cursor.rowcount

    @staticmethod
    def _row(row):
        return DatabaseRow(row) if row is not None else None

    def fetchone(self):
        return self._row(self.cursor.fetchone())

    def fetchall(self):
        return [self._row(row) for row in self.cursor.fetchall()]

    def __iter__(self):
        return (self._row(row) for row in self.cursor)


class PostgresConnection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, query, parameters=()):
        query = query.replace("CURRENT_TIMESTAMP", "CURRENT_TIMESTAMP::text")
        return DatabaseCursor(self.connection.execute(query.replace("%", "%%").replace("?", "%s"), parameters))

    def executemany(self, query, parameters):
        query = query.replace("CURRENT_TIMESTAMP", "CURRENT_TIMESTAMP::text")
        cursor = self.connection.cursor()
        cursor.executemany(query.replace("%", "%%").replace("?", "%s"), parameters)
        return DatabaseCursor(cursor)

    def executescript(self, script):
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def close(self):
        self.connection.close()


def connect():
    if DATABASE_URL:
        import psycopg
        from psycopg.rows import dict_row

        parsed_url = urllib.parse.urlsplit(DATABASE_URL)
        query = urllib.parse.parse_qsl(parsed_url.query, keep_blank_values=True)
        query = [(key, value) for key, value in query if key.lower() != "channel_binding"]
        database_url = urllib.parse.urlunsplit(parsed_url._replace(query=urllib.parse.urlencode(query)))
        return PostgresConnection(psycopg.connect(database_url, row_factory=dict_row))
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def initialize():
    with closing(connect()) as db:
        if not DATABASE_URL:
            db.execute("PRAGMA foreign_keys = ON")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE, role TEXT NOT NULL CHECK(role IN ('teacher','student')));
        CREATE TABLE IF NOT EXISTS classes(id TEXT PRIMARY KEY, name TEXT NOT NULL, year TEXT NOT NULL, teacher_id TEXT REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS enrollments(class_id TEXT REFERENCES classes(id), student_id TEXT REFERENCES users(id), PRIMARY KEY(class_id, student_id));
        CREATE TABLE IF NOT EXISTS plans(id TEXT PRIMARY KEY, class_id TEXT REFERENCES classes(id), week TEXT NOT NULL, title TEXT NOT NULL, target TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS tests(id TEXT PRIMARY KEY, class_id TEXT REFERENCES classes(id), title TEXT NOT NULL, subject TEXT NOT NULL, kind TEXT NOT NULL, due_date TEXT);
        CREATE TABLE IF NOT EXISTS questions(id TEXT PRIMARY KEY, test_id TEXT REFERENCES tests(id), prompt TEXT NOT NULL, points REAL NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS criteria(id TEXT PRIMARY KEY, test_id TEXT REFERENCES tests(id), name TEXT NOT NULL, weight REAL NOT NULL, guidance TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS profiles(student_id TEXT PRIMARY KEY REFERENCES users(id), context_json TEXT NOT NULL DEFAULT '{}');
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), expires_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS subjects(id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE);
        CREATE TABLE IF NOT EXISTS teacher_assignments(id TEXT PRIMARY KEY, class_id TEXT NOT NULL REFERENCES classes(id), teacher_id TEXT NOT NULL REFERENCES users(id), subject TEXT, assignment_type TEXT NOT NULL CHECK(assignment_type IN ('subject','class')), assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, unassigned_at TEXT);
        CREATE TABLE IF NOT EXISTS teacher_metrics(id TEXT PRIMARY KEY, class_id TEXT NOT NULL REFERENCES classes(id), subject TEXT NOT NULL, teacher_id TEXT NOT NULL REFERENCES users(id), name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', weight REAL NOT NULL DEFAULT 1, retired_at TEXT);
        CREATE TABLE IF NOT EXISTS test_attempts(id TEXT PRIMARY KEY, test_id TEXT NOT NULL REFERENCES tests(id), student_id TEXT NOT NULL REFERENCES users(id), answers_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'submitted', submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, is_mock INTEGER NOT NULL DEFAULT 0, UNIQUE(test_id,student_id,is_mock));
        CREATE TABLE IF NOT EXISTS test_analyses(id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL UNIQUE REFERENCES test_attempts(id), test_id TEXT NOT NULL REFERENCES tests(id), student_id TEXT NOT NULL REFERENCES users(id), result_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS student_analysis_snapshots(id TEXT PRIMARY KEY, student_id TEXT NOT NULL REFERENCES users(id), class_id TEXT NOT NULL REFERENCES classes(id), source_test_id TEXT REFERENCES tests(id), snapshot_at TEXT NOT NULL, overall_analysis TEXT NOT NULL, overall_rating REAL NOT NULL, subject_ratings_json TEXT NOT NULL, metric_ratings_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS app_seed_markers(name TEXT PRIMARY KEY, seeded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        """)
        if DATABASE_URL:
            user_columns = {row["column_name"] for row in db.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='users'")}
        else:
            user_columns = {row["name"] for row in db.execute("PRAGMA table_info(users)")}
        user_columns = {row["column_name"] for row in db.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='users'")} if DATABASE_URL else {row["name"] for row in db.execute("PRAGMA table_info(users)")}
        for column, declaration in (("username", "TEXT"), ("password_salt", "TEXT"), ("password_hash", "TEXT"), ("is_admin", "INTEGER NOT NULL DEFAULT 0"), ("is_active", "INTEGER NOT NULL DEFAULT 1")):
            if column not in user_columns:
                db.execute(f"ALTER TABLE users ADD COLUMN {column} {declaration}")
        migrations = {
            "tests": (("is_mock", "INTEGER NOT NULL DEFAULT 0"), ("published", "INTEGER NOT NULL DEFAULT 0"), ("created_by", "TEXT REFERENCES users(id)"), ("duration_minutes", "INTEGER NOT NULL DEFAULT 60")),
            "questions": (("question_type", "TEXT NOT NULL DEFAULT 'subjective'"), ("options_json", "TEXT NOT NULL DEFAULT '[]'"), ("answer_key", "TEXT"), ("position", "INTEGER NOT NULL DEFAULT 0")),
        }
        for table, additions in migrations.items():
            if DATABASE_URL:
                columns = {row["column_name"] for row in db.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=?", (table,))}
            else:
                columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
            for column, declaration in additions:
                if column not in columns:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
        db.execute("""UPDATE tests SET created_by=(SELECT a.teacher_id FROM teacher_assignments a
            WHERE a.class_id=tests.class_id AND a.subject=tests.subject AND a.assignment_type='subject'
            AND a.unassigned_at IS NULL ORDER BY a.assigned_at LIMIT 1)
            WHERE created_by IS NULL AND is_mock=0""")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_assignments_current ON teacher_assignments(teacher_id,class_id,unassigned_at)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_test_attempt_student ON test_attempts(student_id,submitted_at)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_student_time ON student_analysis_snapshots(student_id,snapshot_at)")
        db.commit()


initialize()
logger.info("Smartclass database initialized")


def get_integrity_errors():
    errors = [sqlite3.IntegrityError]
    if DATABASE_URL:
        import psycopg

        errors.append(psycopg.IntegrityError)
    return tuple(errors)


def password_digest(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 180_000).hex()


with closing(connect()) as db:
    seed_summary = seed_school_data(db, password_digest, DEMO_STUDENT_PASSWORD, DEMO_TEACHER_PASSWORD, ADMIN_USERNAME, ADMIN_PASSWORD, DEMO_STUDENT_USERNAME, DEMO_TEACHER_USERNAME)
logger.info("School data seed state: %s", seed_summary)


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
    kind: str = "Assessment"
    due_date: str | None = None
    is_mock: bool = False
    duration_minutes: int = 60


class TestUpdate(BaseModel):
    title: str | None = None
    subject: str | None = None
    kind: str | None = None
    due_date: str | None = None
    duration_minutes: int | None = None


class QuestionInput(BaseModel):
    prompt: str
    points: float = 1
    question_type: str = "subjective"
    options: list[str] = []
    answer_key: str | int | None = None
    position: int = 0


class TestAttemptInput(BaseModel):
    answers: dict[str, str | int | None]
    is_mock: bool = False


class TeacherMetricInput(BaseModel):
    subject: str
    name: str
    description: str = ""
    weight: float = 1


class TeacherAssignmentInput(BaseModel):
    teacher_id: str
    class_id: str
    assignment_type: str
    subject: str | None = None


class AdminStudentInput(BaseModel):
    username: str
    name: str
    password: str
    class_id: str


class AdminClassInput(BaseModel):
    name: str
    year: str


class AdminTeacherInput(BaseModel):
    username: str
    name: str
    password: str
    assignments: list[TeacherAssignmentInput] = []


class AdminUserUpdate(BaseModel):
    name: str | None = None
    username: str | None = None
    password: str | None = None
    class_id: str | None = None


def test_payload(row):
    columns = row.keys()
    return {"id": row["id"], "class_id": row["class_id"], "title": row["title"], "subject": row["subject"], "kind": row["kind"], "due_date": row["due_date"], "question_count": row["question_count"], "is_mock": bool(row["is_mock"]), "published": bool(row["published"]), "duration_minutes": row["duration_minutes"] if "duration_minutes" in columns else 60, "completed": bool(row["completed"]) if "completed" in columns else False, "pending": bool(row["pending"]) if "pending" in columns else False}


def ai_provider() -> str:
    return os.getenv("AI_PROVIDER", "openrouter").strip().lower()


def model_for_provider(provider: str | None = None) -> str:
    provider = provider or ai_provider()
    if provider == "openrouter":
        return os.getenv("OPEN_ROUTER_MODEL") or "openrouter/free"
    return os.getenv("OPENAI_MODEL") or "gpt-4.1-mini"


def get_structured_test_analysis(context: str, subjective_max_score: float, metrics: list[dict]) -> dict:
    provider = ai_provider()
    if provider != "openrouter":
        raise HTTPException(503, "Set AI_PROVIDER to openrouter to analyse submitted tests")
    api_key = os.getenv("OPEN_ROUTER_API_KEY")
    if not api_key:
        raise HTTPException(503, "Configure OPEN_ROUTER_API_KEY to analyse submitted tests")
    model = model_for_provider(provider)
    instructions = "You are a careful teacher. The input contains JSON. Grade subjective responses only; MCQ points have already been validated. Compare each answer to the answer key and allow equivalent reasoning. Use prior state and metric definitions to assess progress. Return only JSON with subjective_score, test_rating (0-10), analysis, strengths (array), focus_areas (array), advice, subject_rating (0-10), metric_ratings (one object per requested metric with metric_id, rating 0-10, evidence), overall_rating (0-10), and overall_analysis. Never include private cumulative ratings in student advice."
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": "Return a json object matching required_output. Assessment context:\n" + context},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://ais-smartclass-api.onrender.com",
        "X-Title": "AI Smartclass",
    }
    request = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=150) as response:
            payload = json.loads(response.read())
        text = payload["choices"][0]["message"]["content"]
        result = json.loads(text)
        return validate_analysis_result(result, subjective_max_score, metrics)
    except urllib.error.HTTPError as error:
        if error.code in (402, 429):
            raise HTTPException(402, "OpenRouter quota or credit limit reached; submitted answers are saved for retry.") from error
        if error.code >= 500:
            raise HTTPException(503, "OpenRouter is temporarily unavailable; submitted answers are saved for retry.") from error
        raise HTTPException(502, "OpenRouter analysis request failed; check backend logs.") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise HTTPException(503, "OpenRouter is temporarily unavailable; submitted answers are saved for retry.") from error
    except (json.JSONDecodeError, ValueError, KeyError, TypeError) as error:
        logger.warning("OpenRouter returned an invalid structured analysis")
        raise HTTPException(502, "OpenRouter returned invalid analysis; submitted answers are saved for retry.") from error


@app.get("/api/health")
def health():
    with closing(connect()) as db:
        db.execute("SELECT 1")
    provider = ai_provider()
    return {"status": "ok", "ai_configured": provider == "openrouter" and bool(os.getenv("OPEN_ROUTER_API_KEY")), "provider": provider, "model": model_for_provider(provider)}


@app.post("/api/login")
def login(data: Login):
    with closing(connect()) as db:
        row = db.execute("SELECT id,name,username,role,password_salt,password_hash,is_admin,is_active FROM users WHERE lower(username)=?", (data.username.strip().lower(),)).fetchone()
        if not row or not row["is_active"] or not hmac.compare_digest(password_digest(data.password, row["password_salt"]), row["password_hash"]):
            logger.warning("Rejected login attempt")
            raise HTTPException(401, "Incorrect username or password")
        token = secrets.token_urlsafe(32)
        db.execute("INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), row["id"], time.time() + 60 * 60 * 24 * 14))
        db.commit()
        logger.info("User authenticated")
        if row["is_admin"]:
            class_rows = [dict(item) for item in db.execute("SELECT id,name,year FROM classes ORDER BY name")]
        elif row["role"] == "teacher":
            class_rows = [dict(item) for item in db.execute("SELECT DISTINCT c.id,c.name,c.year FROM classes c JOIN teacher_assignments a ON a.class_id=c.id WHERE a.teacher_id=? AND a.unassigned_at IS NULL ORDER BY c.name", (row["id"],))]
        else:
            class_rows = [dict(item) for item in db.execute("SELECT c.id,c.name,c.year FROM classes c JOIN enrollments e ON e.class_id=c.id WHERE e.student_id=? ORDER BY c.name", (row["id"],))]
        classes = []
        for school_class in class_rows:
            if row["is_admin"]:
                assignments = db.execute("SELECT subject,assignment_type FROM teacher_assignments WHERE class_id=? AND unassigned_at IS NULL", (school_class["id"],)).fetchall()
                is_class_teacher = True
                subjects = sorted({assignment["subject"] for assignment in assignments if assignment["subject"]})
            elif row["role"] == "teacher":
                assignments = db.execute("SELECT subject,assignment_type FROM teacher_assignments WHERE class_id=? AND teacher_id=? AND unassigned_at IS NULL", (school_class["id"], row["id"])).fetchall()
                is_class_teacher = any(assignment["assignment_type"] == "class" for assignment in assignments)
                subjects = sorted({assignment["subject"] for assignment in assignments if assignment["subject"]})
            else:
                is_class_teacher = False
                subjects = []
            classes.append({**school_class, "is_class_teacher": is_class_teacher, "subjects": subjects})
        selected_class = classes[0] if classes else {"id": "", "name": "No class assigned", "year": ""}
        return {"access_token": token, "user": {"id": row["id"], "name": row["name"], "username": row["username"], "role": row["role"], "is_admin": bool(row["is_admin"])}, "class": selected_class, "classes": classes}


def authenticated_user(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sign in to continue")
    token_hash = hashlib.sha256(authorization[7:].encode()).hexdigest()
    with closing(connect()) as db:
        row = db.execute("""SELECT u.id,u.name,u.username,u.role,u.is_admin FROM sessions s JOIN users u ON u.id=s.user_id
            WHERE s.token_hash=? AND s.expires_at>?""", (token_hash, time.time())).fetchone()
        if not row:
            raise HTTPException(401, "Session expired. Please sign in again.")
        return dict(row)


def require_class_access(class_id: str, user: dict, teacher_only: bool = False, subject: str | None = None):
    if user.get("is_admin"):
        return
    with closing(connect()) as db:
        if user["role"] == "teacher":
            if subject:
                row = db.execute("SELECT 1 FROM teacher_assignments WHERE class_id=? AND teacher_id=? AND subject=? AND assignment_type='subject' AND unassigned_at IS NULL", (class_id, user["id"], subject)).fetchone()
            else:
                row = db.execute("SELECT 1 FROM teacher_assignments WHERE class_id=? AND teacher_id=? AND unassigned_at IS NULL", (class_id, user["id"])).fetchone()
        else:
            row = db.execute("SELECT 1 FROM enrollments WHERE class_id=? AND student_id=?", (class_id, user["id"])).fetchone()
    if not row or (teacher_only and user["role"] != "teacher"):
        raise HTTPException(403, "You do not have access to this class")


def require_subject_assignment(class_id: str, subject: str, user: dict) -> None:
    if user.get("is_admin"):
        return
    if user["role"] != "teacher":
        raise HTTPException(403, "Subject-teacher access required")
    with closing(connect()) as db:
        row = db.execute("SELECT 1 FROM teacher_assignments WHERE class_id=? AND teacher_id=? AND subject=? AND assignment_type='subject' AND unassigned_at IS NULL", (class_id, user["id"], subject)).fetchone()
    if not row:
        raise HTTPException(403, "You are not assigned to teach this subject in this class")


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
def list_tests(class_id: str, subject: str | None = None, is_mock: bool | None = None, user: dict = Depends(authenticated_user)):
    require_class_access(class_id, user)
    with closing(connect()) as db:
        if user["role"] == "student":
            filters = ["t.class_id=?", "t.published=1"]
            parameters = [user["id"], user["id"], class_id]
            query = """SELECT t.*,COUNT(q.id) AS question_count,
                EXISTS(SELECT 1 FROM test_attempts a WHERE a.test_id=t.id AND a.student_id=? AND a.is_mock=0 AND a.status='analysed') AS completed,
                EXISTS(SELECT 1 FROM test_attempts a WHERE a.test_id=t.id AND a.student_id=? AND a.is_mock=0 AND a.status='submitted') AS pending
                FROM tests t LEFT JOIN questions q ON q.test_id=t.id"""
        else:
            filters = ["t.class_id=?"]
            parameters = [class_id]
            query = "SELECT t.*,COUNT(q.id) AS question_count FROM tests t LEFT JOIN questions q ON q.test_id=t.id"
            if not user.get("is_admin"):
                filters.append("t.created_by=?")
                parameters.append(user["id"])
        if subject:
            filters.append("t.subject=?")
            parameters.append(subject)
        if is_mock is not None:
            filters.append("t.is_mock=?")
            parameters.append(int(is_mock))
        query += " WHERE " + " AND ".join(filters) + " GROUP BY t.id ORDER BY t.due_date,t.title"
        rows = db.execute(query, parameters).fetchall()
        return [test_payload(row) for row in rows]


@app.post("/api/tests")
def create_test(data: TestInput, user: dict = Depends(authenticated_user)):
    require_subject_assignment(data.class_id, data.subject, user)
    if not 1 <= data.duration_minutes <= 240:
        raise HTTPException(422, "Test duration must be between 1 and 240 minutes")
    test_id = str(uuid.uuid4())
    with closing(connect()) as db:
        db.execute("INSERT INTO tests(id,class_id,title,subject,kind,due_date,is_mock,published,created_by,duration_minutes) VALUES(?,?,?,?,?,?,?,0,?,?)", (test_id, data.class_id, data.title, data.subject, data.kind, data.due_date, int(data.is_mock), user["id"], data.duration_minutes))
        db.commit()
    return {"id": test_id, **data.model_dump()}


@app.patch("/api/tests/{test_id}")
def update_test(test_id: str, data: TestUpdate, user: dict = Depends(authenticated_user)):
    values = data.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(400, "Provide at least one test field to update")
    allowed_fields = {"title", "subject", "kind", "due_date", "duration_minutes"}
    if any(field not in allowed_fields for field in values):
        raise HTTPException(400, "Unsupported test field")
    with closing(connect()) as db:
        row = db.execute("SELECT class_id,subject FROM tests WHERE id=?", (test_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Test not found")
        require_subject_assignment(row["class_id"], row["subject"], user)
        if "duration_minutes" in values and values["duration_minutes"] is not None and not 1 <= values["duration_minutes"] <= 240:
            raise HTTPException(422, "Test duration must be between 1 and 240 minutes")
        if "subject" in values:
            require_subject_assignment(row["class_id"], values["subject"], user)
        assignments = ",".join(f"{field}=?" for field in values)
        db.execute(f"UPDATE tests SET {assignments} WHERE id=?", (*values.values(), test_id))
        db.commit()
        updated = db.execute("""SELECT t.*,COUNT(q.id) AS question_count FROM tests t
            LEFT JOIN questions q ON q.test_id=t.id WHERE t.id=? GROUP BY t.id""", (test_id,)).fetchone()
    logger.info("Teacher updated class test")
    return test_payload(updated)


@app.post("/api/tests/{test_id}/questions")
def add_question(test_id: str, data: QuestionInput, user: dict = Depends(authenticated_user)):
    if data.question_type not in {"mcq", "subjective"}:
        raise HTTPException(422, "question_type must be mcq or subjective")
    if data.points <= 0 or not data.prompt.strip():
        raise HTTPException(422, "Question text and positive points are required")
    if data.question_type == "mcq":
        if len(data.options) < 2 or any(not option.strip() for option in data.options):
            raise HTTPException(422, "MCQ questions require at least two non-empty options")
        if not isinstance(data.answer_key, int) or not 0 <= data.answer_key < len(data.options):
            raise HTTPException(422, "MCQ answer_key must be the index of a valid option")
    elif not isinstance(data.answer_key, str) or not data.answer_key.strip():
        raise HTTPException(422, "Subjective questions require an answer key or rubric")
    question_id = str(uuid.uuid4())
    with closing(connect()) as db:
        test = db.execute("SELECT class_id,subject,published FROM tests WHERE id=?", (test_id,)).fetchone()
        if not test:
            raise HTTPException(404, "Test not found")
        require_subject_assignment(test["class_id"], test["subject"], user)
        if test["published"]:
            raise HTTPException(409, "Unpublish the test before editing questions")
        position = data.position or db.execute("SELECT COALESCE(MAX(position),0)+1 FROM questions WHERE test_id=?", (test_id,)).fetchone()[0]
        db.execute("INSERT INTO questions(id,test_id,prompt,points,question_type,options_json,answer_key,position) VALUES(?,?,?,?,?,?,?,?)", (question_id, test_id, data.prompt.strip(), data.points, data.question_type, json.dumps(data.options), json.dumps(data.answer_key), position))
        db.commit()
    return {"id": question_id, "test_id": test_id, **data.model_dump()}


@app.get("/api/tests/{test_id}")
def get_digital_test(test_id: str, user: dict = Depends(authenticated_user)):
    with closing(connect()) as db:
        test = db.execute("SELECT * FROM tests WHERE id=?", (test_id,)).fetchone()
        if not test:
            raise HTTPException(404, "Test not found")
        require_class_access(test["class_id"], user, teacher_only=user["role"] == "teacher", subject=test["subject"] if user["role"] == "teacher" else None)
        if user["role"] == "student" and not test["published"]:
            raise HTTPException(404, "Test not found")
        questions = [dict(row) for row in db.execute("SELECT id,prompt,points,question_type,options_json,answer_key,position FROM questions WHERE test_id=? ORDER BY position,id", (test_id,))]
        attempt = None
        if user["role"] == "student" and not test["is_mock"]:
            attempt = db.execute("SELECT id,status,answers_json,submitted_at FROM test_attempts WHERE test_id=? AND student_id=? AND is_mock=0", (test_id, user["id"])).fetchone()
    return {
        **{key: test[key] for key in ("id", "class_id", "title", "subject", "kind", "due_date", "is_mock", "published")},
        "duration_minutes": test["duration_minutes"] if "duration_minutes" in test.keys() else 60,
        "questions": [{"id": row["id"], "prompt": row["prompt"], "points": row["points"], "question_type": row["question_type"], "options": json.loads(row["options_json"]), **({"answer_key": json.loads(row["answer_key"]) if row["answer_key"] else None} if user["role"] != "student" else {})} for row in questions],
        "my_attempt": None if not attempt else {"id": attempt["id"], "status": attempt["status"], "answers": json.loads(attempt["answers_json"]), "submitted_at": attempt["submitted_at"]},
    }


@app.post("/api/tests/{test_id}/publish")
def publish_digital_test(test_id: str, user: dict = Depends(authenticated_user)):
    with closing(connect()) as db:
        test = db.execute("SELECT class_id,subject FROM tests WHERE id=?", (test_id,)).fetchone()
        if not test:
            raise HTTPException(404, "Test not found")
        require_subject_assignment(test["class_id"], test["subject"], user)
        if not db.execute("SELECT 1 FROM questions WHERE test_id=?", (test_id,)).fetchone():
            raise HTTPException(409, "Add at least one question before publishing")
        db.execute("UPDATE tests SET published=1 WHERE id=?", (test_id,))
        db.commit()
    return {"id": test_id, "published": True}


def _analyse_test_submission(test: dict, questions: list[dict], answers: dict, student_id: str, mock: bool) -> dict:
    mcq_questions = []
    normalized_questions = []
    max_score = 0.0
    subjective_max_score = 0.0
    for question in questions:
        options = json.loads(question["options_json"] or "[]")
        answer_key = json.loads(question["answer_key"]) if question["answer_key"] else None
        item = {**dict(question), "options": options, "answer_key": answer_key}
        normalized_questions.append(item)
        max_score += float(question["points"])
        if question["question_type"] == "mcq":
            mcq_questions.append(item)
        else:
            subjective_max_score += float(question["points"])
    mcq_result = score_mcq_questions(mcq_questions, answers)
    with closing(connect()) as db:
        current_row = db.execute("SELECT * FROM student_analysis_snapshots WHERE student_id=? AND class_id=? ORDER BY snapshot_at DESC,id DESC LIMIT 1", (student_id, test["class_id"])).fetchone()
        previous_row = db.execute("""SELECT a.result_json,t.title,t.subject,t.due_date,a.created_at
            FROM test_analyses a JOIN tests t ON t.id=a.test_id
            WHERE a.student_id=? AND a.test_id<>? AND t.class_id=? AND t.subject=?
            ORDER BY a.created_at DESC,a.id DESC LIMIT 1""", (student_id, test["id"], test["class_id"], test["subject"])).fetchone()
        metrics = [dict(row) for row in db.execute("SELECT id,name,description,weight FROM teacher_metrics WHERE class_id=? AND subject=? AND retired_at IS NULL ORDER BY id", (test["class_id"], test["subject"]))]
    current_state = None if not current_row else {
        "as_of": current_row["snapshot_at"],
        "overall_analysis": current_row["overall_analysis"],
        "overall_rating": current_row["overall_rating"],
        "subject_ratings": json.loads(current_row["subject_ratings_json"]),
        "metric_ratings": json.loads(current_row["metric_ratings_json"]),
    }
    previous_test = None
    if previous_row:
        previous_result = json.loads(previous_row["result_json"])
        previous_test = {"title": previous_row["title"], "subject": previous_row["subject"], "date": previous_row["created_at"], "test_rating": previous_result.get("test_rating"), "analysis": previous_result.get("analysis"), "advice": previous_result.get("advice"), "score": previous_result.get("score")}
    subject_ratings = current_state["subject_ratings"] if current_state else {}
    previous_metric_ratings = current_state["metric_ratings"] if current_state else {}
    metric_ratings = {metric["id"]: previous_metric_ratings.get(metric["id"]) for metric in metrics}
    test_context = {"id": test["id"], "title": test["title"], "subject": test["subject"], "date": datetime.now(timezone.utc).isoformat(), "max_score": max_score, "is_mock": mock}
    context = build_analysis_context(test_context, normalized_questions, answers, current_state, previous_test, subject_ratings, metric_ratings, metrics, mcq_result)
    result = get_structured_test_analysis(context, subjective_max_score, metrics)
    result["score"] = round(mcq_result["score"] + float(result.pop("subjective_score")), 2)
    result["max_score"] = max_score
    result["question_results"] = mcq_result["question_results"]
    result["question_results"].extend(result.pop("subjective_question_results", []))
    return result


@app.post("/api/tests/{test_id}/attempts")
def submit_digital_test(test_id: str, data: TestAttemptInput, user: dict = Depends(authenticated_user)):
    if user["role"] != "student":
        raise HTTPException(403, "Only students can take a test")
    existing_attempt = None
    with closing(connect()) as db:
        test = db.execute("SELECT * FROM tests WHERE id=?", (test_id,)).fetchone()
        if not test or not test["published"]:
            raise HTTPException(404, "Test not found")
        require_class_access(test["class_id"], user)
        if bool(test["is_mock"]) != data.is_mock:
            raise HTTPException(422, "Mock-test mode does not match this test")
        if not data.is_mock:
            existing_attempt = db.execute("SELECT id,status,answers_json,submitted_at FROM test_attempts WHERE test_id=? AND student_id=? AND is_mock=0", (test_id, user["id"])).fetchone()
            if existing_attempt and existing_attempt["status"] != "submitted":
                raise HTTPException(409, "You already submitted this test")
        questions = [dict(row) for row in db.execute("SELECT id,prompt,points,question_type,options_json,answer_key,position FROM questions WHERE test_id=? ORDER BY position,id", (test_id,))]
    if not questions:
        raise HTTPException(409, "This test has no questions")
    expected_ids = {question["id"] for question in questions}
    if set(data.answers) - expected_ids:
        raise HTTPException(422, "Answers include an unknown question")
    normalized_answers = {}
    for question in questions:
        answer = data.answers.get(question["id"])
        if question["question_type"] == "mcq":
            options = json.loads(question["options_json"] or "[]")
            if answer is not None and (not isinstance(answer, int) or isinstance(answer, bool) or not 0 <= answer < len(options)):
                raise HTTPException(422, "An MCQ answer choice is invalid")
        elif answer is None:
            answer = ""
        elif not isinstance(answer, str) or len(answer) > 20000:
            raise HTTPException(422, "Subjective answers must contain at most 20,000 characters")
        normalized_answers[question["id"]] = answer
    if existing_attempt and json.loads(existing_attempt["answers_json"]) != normalized_answers:
        raise HTTPException(409, "A saved submission already exists; retry it with the original answers")
    if data.is_mock:
        result = _analyse_test_submission(dict(test), questions, normalized_answers, user["id"], True)
        public = {key: value for key, value in result.items() if key not in {"overall_rating", "overall_analysis", "subject_rating", "metric_ratings"}}
        return {"attempt_id": None, "is_mock": True, **public}
    attempt_id = existing_attempt["id"] if existing_attempt else str(uuid.uuid4())
    submitted_at = existing_attempt["submitted_at"] if existing_attempt else datetime.now(timezone.utc).isoformat(timespec="microseconds")
    with closing(connect()) as db:
        if not existing_attempt:
            try:
                db.execute("INSERT INTO test_attempts(id,test_id,student_id,answers_json,status,submitted_at,is_mock) VALUES(?,?,?,?,?,?,0)", (attempt_id, test_id, user["id"], json.dumps(normalized_answers), "submitted", submitted_at))
            except get_integrity_errors() as error:
                db.rollback()
                raise HTTPException(409, "You already submitted this test") from error
            db.commit()
    result = _analyse_test_submission(dict(test), questions, normalized_answers, user["id"], False)
    with closing(connect()) as db:
        db.execute("UPDATE test_attempts SET status='analysed' WHERE id=? AND status='submitted'", (attempt_id,))
        db.execute("INSERT INTO test_analyses(id,attempt_id,test_id,student_id,result_json,created_at) VALUES(?,?,?,?,?,?)", (str(uuid.uuid4()), attempt_id, test_id, user["id"], json.dumps(result), submitted_at))
        previous = db.execute("SELECT subject_ratings_json,metric_ratings_json FROM student_analysis_snapshots WHERE student_id=? AND class_id=? ORDER BY snapshot_at DESC,id DESC LIMIT 1", (user["id"], test["class_id"])).fetchone()
        subjects = json.loads(previous["subject_ratings_json"]) if previous else {}
        previous_metrics = json.loads(previous["metric_ratings_json"]) if previous else {}
        subjects[test["subject"]] = result["subject_rating"]
        for item in result["metric_ratings"]:
            previous_metrics[item["metric_id"]] = item["rating"]
        db.execute("INSERT INTO student_analysis_snapshots(id,student_id,class_id,source_test_id,snapshot_at,overall_analysis,overall_rating,subject_ratings_json,metric_ratings_json) VALUES(?,?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), user["id"], test["class_id"], test_id, submitted_at, result["overall_analysis"], result["overall_rating"], json.dumps(subjects), json.dumps(previous_metrics)))
        db.commit()
    logger.info("Digital test submitted and analysis snapshot stored")
    student_result = {key: value for key, value in result.items() if key not in {"overall_rating", "overall_analysis", "subject_rating", "metric_ratings"}}
    return {"attempt_id": attempt_id, "is_mock": False, **student_result}


def _current_teacher_assignments(db, class_id: str, user: dict) -> list[dict]:
    return [dict(row) for row in db.execute("SELECT subject,assignment_type FROM teacher_assignments WHERE class_id=? AND teacher_id=? AND unassigned_at IS NULL", (class_id, user["id"]))]


@app.get("/api/students/me/analyses")
def list_my_test_analyses(user: dict = Depends(authenticated_user)):
    if user["role"] != "student":
        raise HTTPException(403, "Student account required")
    with closing(connect()) as db:
        rows = db.execute("""SELECT a.test_id,t.title,t.subject,t.due_date,a.created_at,a.result_json
            FROM test_analyses a JOIN tests t ON t.id=a.test_id
            WHERE a.student_id=? ORDER BY a.created_at DESC,a.test_id""", (user["id"],)).fetchall()
    fields = ("score", "max_score", "test_rating", "analysis", "strengths", "focus_areas", "advice", "question_results")
    return [{"test_id": row["test_id"], "title": row["title"], "subject": row["subject"], "date": row["created_at"], **{key: json.loads(row["result_json"]).get(key) for key in fields}} for row in rows]


@app.get("/api/classes/{class_id}/students/{student_id}/analysis")
def get_student_analysis(class_id: str, student_id: str, as_of: str | None = None, subject: str | None = None, user: dict = Depends(authenticated_user)):
    if user["role"] != "teacher" and not user.get("is_admin"):
        raise HTTPException(403, "Teacher access required")
    with closing(connect()) as db:
        require_class_access(class_id, user, teacher_only=True)
        enrollment = db.execute("SELECT 1 FROM enrollments WHERE class_id=? AND student_id=?", (class_id, student_id)).fetchone()
        if not enrollment:
            raise HTTPException(404, "Student is not enrolled in this class")
        assignments = _current_teacher_assignments(db, class_id, user) if not user.get("is_admin") else [{"subject": None, "assignment_type": "class"}]
        is_class_teacher = user.get("is_admin") or any(item["assignment_type"] == "class" for item in assignments)
        allowed_subjects = {item["subject"] for item in assignments if item["subject"]}
        if subject and not is_class_teacher and subject not in allowed_subjects:
            raise HTTPException(403, "You are not assigned to this subject in this class")
        analysis_query = """SELECT a.test_id,a.created_at,a.result_json,t.title,t.subject,t.due_date
            FROM test_analyses a JOIN tests t ON t.id=a.test_id
            WHERE a.student_id=? AND t.class_id=?"""
        analysis_params = [student_id, class_id]
        if as_of:
            cutoff = as_of + "T23:59:59.999999+23:59" if len(as_of) == 10 else as_of
            analysis_query += " AND a.created_at<=?"
            analysis_params.append(cutoff)
        analysis_query += " ORDER BY a.created_at DESC,a.test_id"
        rows = db.execute(analysis_query, analysis_params).fetchall()
        if subject:
            rows = [row for row in rows if row["subject"] == subject]
        elif not is_class_teacher:
            rows = [row for row in rows if row["subject"] in allowed_subjects]
        query = "SELECT * FROM student_analysis_snapshots WHERE student_id=? AND class_id=?"
        params = [student_id, class_id]
        if as_of:
            query += " AND snapshot_at<=?"
            params.append(as_of + "T23:59:59.999999+23:59" if len(as_of) == 10 else as_of)
        query += " ORDER BY snapshot_at DESC,id DESC LIMIT 1"
        snapshot = db.execute(query, params).fetchone()
        visible_subjects = json.loads(snapshot["subject_ratings_json"]) if snapshot else {}
        if subject:
            visible_subjects = {key: value for key, value in visible_subjects.items() if key == subject}
        elif not is_class_teacher:
            visible_subjects = {key: value for key, value in visible_subjects.items() if key in allowed_subjects}
        if user.get("is_admin"):
            metric_sql = "SELECT id,name,subject FROM teacher_metrics WHERE class_id=? AND retired_at IS NULL"
            metric_params = [class_id]
            if subject:
                metric_sql += " AND subject=?"
                metric_params.append(subject)
            metric_rows = db.execute(metric_sql, metric_params).fetchall()
        elif allowed_subjects:
            visible_allowed = {subject} if subject else allowed_subjects
            placeholders = ",".join("?" for _ in visible_allowed)
            metric_rows = db.execute(f"SELECT id,name,subject FROM teacher_metrics WHERE class_id=? AND teacher_id=? AND retired_at IS NULL AND subject IN ({placeholders})", (class_id, user["id"], *sorted(visible_allowed))).fetchall()
        else:
            metric_rows = []
        raw_metric_ratings = json.loads(snapshot["metric_ratings_json"]) if snapshot else {}
        metric_ratings = {row["id"]: {"name": row["name"], "subject": row["subject"], "rating": raw_metric_ratings.get(row["id"])} for row in metric_rows}
    visible_tests = []
    for row in rows:
        result = json.loads(row["result_json"])
        if not is_class_teacher:
            result = {key: value for key, value in result.items() if key not in {"overall_rating", "overall_analysis"}}
        visible_tests.append({"test_id": row["test_id"], "title": row["title"], "subject": row["subject"], "date": row["created_at"], "result": result})
    return {
        "student_id": student_id,
        "as_of": snapshot["snapshot_at"] if snapshot else as_of,
        "tests": visible_tests,
        "overall": None if not snapshot or not is_class_teacher else {"analysis": snapshot["overall_analysis"], "rating": snapshot["overall_rating"]},
        "subject_ratings": visible_subjects,
        "metric_ratings": metric_ratings,
    }


@app.get("/api/classes/{class_id}/ratings")
def list_class_ratings(class_id: str, user: dict = Depends(authenticated_user)):
    if user["role"] != "teacher" and not user.get("is_admin"):
        raise HTTPException(403, "Teacher access required")
    with closing(connect()) as db:
        require_class_access(class_id, user, teacher_only=True)
        assignments = _current_teacher_assignments(db, class_id, user) if not user.get("is_admin") else [{"subject": None, "assignment_type": "class"}]
        is_class_teacher = user.get("is_admin") or any(item["assignment_type"] == "class" for item in assignments)
        allowed_subjects = {item["subject"] for item in assignments if item["subject"]}
        students = db.execute("SELECT u.id,u.name FROM users u JOIN enrollments e ON e.student_id=u.id WHERE e.class_id=? AND u.is_active=1 ORDER BY u.name", (class_id,)).fetchall()
        records = []
        for student in students:
            snapshot = db.execute("SELECT snapshot_at,overall_rating,overall_analysis,subject_ratings_json,metric_ratings_json FROM student_analysis_snapshots WHERE student_id=? AND class_id=? ORDER BY snapshot_at DESC,id DESC LIMIT 1", (student["id"], class_id)).fetchone()
            subjects = json.loads(snapshot["subject_ratings_json"]) if snapshot else {}
            if not is_class_teacher:
                subjects = {key: value for key, value in subjects.items() if key in allowed_subjects}
            metrics = json.loads(snapshot["metric_ratings_json"]) if snapshot else {}
            metric_rows = db.execute("SELECT id,subject,name,teacher_id FROM teacher_metrics WHERE class_id=? AND retired_at IS NULL", (class_id,)).fetchall()
            metrics = {metric["id"]: {"subject": metric["subject"], "name": metric["name"], "rating": metrics.get(metric["id"])} for metric in metric_rows if user.get("is_admin") or metric["subject"] in allowed_subjects and metric["teacher_id"] == user["id"]}
            records.append({"student_id": student["id"], "name": student["name"], "as_of": snapshot["snapshot_at"] if snapshot else None, "overall_rating": snapshot["overall_rating"] if snapshot and is_class_teacher else None, "overall_analysis": snapshot["overall_analysis"] if snapshot and is_class_teacher else None, "subject_ratings": subjects, "metric_ratings": metrics})
    return records


@app.get("/api/classes/{class_id}/metrics")
def list_teacher_metrics(class_id: str, subject: str, user: dict = Depends(authenticated_user)):
    require_subject_assignment(class_id, subject, user)
    with closing(connect()) as db:
        rows = db.execute("SELECT id,class_id,subject,name,description,weight FROM teacher_metrics WHERE class_id=? AND subject=? AND retired_at IS NULL ORDER BY name", (class_id, subject)).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/classes/{class_id}/metrics")
def create_teacher_metric(class_id: str, data: TeacherMetricInput, user: dict = Depends(authenticated_user)):
    if data.weight <= 0:
        raise HTTPException(422, "Metric weight must be positive")
    require_subject_assignment(class_id, data.subject, user)
    metric_id = str(uuid.uuid4())
    with closing(connect()) as db:
        db.execute("INSERT INTO teacher_metrics(id,class_id,subject,teacher_id,name,description,weight) VALUES(?,?,?,?,?,?,?)", (metric_id, class_id, data.subject, user["id"], data.name.strip(), data.description.strip(), data.weight))
        db.commit()
    return {"id": metric_id, "class_id": class_id, "teacher_id": user["id"], **data.model_dump()}


@app.delete("/api/classes/{class_id}/metrics/{metric_id}")
def retire_teacher_metric(class_id: str, metric_id: str, user: dict = Depends(authenticated_user)):
    with closing(connect()) as db:
        metric = db.execute("SELECT subject,teacher_id FROM teacher_metrics WHERE id=? AND class_id=? AND retired_at IS NULL", (metric_id, class_id)).fetchone()
        if not metric:
            raise HTTPException(404, "Metric not found")
        require_subject_assignment(class_id, metric["subject"], user)
        if not user.get("is_admin") and metric["teacher_id"] != user["id"]:
            raise HTTPException(403, "Only the metric owner can retire it")
        db.execute("UPDATE teacher_metrics SET retired_at=CURRENT_TIMESTAMP WHERE id=?", (metric_id,))
        db.commit()
    return {"id": metric_id, "retired": True}


def require_admin(user: dict) -> None:
    if not user.get("is_admin"):
        raise HTTPException(403, "Administrator access required")


def _create_account(db, username: str, name: str, role: str, password: str, is_admin: bool = False) -> None:
    if len(username.strip()) < 3 or len(password) < 10 or not name.strip():
        raise HTTPException(422, "Username and name are required; passwords must be at least 10 characters")
    existing = db.execute("SELECT 1 FROM users WHERE lower(username)=lower(?)", (username.strip(),)).fetchone()
    if existing:
        raise HTTPException(409, "Username is already in use")
    salt = secrets.token_hex(16)
    db.execute("INSERT INTO users(id,name,email,role,username,password_salt,password_hash,is_admin,is_active) VALUES(?,?,NULL,?,?,?,?,?,1)", (username.strip().lower(), name.strip(), role, username.strip(), salt, password_digest(password, salt), int(is_admin)))
    if role == "student":
        db.execute("INSERT INTO profiles(student_id,context_json) VALUES(?,?)", (username.strip().lower(), json.dumps({"strengths": [], "focus_areas": []})))


@app.get("/api/admin/classes")
def admin_list_classes(user: dict = Depends(authenticated_user)):
    require_admin(user)
    with closing(connect()) as db:
        rows = db.execute("SELECT c.id,c.name,c.year,COUNT(DISTINCT CASE WHEN u.is_active=1 THEN e.student_id END) AS student_count FROM classes c LEFT JOIN enrollments e ON e.class_id=c.id LEFT JOIN users u ON u.id=e.student_id GROUP BY c.id ORDER BY c.name").fetchall()
    return [dict(row) for row in rows]


@app.post("/api/admin/classes")
def admin_create_class(data: AdminClassInput, user: dict = Depends(authenticated_user)):
    require_admin(user)
    name = data.name.strip()
    year = data.year.strip()
    if not name or not year:
        raise HTTPException(422, "Class name and school year are required")
    class_id = str(uuid.uuid4())
    with closing(connect()) as db:
        if db.execute("SELECT 1 FROM classes WHERE lower(name)=lower(?) AND year=?", (name, year)).fetchone():
            raise HTTPException(409, "That class already exists for this school year")
        db.execute("INSERT INTO classes(id,name,year,teacher_id) VALUES(?,?,?,NULL)", (class_id, name, year))
        db.commit()
    return {"id": class_id, "name": name, "year": year, "student_count": 0}


@app.get("/api/admin/users")
def admin_list_users(role: str | None = None, user: dict = Depends(authenticated_user)):
    require_admin(user)
    with closing(connect()) as db:
        query = "SELECT u.id,u.name,u.username,u.role,u.is_admin,u.is_active,(SELECT e.class_id FROM enrollments e WHERE e.student_id=u.id ORDER BY e.class_id LIMIT 1) AS class_id FROM users u"
        if role:
            rows = db.execute(query + " WHERE u.role=? ORDER BY u.name", (role,)).fetchall()
        else:
            rows = db.execute(query + " ORDER BY u.role,u.name").fetchall()
    return [dict(row) for row in rows]


@app.post("/api/admin/students")
def admin_create_student(data: AdminStudentInput, user: dict = Depends(authenticated_user)):
    require_admin(user)
    with closing(connect()) as db:
        if not db.execute("SELECT 1 FROM classes WHERE id=?", (data.class_id,)).fetchone():
            raise HTTPException(404, "Class not found")
        _create_account(db, data.username, data.name, "student", data.password)
        student_id = data.username.strip().lower()
        db.execute("INSERT INTO enrollments(class_id,student_id) VALUES(?,?)", (data.class_id, student_id))
        db.commit()
    return {"id": student_id, "username": data.username, "name": data.name, "class_id": data.class_id, "role": "student"}


@app.post("/api/admin/teachers")
def admin_create_teacher(data: AdminTeacherInput, user: dict = Depends(authenticated_user)):
    require_admin(user)
    with closing(connect()) as db:
        _create_account(db, data.username, data.name, "teacher", data.password)
        teacher_id = data.username.strip().lower()
        for assignment in data.assignments:
            if assignment.assignment_type not in {"subject", "class"} or (assignment.assignment_type == "subject" and not assignment.subject) or (assignment.assignment_type == "class" and assignment.subject):
                raise HTTPException(422, "Subject assignments need a subject; class-teacher assignments do not")
            if not db.execute("SELECT 1 FROM classes WHERE id=?", (assignment.class_id,)).fetchone():
                raise HTTPException(404, "Assigned class not found")
            db.execute("INSERT INTO teacher_assignments(id,class_id,teacher_id,subject,assignment_type) VALUES(?,?,?,?,?)", (str(uuid.uuid4()), assignment.class_id, teacher_id, assignment.subject, assignment.assignment_type))
        db.commit()
    return {"id": teacher_id, "username": data.username, "name": data.name, "role": "teacher", "assignments": [item.model_dump() for item in data.assignments]}


@app.post("/api/admin/assignments")
def admin_assign_teacher(data: TeacherAssignmentInput, user: dict = Depends(authenticated_user)):
    require_admin(user)
    if data.assignment_type not in {"subject", "class"} or (data.assignment_type == "subject" and not data.subject) or (data.assignment_type == "class" and data.subject):
        raise HTTPException(422, "Subject assignments need a subject; class-teacher assignments do not")
    with closing(connect()) as db:
        if not db.execute("SELECT 1 FROM users WHERE id=? AND role='teacher' AND is_active=1", (data.teacher_id,)).fetchone():
            raise HTTPException(404, "Active teacher not found")
        if not db.execute("SELECT 1 FROM classes WHERE id=?", (data.class_id,)).fetchone():
            raise HTTPException(404, "Class not found")
        if db.execute("SELECT 1 FROM teacher_assignments WHERE teacher_id=? AND class_id=? AND assignment_type=? AND subject IS ? AND unassigned_at IS NULL", (data.teacher_id, data.class_id, data.assignment_type, data.subject)).fetchone():
            raise HTTPException(409, "Teacher already has this active assignment")
        assignment_id = str(uuid.uuid4())
        db.execute("INSERT INTO teacher_assignments(id,class_id,teacher_id,subject,assignment_type) VALUES(?,?,?,?,?)", (assignment_id, data.class_id, data.teacher_id, data.subject, data.assignment_type))
        db.commit()
    return {"id": assignment_id, **data.model_dump()}


@app.patch("/api/admin/users/{user_id}")
def admin_update_user(user_id: str, data: AdminUserUpdate, user: dict = Depends(authenticated_user)):
    require_admin(user)
    values = data.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(400, "Provide at least one account field to update")
    new_password = values.pop("password", None)
    class_id = values.pop("class_id", None)
    if "name" in values and not values["name"].strip():
        raise HTTPException(422, "Name cannot be empty")
    if "username" in values:
        values["username"] = values["username"].strip()
        if len(values["username"]) < 3:
            raise HTTPException(422, "Username must be at least 3 characters")
    if new_password is not None and len(new_password) < 10:
        raise HTTPException(422, "Passwords must be at least 10 characters")
    with closing(connect()) as db:
        account = db.execute("SELECT role,is_admin FROM users WHERE id=?", (user_id,)).fetchone()
        if not account or account["is_admin"]:
            raise HTTPException(404, "User not found or protected administrator account")
        if class_id and account["role"] != "student":
            raise HTTPException(422, "Only student accounts can be moved between classes")
        if class_id and not db.execute("SELECT 1 FROM classes WHERE id=?", (class_id,)).fetchone():
            raise HTTPException(404, "Class not found")
        if "username" in values and db.execute("SELECT 1 FROM users WHERE lower(username)=lower(?) AND id<>?", (values["username"], user_id)).fetchone():
            raise HTTPException(409, "Username is already in use")
        assignments = [f"{field}=?" for field in values]
        parameters = list(values.values())
        if new_password is not None:
            salt = secrets.token_hex(16)
            assignments.extend(("password_salt=?", "password_hash=?"))
            parameters.extend((salt, password_digest(new_password, salt)))
        if assignments:
            db.execute(f"UPDATE users SET {','.join(assignments)} WHERE id=?", (*parameters, user_id))
        if class_id:
            db.execute("DELETE FROM enrollments WHERE student_id=?", (user_id,))
            db.execute("INSERT INTO enrollments(class_id,student_id) VALUES(?,?)", (class_id, user_id))
        if new_password is not None or "username" in values:
            db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        db.commit()
        updated = db.execute("SELECT id,name,username,role,is_active FROM users WHERE id=?", (user_id,)).fetchone()
    return {**dict(updated), "class_id": class_id}


@app.delete("/api/admin/assignments/{assignment_id}")
def admin_unassign_teacher(assignment_id: str, user: dict = Depends(authenticated_user)):
    require_admin(user)
    with closing(connect()) as db:
        changed = db.execute("UPDATE teacher_assignments SET unassigned_at=CURRENT_TIMESTAMP WHERE id=? AND unassigned_at IS NULL", (assignment_id,)).rowcount
        if not changed:
            raise HTTPException(404, "Active assignment not found")
        db.commit()
    return {"id": assignment_id, "unassigned": True}


@app.patch("/api/admin/users/{user_id}/active")
def admin_set_user_active(user_id: str, active: bool, user: dict = Depends(authenticated_user)):
    require_admin(user)
    with closing(connect()) as db:
        changed = db.execute("UPDATE users SET is_active=? WHERE id=? AND is_admin=0", (int(active), user_id)).rowcount
        if not changed:
            raise HTTPException(404, "User not found or protected administrator account")
        if not active:
            db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            if db.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()["role"] == "teacher":
                db.execute("UPDATE teacher_assignments SET unassigned_at=CURRENT_TIMESTAMP WHERE teacher_id=? AND unassigned_at IS NULL", (user_id,))
        db.commit()
    return {"id": user_id, "active": active}


@app.get("/api/classes/{class_id}/students")
def class_students(class_id: str, user: dict = Depends(authenticated_user)):
    require_class_access(class_id, user, teacher_only=True)
    with closing(connect()) as db:
        return [dict(row) for row in db.execute("SELECT u.id,u.name,u.email FROM users u JOIN enrollments e ON e.student_id=u.id WHERE e.class_id=?", (class_id,))]