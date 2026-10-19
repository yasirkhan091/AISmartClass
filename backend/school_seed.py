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
STUDENT_FIRST_NAMES = (
    "Aanya", "Aarav", "Aditi", "Ananya", "Arjun", "Avni", "Diya", "Ishaan",
    "Kabir", "Kavya", "Meera", "Neel", "Riya", "Saanvi", "Vihaan", "Zoya",
    "Aditya", "Isha", "Kian", "Nisha",
)
STUDENT_LAST_NAMES = (
    "Sharma", "Patel", "Singh", "Verma", "Rao", "Nair", "Das", "Gupta",
    "Khan", "Joshi", "Roy", "Mehta", "Bose", "Kapoor", "Reddy", "Thomas",
    "Malhotra", "Menon", "Sethi", "Iyer",
)
HISTORICAL_DATES = ("2026-01-15", "2026-03-15", "2026-05-15", "2026-07-15")
QUESTION_TEMPLATES = {
    "Mathematics": (
        ("mcq", "Solve 3x = 12.", ["x = 3", "x = 4", "x = 5", "x = 6"], 1, "Divide both sides by 3 to get x = 4."),
        ("subjective", "A rectangle is 5 cm long and 3 cm wide. Find its area and show the calculation.", [], "Area = length x width = 5 x 3 = 15 square centimeters."),
        ("mcq", "What is 1/2 + 1/4?", ["1/4", "2/4", "3/4", "1"], 2, "One half is two quarters, so the sum is three quarters."),
        ("subjective", "Solve 2x + 5 = 13. Show each step.", [], "Subtract 5 from both sides, then divide by 2. x = 4."),
    ),
    "English": (
        ("mcq", "Which word is closest in meaning to rapid?", ["Fast", "Quiet", "Heavy", "Late"], 0, "Rapid means fast."),
        ("subjective", "Rewrite this sentence in the past tense: She walks to school every day.", [], "She walked to school every day."),
        ("mcq", "Which word is the adjective in 'The bright sun warmed the field'?", ["sun", "bright", "warmed", "field"], 1, "Bright describes the sun."),
        ("subjective", "Join these ideas with a suitable conjunction: It was raining. We stayed inside.", [], "It was raining, so we stayed inside."),
    ),
    "Hindi": (
        ("mcq", "Which Hindi word means water?", ["Agni", "Jal", "Vayu", "Dharti"], 1, "Jal means water."),
        ("subjective", "Write the opposite of 'din' (day) in Hindi, using Roman letters or Devanagari.", [], "Raat, or रात, means night."),
        ("mcq", "Which word means 'book' in Hindi?", ["Pustak", "Phool", "Paani", "Ghar"], 0, "Pustak means book."),
        ("subjective", "Write one complete Hindi sentence about your school and explain its meaning.", [], "A relevant Hindi sentence with a matching explanation."),
    ),
    "Physics": (
        ("mcq", "What is the SI unit of force?", ["Joule", "Newton", "Watt", "Pascal"], 1, "Force is measured in newtons."),
        ("subjective", "A cyclist travels 100 metres in 20 seconds. Calculate the average speed.", [], "Speed = distance / time = 100 / 20 = 5 metres per second."),
        ("mcq", "What can an unbalanced force change?", ["An object's motion", "Its mass", "Its material", "Its temperature only"], 0, "An unbalanced force changes motion."),
        ("subjective", "Explain why a dropped ball falls toward the ground.", [], "Earth's gravitational force pulls the ball toward its centre."),
    ),
    "Chemistry": (
        ("mcq", "What is the chemical formula for water?", ["CO2", "H2O", "O2", "NaCl"], 1, "A water molecule contains two hydrogen atoms and one oxygen atom."),
        ("subjective", "Is melting ice a physical or chemical change? Explain your answer.", [], "It is a physical change because the substance remains water."),
        ("mcq", "A solution with pH 3 is best described as:", ["Acidic", "Neutral", "Alkaline", "Pure metal"], 0, "A pH below 7 is acidic."),
        ("subjective", "Describe how you could separate a mixture of sand and dissolved salt.", [], "Filter out the sand, then evaporate the water to recover the salt."),
    ),
    "Biology": (
        ("mcq", "Which cell structure carries out most photosynthesis?", ["Nucleus", "Chloroplast", "Cell wall", "Mitochondrion"], 1, "Chloroplasts contain chlorophyll for photosynthesis."),
        ("subjective", "Describe two jobs performed by plant roots.", [], "Roots anchor the plant and absorb water and minerals."),
        ("mcq", "Which organ pumps blood around the human body?", ["Lung", "Brain", "Heart", "Kidney"], 2, "The heart pumps blood through the circulatory system."),
        ("subjective", "Give a simple three-part food chain and explain the arrows.", [], "A valid producer-consumer chain with arrows showing energy transfer."),
    ),
    "History": (
        ("mcq", "Which Mauryan ruler is associated with the Kalinga War?", ["Ashoka", "Chandragupta II", "Harsha", "Akbar"], 0, "Ashoka fought the Kalinga War."),
        ("subjective", "Describe one change in Ashoka's rule after the Kalinga War.", [], "Ashoka promoted dhamma, non-violence, and public welfare after the war."),
        ("mcq", "In which year did India become independent?", ["1857", "1919", "1947", "1950"], 2, "India became independent in 1947."),
        ("subjective", "Why do historians compare letters, inscriptions, and objects when studying the past?", [], "Multiple sources help corroborate evidence and build a more reliable account."),
    ),
    "Geography": (
        ("mcq", "What is the latitude of the Equator?", ["0 degrees", "23.5 degrees", "66.5 degrees", "90 degrees"], 0, "The Equator is at zero degrees latitude."),
        ("subjective", "Explain the main stages of the water cycle.", [], "Evaporation, condensation, and precipitation, with water collecting and cycling again."),
        ("mcq", "Which is the largest continent by area?", ["Africa", "Asia", "Europe", "South America"], 1, "Asia is the largest continent."),
        ("subjective", "How does a map scale help someone estimate real distance?", [], "It relates a measured map distance to the corresponding ground distance."),
    ),
    "Computer Science": (
        ("mcq", "What number does the binary digit 1 represent?", ["Zero", "One", "Two", "Ten"], 1, "The binary digit 1 represents one."),
        ("subjective", "Write an algorithm in three or more steps for finding the larger of two numbers.", [], "Read both values, compare them, and report the larger value."),
        ("mcq", "Which is an input device?", ["Monitor", "Speaker", "Keyboard", "Printer"], 2, "A keyboard sends input to the computer."),
        ("subjective", "Give two ways to make an online account safer and explain one.", [], "Examples include a unique strong password and multi-factor authentication."),
    ),
    "Art": (
        ("mcq", "Which set contains the traditional primary colours?", ["Red, blue, yellow", "Green, orange, purple", "Black, white, grey", "Pink, teal, brown"], 0, "Red, blue, and yellow are traditional primary colours."),
        ("subjective", "Explain one difference between warm and cool colours and give an example of each.", [], "Warm colours include red or orange; cool colours include blue or green."),
        ("mcq", "Mixing red and blue paint usually creates which colour?", ["Green", "Purple", "Yellow", "White"], 1, "Red and blue make purple."),
        ("subjective", "Describe one way an artist can use perspective to show depth.", [], "Converging lines, scale changes, or overlap can make space appear deeper."),
    ),
    "General Knowledge": (
        ("mcq", "Which planet is known as the Red Planet?", ["Venus", "Mars", "Jupiter", "Neptune"], 1, "Mars is known as the Red Planet."),
        ("subjective", "Name India's capital and one public institution located there.", [], "New Delhi is India's capital; a valid institution example earns credit."),
        ("mcq", "Which number completes the pattern 2, 4, 6, __?", ["7", "8", "9", "10"], 1, "The pattern increases by two, so the answer is 8."),
        ("subjective", "A library has 12 storybooks and lends 5. How many remain? Show your calculation.", [], "12 - 5 = 7 storybooks remain."),
    ),
}


def questions_for(subject: str):
    templates = QUESTION_TEMPLATES.get(subject, QUESTION_TEMPLATES["General Knowledge"])
    return [template if len(template) == 5 else (*template, "") for template in templates]


METRICS = (
    ("Precision", "Works accurately and checks details."),
    ("Time management", "Allocates time effectively and completes tasks."),
    ("Critical thinking", "Explains reasoning and evaluates alternatives."),
    ("Concept application", "Applies subject concepts to unfamiliar problems."),
    ("Communication", "Presents answers clearly and in an organized way."),
)
METRIC_NAMES = tuple(name for name, _ in METRICS)


def student_name(section_index: int, student_index: int) -> str:
    first = STUDENT_FIRST_NAMES[(student_index - 1) % len(STUDENT_FIRST_NAMES)]
    surname_index = ((student_index - 1) // len(STUDENT_FIRST_NAMES) + section_index * 4) % len(STUDENT_LAST_NAMES)
    return f"{first} {STUDENT_LAST_NAMES[surname_index]}"


def _refresh_seeded_data(db, password_digest, admin_username, admin_password, sample_student_username, sample_teacher_username):
    if admin_password:
        _upsert_user(db, password_digest, admin_username, admin_username, "teacher", admin_password, True)

    teacher_ids = []
    teacher_updates = []
    for teacher_index, name in enumerate(TEACHER_NAMES, start=1):
        username = sample_teacher_username.strip().lower() if teacher_index == 1 and sample_teacher_username.strip() else f"teacher{teacher_index:02d}"
        teacher_ids.append(username)
        teacher_updates.append((name, username))
    db.executemany("UPDATE users SET name=? WHERE id=? AND role='teacher' AND is_admin=0", teacher_updates)

    student_updates = []
    stale_enrollments = []
    expected_enrollments = []
    for section_index, section in enumerate(SECTIONS):
        class_id = f"class9-{section.lower()}"
        for student_index in range(1, 81):
            username = sample_student_username.strip().lower() if section_index == 0 and student_index == 1 and sample_student_username.strip() else f"student9{section.lower()}{student_index:03d}"
            student_updates.append((student_name(section_index, student_index), username))
            stale_enrollments.append((username, class_id))
            expected_enrollments.append((class_id, username))
    db.executemany("UPDATE users SET name=? WHERE id=? AND role='student'", student_updates)
    db.executemany("DELETE FROM enrollments WHERE student_id=? AND class_id<>?", stale_enrollments)
    db.executemany("INSERT INTO enrollments(class_id,student_id) VALUES(?,?) ON CONFLICT DO NOTHING", expected_enrollments)

    metrics_by_subject = {}
    metric_seed_rows = []
    for subject_index, subject in enumerate(SUBJECTS):
        for section_index, section in enumerate(SECTIONS):
            class_id = f"class9-{section.lower()}"
            teacher_id = teacher_ids[2 * subject_index + section_index // 2]
            metric_rows = []
            for metric_index, (name, description) in enumerate(METRICS):
                metric_id = f"metric-{class_id}-{subject_index}-{metric_index}"
                metric_seed_rows.append((metric_id, class_id, subject, teacher_id, name, description))
                metric_rows.append({"id": metric_id, "name": name})
            metrics_by_subject[(class_id, subject)] = metric_rows
    db.executemany("""INSERT INTO teacher_metrics(id,class_id,subject,teacher_id,name,description,weight)
        VALUES(?,?,?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET teacher_id=excluded.teacher_id,
        name=excluded.name,description=excluded.description,retired_at=NULL""", metric_seed_rows)

    seeded_tests = db.execute("""SELECT id,class_id,subject FROM tests
        WHERE id LIKE 'test-class9-%' OR id LIKE 'mock-general-knowledge-%'""").fetchall()
    test_updates = []
    question_rows = []
    for test in seeded_tests:
        subject = "General Knowledge" if test["id"].startswith("mock-") else test["subject"]
        if subject in SUBJECTS:
            subject_index = SUBJECTS.index(subject)
            section_index = SECTIONS.index(test["class_id"][-1].upper())
            owner = teacher_ids[2 * subject_index + section_index // 2]
        else:
            owner = None
        if owner:
            test_updates.append((owner, test["id"]))
        for question_index, (kind, prompt, options, key, _) in enumerate(questions_for(subject), start=1):
            question_id = f"{test['id']}-q{question_index}"
            question_rows.append((question_id, test["id"], prompt, 2.5, kind, json.dumps(options), json.dumps(key), question_index))
    db.executemany("UPDATE tests SET created_by=?,duration_minutes=60 WHERE id=?", test_updates)
    db.executemany("""INSERT INTO questions(id,test_id,prompt,points,question_type,options_json,answer_key,position)
        VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET prompt=excluded.prompt,
        points=excluded.points,question_type=excluded.question_type,options_json=excluded.options_json,
        answer_key=excluded.answer_key,position=excluded.position""", question_rows)

    results_by_attempt = {}
    analysis_updates = []
    analyses = db.execute("""SELECT a.id,a.test_id,a.student_id,a.result_json,t.class_id,t.subject
        FROM test_analyses a JOIN tests t ON t.id=a.test_id
        WHERE t.id LIKE 'test-class9-%' ORDER BY a.created_at,a.id""").fetchall()
    for row in analyses:
        result = json.loads(row["result_json"])
        rating = float(result.get("test_rating", 5))
        metric_ratings = [
            {"metric_id": metric["id"], "rating": round(max(0, min(10, rating + (index - 2) * 0.25)), 1), "evidence": f"Evidence for {metric['name'].lower()} in this assessment."}
            for index, metric in enumerate(metrics_by_subject[(row["class_id"], row["subject"])])
        ]
        result["metric_ratings"] = metric_ratings
        result["analysis"] = f"The student demonstrated {row['subject'].lower()} knowledge with improving accuracy."
        analysis_updates.append((json.dumps(result), row["id"]))
        results_by_attempt[(row["test_id"], row["student_id"])] = metric_ratings
    db.executemany("UPDATE test_analyses SET result_json=? WHERE id=?", analysis_updates)

    metric_history = {}
    snapshot_updates = []
    snapshots = db.execute("""SELECT s.id,s.student_id,s.class_id,s.source_test_id
        FROM student_analysis_snapshots s JOIN tests t ON t.id=s.source_test_id
        WHERE t.id LIKE 'test-class9-%' ORDER BY s.student_id,s.class_id,s.snapshot_at,s.id""").fetchall()
    for snapshot in snapshots:
        history_key = (snapshot["student_id"], snapshot["class_id"])
        ratings = metric_history.setdefault(history_key, {})
        for metric in results_by_attempt.get((snapshot["source_test_id"], snapshot["student_id"]), []):
            ratings[metric["metric_id"]] = metric["rating"]
        snapshot_updates.append((json.dumps(ratings), snapshot["id"]))
    db.executemany("UPDATE student_analysis_snapshots SET metric_ratings_json=? WHERE id=?", snapshot_updates)


def seed_school_data(db, password_digest, student_password: str, teacher_password: str, admin_username: str, admin_password: str, sample_student_username: str = "student9a001", sample_teacher_username: str = "teacher01") -> dict:
    if db.execute("SELECT 1 FROM app_seed_markers WHERE name=?", ("school-demo-v1",)).fetchone():
        _refresh_seeded_data(db, password_digest, admin_username, admin_password, sample_student_username, sample_teacher_username)
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
        account_rows.append((username.lower(), name, None, "teacher", username, salt, password_digest(teacher_password, salt), 0))

    for section_index, section in enumerate(SECTIONS):
        class_id = f"class9-{section.lower()}"
        class_name = f"Class 9 Section {section}"
        classes.append((class_id, class_name))
        db.execute("INSERT INTO classes(id,name,year,teacher_id) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,year=excluded.year", (class_id, class_name, "2026 / 27", None))
        students = []
        for index in range(1, 81):
            username = sample_student_username.strip() if section == "A" and index == 1 and sample_student_username.strip() else f"student9{section.lower()}{index:03d}"
            user_id = username.lower()
            name = student_name(section_index, index)
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
    subject_teacher_by_class = {}
    for subject_index, subject in enumerate(SUBJECTS):
        first_teacher = 2 * subject_index
        for section_index, (class_id, _) in enumerate(classes):
            teacher_index = first_teacher + (section_index // 2)
            teacher_id = teacher_ids[teacher_index]
            subject_teacher_by_class[(class_id, subject)] = teacher_id
            assignment_rows.append((f"assign-{class_id}-{subject_index}", class_id, teacher_id, subject, "subject"))
            class_teacher = None
            if subject_index == 0 and section_index in (0, 2):
                class_teacher = teacher_id
            elif subject_index == 1 and section_index in (1, 3):
                class_teacher = teacher_id
            if class_teacher:
                assignment_rows.append((f"class-teacher-{class_id}", class_id, class_teacher, None, "class"))
            for metric_index, (metric_name, metric_description) in enumerate(METRICS):
                metric_id = f"metric-{class_id}-{subject_index}-{metric_index}"
                metric_seed_rows.append((metric_id, class_id, subject, teacher_id, metric_name, metric_description, 1.0))
    db.executemany("INSERT INTO teacher_assignments(id,class_id,teacher_id,subject,assignment_type) VALUES(?,?,?,?,?) ON CONFLICT(id) DO NOTHING", assignment_rows)
    db.executemany("INSERT INTO teacher_metrics(id,class_id,subject,teacher_id,name,description,weight) VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,description=excluded.description,teacher_id=excluded.teacher_id,retired_at=NULL", metric_seed_rows)

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
                test_rows.append((test_id, class_id, f"{subject} Assessment {test_number}", subject, "MCQ + Subjective", exam_date, subject_teacher_by_class[(class_id, subject)]))
                questions = []
                for question_index, (kind, prompt, options, key, _) in enumerate(questions_for(subject), start=1):
                    question_id = f"{test_id}-q{question_index}"
                    question_rows.append((question_id, test_id, prompt, 2.5, kind, json.dumps(options), json.dumps(key), question_index))
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

    db.executemany("INSERT INTO tests(id,class_id,title,subject,kind,due_date,is_mock,published,created_by) VALUES(?,?,?,?,?,?,0,1,?) ON CONFLICT(id) DO NOTHING", test_rows)
    db.executemany("INSERT INTO questions(id,test_id,prompt,points,question_type,options_json,answer_key,position) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING", question_rows)
    db.executemany("INSERT INTO test_attempts(id,test_id,student_id,answers_json,status,submitted_at,is_mock) VALUES(?,?,?,?,?,?,0) ON CONFLICT(id) DO NOTHING", attempt_rows)
    db.executemany("INSERT INTO test_analyses(id,attempt_id,test_id,student_id,result_json,created_at) VALUES(?,?,?,?,?,?) ON CONFLICT(attempt_id) DO NOTHING", analysis_rows)
    db.executemany("INSERT INTO student_analysis_snapshots(id,student_id,class_id,source_test_id,snapshot_at,overall_analysis,overall_rating,subject_ratings_json,metric_ratings_json) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING", snapshot_rows)

    for class_id, class_name in classes:
        mock_id = f"mock-general-knowledge-{class_id[-1]}"
        db.execute("INSERT INTO tests(id,class_id,title,subject,kind,due_date,is_mock,published) VALUES(?,?,?,?,?,?,1,1) ON CONFLICT(id) DO NOTHING", (mock_id, class_id, "General Knowledge and Logic Practice", "General Knowledge", "MCQ + Subjective", date.today().isoformat()))
        db.executemany("INSERT INTO questions(id,test_id,prompt,points,question_type,options_json,answer_key,position) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET prompt=excluded.prompt,options_json=excluded.options_json,answer_key=excluded.answer_key,position=excluded.position", [(f"{mock_id}-q{question_index}", mock_id, prompt, 2.5, kind, json.dumps(options), json.dumps(key), question_index) for question_index, (kind, prompt, options, key, _) in enumerate(questions_for("General Knowledge"), start=1)])
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