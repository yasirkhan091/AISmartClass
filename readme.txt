AI Smartclass

Native Android classroom app with student and teacher views. Students can
track progress and choose a PDF answer sheet for a test. Teachers can create
tests and weekly targets. The app keeps demo plans, tests, and submissions on
the device.

Build the APK with:
	./gradlew assembleDebug

APK output:
	AIClassroom_v0.2.apk

Release versions
----------------
For each release, increment versionName and versionCode in
app/build.gradle.kts. The APK filename uses versionName; commit the source and
APK together so each release can be restored with Git.

Backend
-------
The FastAPI backend in backend/ stores users, classes, plans, test questions,
rubrics, PDF submissions, evaluations, and AI-readable student profiles in
SQLite. It sends the original student PDF to Gemini from the server, so visual
handwriting is available to the model and the API key stays off the phone.
Keep your real key in backend/.env (ignored by Git), not backend/.env.example.
To start a local backend on Linux:
	cd backend
	python -m venv .venv && . .venv/bin/activate
	pip install -r requirements.txt
	set -a && . ./.env && set +a
	uvicorn main:app --host 0.0.0.0 --port 8000

The laptop and phone must be on the same Wi-Fi. Open http://<laptop-lan-ip>:8000/docs
on the laptop to exercise login, class, test, PDF submission, and evaluation
endpoints. Check /api/health for backend status. Allow inbound TCP port 8000
through the laptop firewall if needed.

The APK currently runs in offline demo mode: creating targets/tests and choosing
a student PDF are local-only actions. It does not yet call this backend, so AI
grading can be tested through /docs but not from the phone app yet. Backend and
Android failures are logged to the backend console and Android Logcat (tag:
AIClassroom); logs avoid PDF contents and API keys.

Google AI Studio currently offers a limited free API tier for eligible models
and regions. Create a key at https://aistudio.google.com/apikey and set it as
GEMINI_API_KEY on the backend. Free-tier quotas and terms can change; Google
may use free-tier prompts to improve its products. Test with dummy or
redacted student work, not identifiable student records. Never put the key in
the APK. The Android app remains an offline prototype and is not yet connected
to a deployed backend. Configure TLS, authentication, and access controls
before using real student data.