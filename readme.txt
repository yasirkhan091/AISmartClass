AI Smartclass

Native Android classroom app with backend-backed teacher/student portals.
Teachers publish class tests with PDF question papers. Students in that class
can open the paper, submit an answer-sheet PDF, and view Gemini scores and
advice.

Build the APK with:
	./gradlew assembleDebug

APK output:
	AIClassroom_v0.3.apk

Release versions
----------------
For each release, increment versionName and versionCode in
app/build.gradle.kts. The APK filename uses versionName; commit the source and
APK together so each release can be restored with Git.

Backend
-------
The FastAPI backend in backend/ stores users, classes, plans, test questions,
rubrics, PDF submissions, evaluations, and AI-readable student profiles in
SQLite. It sends the test paper, optional worked solution, and student's
original PDF to Gemini from the server so handwriting is available and the
API key stays off the phone.
Keep your real key in backend/.env (ignored by Git), not backend/.env.example.

The seeded demo accounts all use password yasir123123:
	naruto and sasuke are students; kakashi is the teacher.

On Ubuntu, install Python support if needed, then start the backend:
	sudo apt update && sudo apt install python3-venv python3-pip
	cd backend
	python3 generate_demo_pdfs.py
	python3 -m venv .venv && . .venv/bin/activate
	pip install -r requirements.txt
	set -a && . ./.env && set +a
	uvicorn main:app --host 0.0.0.0 --port 8000

The laptop and phone must be on the same Wi-Fi. Find the laptop's LAN address
with `hostname -I`. On the phone login screen, enter
`http://<laptop-lan-ip>:8000` as Backend address, then sign in. Check
`http://<laptop-lan-ip>:8000/api/health` from the phone browser. Allow inbound
TCP port 8000 through the laptop firewall if needed.

Two seeded tests and sample student attempts are in backend/demo_papers/:
`linear_equations.pdf`, `linear_equations_answers.pdf`, `polynomials.pdf`, and
`polynomials_answers.pdf`. The separate `*_key.pdf` files are teacher-only
grading references and are sent to Gemini with each submission. Copy an answer
PDF to the phone, sign in as a student, open a test, and submit it. Backend and
Android failures are logged to the backend console and Android Logcat (tag:
AIClassroom); logs avoid PDF contents and API keys.

Google AI Studio currently offers a limited free API tier for eligible models
and regions. Create a key at https://aistudio.google.com/apikey and set it as
GEMINI_API_KEY on the backend. Free-tier quotas and terms can change; Google
may use free-tier prompts to improve its products. Test with dummy or
redacted student work, not identifiable student records. Never put the key in
the APK. This LAN setup uses unencrypted HTTP for development only; do not
expose it publicly or use real student data until HTTPS and production access
controls are added.