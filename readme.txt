AI Smartclass

Native Android classroom app with backend-backed student, teacher, and admin
portals. Teachers build digital MCQ and written-answer tests. Students answer
in the app and submit structured JSON; no assessment PDFs are used.

Build the APK with:
	./gradlew assembleDebug

APK output:
	AIClassroom_v1.0.apk

Release versions
----------------
For each release, increment versionName and versionCode in
app/build.gradle.kts. The APK filename uses versionName; commit the source and
APK together so each release can be restored with Git.

Backend and tech stack
----------------------
The Android client is a native Kotlin app using Jetpack Compose and Material 3.
It communicates with the Python FastAPI backend over HTTPS using JSON REST
endpoints. The backend stores users, teacher assignments, digital tests,
attempts, per-test analysis, teacher metrics, and dated student rating
snapshots. Local development defaults to SQLite. Production uses PostgreSQL
through psycopg, configured with DATABASE_URL.

The backend validates MCQs locally and sends a compact JSON context with
subjective answers, answer keys, prior analysis, current ratings, and teacher
metrics to OpenRouter. The response is validated JSON. Mock tests use the same
analysis path but are never persisted or added to cumulative ratings. Keep the
OPEN_ROUTER_API_KEY in backend/.env (ignored by Git); provider keys never belong in the
APK.

The deterministic seed creates Class 9 sections A-D with 80 students per
section, 20 teachers, 10 subjects, four historical tests per subject, metrics,
synthetic per-test analysis, and dated overall snapshots. Seed accounts use
DEMO_STUDENT_PASSWORD and DEMO_TEACHER_PASSWORD. Production also requires a
private ADMIN_PASSWORD of at least 10 characters for ADMIN_USERNAME. Never
commit these passwords. Seed identities and generated work are for testing.

On Ubuntu, install Python support if needed, then start the backend locally:
	sudo apt update && sudo apt install python3-venv python3-pip
	cd backend
	python3 -m venv .venv && . .venv/bin/activate
	pip install -r requirements.txt
	uvicorn main:app --env-file .env --host 0.0.0.0 --port 8000

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
GitHub repository and set DATABASE_URL, DEMO_STUDENT_PASSWORD,
DEMO_TEACHER_PASSWORD, ADMIN_PASSWORD, and OPEN_ROUTER_API_KEY as private Render
environment values. DATABASE_URL must be the provider's TLS-enabled connection
string. Set AI_PROVIDER=openrouter and OPEN_ROUTER_MODEL (default
openrouter/free). Keep every secret out of Git.

After Render reports the service live, copy its HTTPS address into the
Backend address field on each phone and tap Test connection. Render free web
services can sleep while idle, so the first request after inactivity may take
longer. Build the APK with `./gradlew assembleDebug`; the current Android app
persists the backend address on each device.

GitHub CLI can create/push the repository, but it is not installed in every
environment. The GitHub and Render dashboards can also be used for account
authorization and initial setup; Render then deploys automatically on each
commit to master.

Teachers create digital tests and subject metrics in the app. Subject teachers
can review analyses and ratings for their subjects; class teachers can view all
class ratings; administrators manage accounts and assignments. A teacher loses
access to a class when their assignment ends, while a replacement teacher can
review the class's historical records. Mock tests return feedback immediately
but do not change stored histories or cumulative ratings. Use seeded or
synthetic identities for testing, not identifiable student records.

OpenRouter API billing is separate from ChatGPT subscriptions. Never put provider
keys in the APK. Local LAN development uses unencrypted HTTP; hosted access
must use the Render HTTPS URL.
Local LAN development uses unencrypted HTTP. Hosted access must use the Render
HTTPS URL. Demo usernames are public by design, so share passwords privately
and avoid real or identifiable student records until individual user accounts,
appropriate privacy controls, and a retention policy are in place.