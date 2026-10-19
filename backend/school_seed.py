import json
import secrets
from datetime import date


SUBJECTS = (
    "Mathematics", "English", "Hindi", "Physics", "Chemistry",
    "Biology", "History", "Geography", "Computer Science", "Art",
)
SECTIONS = ("A", "B", "C", "D")
TEACHER_NAMES = (
    "Aarav Sharma", "Diya Patel", "Kabir Singh", "Anaya Verma", "Arjun Rao",
    "Meera Nair", "Vivaan Das", "Isha Gupta", "Reyansh Khan", "Saanvi Joshi",
    "Advik Roy", "Anika Mehta", "Ishaan Bose", "Myra Kapoor", "Ayaan Reddy",
    "Sara Thomas", "Krish Malhotra", "Kiara Menon", "Rudra Sethi", "Tara Iyer",
)
STUDENT_NAMES = (
    "Aanya", "Aarav", "Aditi", "Arjun", "Diya", "Ishaan", "Kabir", "Kiara",
    "Meera", "Neel", "Riya", "Saanvi", "Vihaan", "Zoya", "Anaya", "Dev",
)
HISTORICAL_DATES = ("2026-01-15", "2026-03-15", "2026-05-15", "2026-07-15")
QUESTION_TEMPLATES = (
    ("mcq", "Choose the correct response for {subject}: question {number}.", ["A", "B", "C", "D"], 1, "Option B is correct."),
    ("mcq", "Which statement best describes {subject} concept {number}?", ["Statement A", "Statement B", "Statement C", "Statement D"], 2, "Statement C applies the concept correctly."),
    ("subjective", "Explain one important idea from {subject}, question {number}.", [], "A clear explanation with a relevant example.", "Include the key idea and explain why it matters."),
    ("subjective", "Show your reasoning for this {subject} problem, question {number}.", [], "A correct method, clear steps, and a supported conclusion.", "Show each step and connect it to the conclusion."),
)
METRIC_NAMES = ("Subject understanding", "Reasoning and working", "Clear communication")


def seed_school_data(db, password_digest, student_password: str, teacher_password: str, admin_username: str, admin_password: str, sample_student_username: str = "student9a001", sample_teacher_username: str = "teacher01") -> dict:
    if db.execute("SELECT 1 FROM app_seed_markers WHERE name=?", ("school-demo-v1",)).fetchone():
        if admin_password:
            _upsert_user(db, password_digest, admin_username, admin_username, "teacher", admin_password, True)
            db.commit()
        return {"seeded": False, "admin_seeded": bool(admin_password)}

    for subject in SUBJECTS:
        db.execute("INSERT INTO subjects(id,name) VALUES(?,?) ON CONFLICT DO NOTHING", (subject.lower().replace(" ", "-"), subject))

    admin_seeded = False
    if admin_password:
        _upsert_user(db, password_digest, admin_username, admin_username, "teacher", admin_password, True)
        admin_seeded = True

    classes = []
    students_by_class = {}
    teacher_ids = []
    account_rows = []
    enrollment_rows = []
    profile_rows = []
    for teacher_index, name in enumerate(TEACHER_NAMES, start=1):
        username = sample_teacher_username.strip() if teacher_index == 1 and sample_teacher_username.strip() else f"teacher{teacher_index:02d}"
        teacher_ids.append(username.lower())
        salt = secrets.token_hex(16)
        display_name = "Sample Teacher" if teacher_index == 1 and sample_teacher_username.strip() else name
        account_rows.append((username.lower(), display_name, None, "teacher", username, salt, password_digest(teacher_password, salt), 0))

    for section in SECTIONS:
        class_id = f"class9-{section.lower()}"
        class_name = f"Class 9 Section {section}"
        classes.append((class_id, class_name))
        db.execute("INSERT INTO classes(id,name,year,teacher_id) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,year=excluded.year", (class_id, class_name, "2026 / 27", None))
        students = []
        for index in range(1, 81):
            username = sample_student_username.strip() if section == "A" and index == 1 and sample_student_username.strip() else f"student9{section.lower()}{index:03d}"
            user_id = username.lower()
            name = f"Sample Student {section}-001" if section == "A" and index == 1 and sample_student_username.strip() else f"{STUDENT_NAMES[(index - 1) % len(STUDENT_NAMES)]} {section}-{index:03d}"
            students.append((user_id, name, index))
            salt = secrets.token_hex(16)
            account_rows.append((user_id, name, None, "student", username, salt, password_digest(student_password, salt), 0))
            enrollment_rows.append((class_id, user_id))
            profile_rows.append((user_id, json.dumps({"class": class_name, "strengths": [], "focus_areas": []})))
        students_by_class[class_id] = students

    db.executemany("INSERT INTO users(id,name,email,role,username,password_salt,password_hash,is_admin) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(username) DO NOTHING", account_rows)
    db.executemany("INSERT INTO enrollments(class_id,student_id) VALUES(?,?) ON CONFLICT DO NOTHING", enrollment_rows)
    db.executemany("INSERT INTO profiles(student_id,context_json) VALUES(?,?) ON CONFLICT DO NOTHING", profile_rows)

    assignment_rows = []
    metric_seed_rows = []
    for subject_index, subject in enumerate(SUBJECTS):
        first_teacher = 2 * subject_index
        for section_index, (class_id, _) in enumerate(classes):
            teacher_index = first_teacher + (section_index // 2)
            teacher_id = teacher_ids[teacher_index]
            assignment_rows.append((f"assign-{class_id}-{subject_index}", class_id, teacher_id, subject, "subject"))
            class_teacher = None
            if subject_index == 0 and section_index in (0, 2):
                class_teacher = teacher_id
            elif subject_index == 1 and section_index in (1, 3):
                class_teacher = teacher_id
            if class_teacher:
                assignment_rows.append((f"class-teacher-{class_id}", class_id, class_teacher, None, "class"))
            for metric_index, metric_name in enumerate(METRIC_NAMES):
                metric_id = f"metric-{class_id}-{subject_index}-{metric_index}"
                metric_seed_rows.append((metric_id, class_id, subject, teacher_id, metric_name, f"Demonstrates {metric_name.lower()} in {subject}.", 1.0))
    db.executemany("INSERT INTO teacher_assignments(id,class_id,teacher_id,subject,assignment_type) VALUES(?,?,?,?,?) ON CONFLICT(id) DO NOTHING", assignment_rows)
    db.executemany("INSERT INTO teacher_metrics(id,class_id,subject,teacher_id,name,description,weight) VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING", metric_seed_rows)

    seeded_tests = 0
    seeded_attempts = 0
    attempt_rows = []
    analysis_rows = []
    snapshot_rows = []
    test_rows = []
    question_rows = []
    for class_id, _ in classes:
        subject_ratings_by_student = {student_id: {} for student_id, _, _ in students_by_class[class_id]}
        metric_ratings_by_student = {student_id: {} for student_id, _, _ in students_by_class[class_id]}
        for test_number in range(1, 5):
            for subject_index, subject in enumerate(SUBJECTS):
                metric_rows = [
                    {"id": f"metric-{class_id}-{subject_index}-{metric_index}", "name": name}
                    for metric_index, name in enumerate(METRIC_NAMES)
                ]
                test_id = f"test-{class_id}-{subject_index}-{test_number}"
                exam_date = HISTORICAL_DATES[test_number - 1]
                test_rows.append((test_id, class_id, f"{subject} Assessment {test_number}", subject, "MCQ + Subjective", exam_date))
                questions = []
                for question_index, (kind, prompt, options, key, _) in enumerate(QUESTION_TEMPLATES, start=1):
                    question_id = f"{test_id}-q{question_index}"
                    formatted_prompt = prompt.format(subject=subject, number=question_index)
                    question_rows.append((question_id, test_id, formatted_prompt, 2.5, kind, json.dumps(options), json.dumps(key), question_index))
                    questions.append({"id": question_id, "question_type": kind, "points": 2.5, "answer_key": key})
                seeded_tests += 1

                for student_id, _, student_index in students_by_class[class_id]:
                    progress = (test_number - 1) * 0.35
                    base_rating = 5.2 + ((student_index * 7 + subject_index * 3) % 23) * 0.15
                    test_rating = round(min(9.7, base_rating + progress), 1)
                    subject_old = subject_ratings_by_student[student_id].get(subject, test_rating)
                    subject_rating = round((subject_old * (test_number - 1) + test_rating) / test_number, 1)
                    subject_ratings_by_student[student_id][subject] = subject_rating
                    metric_ratings = {}
                    for metric_index, metric in enumerate(metric_rows):
                        rating = round(max(0, min(10, test_rating + (metric_index - 1) * 0.4)), 1)
                        metric_ratings[metric["id"]] = rating
                        metric_ratings_by_student[student_id][metric["id"]] = rating
                    overall_rating = round(sum(subject_ratings_by_student[student_id].values()) / len(subject_ratings_by_student[student_id]), 1)
                    score = round(test_rating, 1)
                    answers = {
                        questions[0]["id"]: 1 if student_index % 5 else 0,
                        questions[1]["id"]: 2 if student_index % 4 else 1,
                        questions[2]["id"]: "A clear explanation with a relevant example.",
                        questions[3]["id"]: "I showed the steps and checked the conclusion.",
                    }
                    attempt_id = f"attempt-{test_id}-{student_id}"
                    timestamp = f"{exam_date}T08:{subject_index * 5:02d}:00+00:00"
                    result = {
                        "score": score,
                        "max_score": 10,
                        "test_rating": test_rating,
                        "analysis": f"{student_id} demonstrated {subject.lower()} knowledge with improving accuracy.",
                        "strengths": ["Concept recall", "Attempt completion"],
                        "focus_areas": ["Show reasoning clearly"],
                        "advice": "Write each step and check the final result against the question.",
                        "subject_rating": subject_rating,
                        "metric_ratings": [{"metric_id": metric_id, "rating": rating, "evidence": "Generated sample evidence for this assessment."} for metric_id, rating in metric_ratings.items()],
                        "overall_rating": overall_rating,
                        "overall_analysis": f"Current overall rating {overall_rating}/10 across {len(subject_ratings_by_student[student_id])} assessed subjects.",
                        "question_results": [],
                    }
                    attempt_rows.append((attempt_id, test_id, student_id, json.dumps(answers), "analysed", timestamp))
                    analysis_rows.append((f"analysis-{attempt_id}", attempt_id, test_id, student_id, json.dumps(result), timestamp))
                    snapshot_rows.append((f"snapshot-{attempt_id}", student_id, class_id, test_id, timestamp, result["overall_analysis"], overall_rating, json.dumps(subject_ratings_by_student[student_id]), json.dumps(metric_ratings_by_student[student_id])))
                    seeded_attempts += 1

    db.executemany("INSERT INTO tests(id,class_id,title,subject,kind,due_date,is_mock,published) VALUES(?,?,?,?,?,?,0,1) ON CONFLICT(id) DO NOTHING", test_rows)
    db.executemany("INSERT INTO questions(id,test_id,prompt,points,question_type,options_json,answer_key,position) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING", question_rows)
    db.executemany("INSERT INTO test_attempts(id,test_id,student_id,answers_json,status,submitted_at,is_mock) VALUES(?,?,?,?,?,?,0) ON CONFLICT(id) DO NOTHING", attempt_rows)
    db.executemany("INSERT INTO test_analyses(id,attempt_id,test_id,student_id,result_json,created_at) VALUES(?,?,?,?,?,?) ON CONFLICT(attempt_id) DO NOTHING", analysis_rows)
    db.executemany("INSERT INTO student_analysis_snapshots(id,student_id,class_id,source_test_id,snapshot_at,overall_analysis,overall_rating,subject_ratings_json,metric_ratings_json) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING", snapshot_rows)

    for class_id, class_name in classes:
        mock_id = f"mock-general-knowledge-{class_id[-1]}"
        db.execute("INSERT INTO tests(id,class_id,title,subject,kind,due_date,is_mock,published) VALUES(?,?,?,?,?,?,1,1) ON CONFLICT(id) DO NOTHING", (mock_id, class_id, "General Knowledge and Logic Practice", "General Knowledge", "MCQ + Subjective", date.today().isoformat()))
        db.executemany("INSERT INTO questions(id,test_id,prompt,points,question_type,options_json,answer_key,position) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING", [(f"{mock_id}-q{question_index}", mock_id, prompt.format(subject="General Knowledge", number=question_index), 2.5, kind, json.dumps(options), json.dumps(key), question_index) for question_index, (kind, prompt, options, key, _) in enumerate(QUESTION_TEMPLATES, start=1)])
    db.execute("INSERT INTO app_seed_markers(name) VALUES(?)", ("school-demo-v1",))
    db.commit()
    return {"seeded": True, "classes": len(classes), "students": sum(len(items) for items in students_by_class.values()), "teachers": len(teacher_ids), "tests": seeded_tests, "attempts": seeded_attempts, "admin_seeded": admin_seeded}


def _upsert_user(db, password_digest, username: str, name: str, role: str, password: str, is_admin: bool = False) -> None:
    user_id = username.lower()
    existing = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if existing:
        if is_admin:
            salt = __import__("secrets").token_hex(16)
            db.execute("UPDATE users SET is_admin=1,password_salt=?,password_hash=?,is_active=1 WHERE id=?", (salt, password_digest(password, salt), existing["id"]))
        return
    salt = secrets.token_hex(16)
    db.execute("INSERT INTO users(id,name,email,role,username,password_salt,password_hash,is_admin) VALUES(?,?,NULL,?,?,?,?,?)", (user_id, name, role, username, salt, password_digest(password, salt), int(is_admin)))