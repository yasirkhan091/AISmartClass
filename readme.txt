AI Smartclass

Native Android classroom app with backend-backed teacher/student portals.
Teachers publish class tests with PDF question papers. Students in that class
can open the paper, submit an answer-sheet PDF, and view AI scores and
advice.

Build the APK with:
	./gradlew assembleDebug

APK output:
	AIClassroom_v0.9.apk

Release versions
----------------
For each release, increment versionName and versionCode in
app/build.gradle.kts. The APK filename uses versionName; commit the source and
APK together so each release can be restored with Git.

Backend and tech stack
----------------------
The Android client is a native Kotlin app using Jetpack Compose and Material 3.
It communicates with the Python FastAPI backend over HTTPS using JSON REST
endpoints and multipart PDF uploads. The backend stores users, classes, plans,
tests, submissions, evaluations, sessions, profiles, and PDFs in a relational
database. Local development defaults to SQLite. Production uses PostgreSQL
through psycopg, configured with DATABASE_URL. PDF bytes live in the database,
so they survive Render restarts without a paid persistent disk.

For grading and feedback, the backend sends the original PDFs to Google Gemini
or OpenAI from the server. Provider API keys never belong in the APK. OpenAI
uses its Responses API; Gemini remains supported. AI provider API usage may
incur charges independently of hosting. Keep local keys in backend/.env
(ignored by Git), not backend/.env.example.

The seeded demo accounts are IsraKhan (student) and YasirKhan (teacher).
Usernames are case-insensitive. Local development defaults to blank passwords.
Production requires separate, non-empty DEMO_STUDENT_PASSWORD and
DEMO_TEACHER_PASSWORD values of at least 10 characters; longer passwords are
recommended and must never be committed. All students currently share the
student account, so this demo account scheme is only suitable for a controlled
pilot, not real student records.

On Ubuntu, install Python support if needed, then start the backend locally:
	sudo apt update && sudo apt install python3-venv python3-pip
	cd backend
	python3 generate_demo_pdfs.py
	python3 -m venv .venv && . .venv/bin/activate
	pip install -r requirements.txt
	set -a && . ./.env && set +a
	uvicorn main:app --host 0.0.0.0 --port 8000

The laptop and phone must be on the same Wi-Fi. On Windows, get the laptop's
Wi-Fi IPv4 address with `ipconfig`. If the backend runs in WSL2 NAT mode, open
PowerShell as Administrator and forward port 8000 to WSL:
	$WslIp = (wsl hostname -I).Trim().Split(' ')[0]
	netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=8000 connectaddress=$WslIp connectport=8000
	New-NetFirewallRule -DisplayName "AI Smartclass local backend" -Direction Inbound -Protocol TCP -LocalPort 8000 -RemoteAddress LocalSubnet -Action Allow
On the phone login screen, enter `http://<windows-wifi-ip>:8000` and tap
Test connection. The health check reports backend and configured-provider status.

Hosted deployment
-----------------
The root render.yaml defines a free Render Python web service with automatic
deploys for commits to master. Render's free web filesystem is ephemeral, so
production must use an external PostgreSQL database. Create a free PostgreSQL
database with a provider such as Neon, then create a Render Blueprint from this
GitHub repository and set DATABASE_URL, DEMO_STUDENT_PASSWORD, and
DEMO_TEACHER_PASSWORD as private Render environment values. DATABASE_URL must be
the provider's TLS-enabled connection string. Add the chosen AI provider key
there too if AI grading/advice is required. Keep every secret out of Git.

After Render reports the service live, copy its HTTPS address into the
Backend address field on each phone and tap Test connection. Render free web
services can sleep while idle, so the first request after inactivity may take
longer. Build the APK with `./gradlew assembleDebug`; the current Android app
persists the backend address on each device.

GitHub CLI can create/push the repository, but it is not installed in every
environment. The GitHub and Render dashboards can also be used for account
authorization and initial setup; Render then deploys automatically on each
commit to master.

Two seeded tests and sample student attempts are in backend/demo_papers/:
`linear_equations.pdf`, `linear_equations_answers.pdf`, `polynomials.pdf`, and
`polynomials_answers.pdf`. The separate `*_key.pdf` files are teacher-only
grading references and are sent to the configured provider with each submission. Copy an answer
PDF to the phone, sign in as a student, open a test, and submit it. Backend and
Android failures are logged to the backend console and Android Logcat (tag:
AIClassroom); logs avoid PDF contents and API keys.

Teachers can edit test details, replace a question-paper PDF, or delete a test.
Deleting a test also removes its submissions, evaluations, and uploaded files.
Students can take the anytime Algebra Quick Check MCQ repeatedly. The server
scores each attempt; Gemini/OpenAI advice is generated only when the student
asks to view it, and only the latest generated advice per student/test is kept.
This text-only mock is intended to demonstrate AI feedback without PDF input.

Set `AI_PROVIDER=gemini` to use Gemini only, `AI_PROVIDER=openai` to use OpenAI
only, or `AI_PROVIDER=auto` to try Gemini first and then OpenAI if Gemini fails.
Use `GEMINI_API_KEY` with `GEMINI_MODEL=gemini-3.8-flash`, and/or
`OPENAI_API_KEY` with `OPENAI_MODEL=gpt-4.1-mini`. Auto fallback may incur
OpenAI API charges. OpenAI API billing is separate from ChatGPT subscriptions.
Never put provider keys in the APK.
Test with dummy or redacted student work, not identifiable student records.
Local LAN development uses unencrypted HTTP. Hosted access must use the Render
HTTPS URL. Demo usernames are public by design, so share passwords privately
and avoid real or identifiable student records until individual user accounts,
appropriate privacy controls, and a retention policy are in place.