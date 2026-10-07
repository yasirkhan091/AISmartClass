AI Smartclass

Native Android classroom app with backend-backed teacher/student portals.
Teachers publish class tests with PDF question papers. Students in that class
can open the paper, submit an answer-sheet PDF, and view AI scores and
advice.

Build the APK with:
	./gradlew assembleDebug

APK output:
	AIClassroom_v0.7.apk

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
original PDF to the configured AI provider from the server so handwriting is
available and the API key stays off the phone. OpenAI uses the Responses API;
Gemini remains supported. Keep real keys in backend/.env (ignored by Git), not
backend/.env.example.

The seeded demo accounts use a blank password; sign in with username only:
	naruto and sasuke are students; kakashi is the teacher.
This disables password protection for demo accounts. Only use on a private
testing network; anyone who can reach the server can sign in as any demo user.

On Ubuntu, install Python support if needed, then start the backend:
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

Two seeded tests and sample student attempts are in backend/demo_papers/:
`linear_equations.pdf`, `linear_equations_answers.pdf`, `polynomials.pdf`, and
`polynomials_answers.pdf`. The separate `*_key.pdf` files are teacher-only
grading references and are sent to the configured provider with each submission. Copy an answer
PDF to the phone, sign in as a student, open a test, and submit it. Backend and
Android failures are logged to the backend console and Android Logcat (tag:
AIClassroom); logs avoid PDF contents and API keys.

Set `AI_PROVIDER=openai`, `OPENAI_API_KEY`, and `AI_MODEL=gpt-4.1-mini` in
backend/.env for OpenAI, or select Gemini and set its server-side key. OpenAI
API billing is separate from a ChatGPT subscription; add API credits in the
OpenAI developer platform before grading. Never put provider keys in the APK.
Test with dummy or redacted student work, not identifiable student records.
This LAN setup uses unencrypted HTTP for development only; do not expose it
publicly or use real student data until HTTPS and production access controls
are added.