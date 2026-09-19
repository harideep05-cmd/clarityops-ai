# Development setup

Use Python 3.12 and Node 22.12 or later (the existing Vite 8 lock requires a
modern Node). Run commands from the repository root unless stated otherwise.

```sh
cd backend
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate
python -m pip install -r requirements.txt
# Copy .env.example to .env and set GEMINI_API_KEY locally.
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```sh
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

The baseline `/health` route works without a provider key after lazy initialization.
The knowledge MVP setup and exact validation instructions will be recorded in the
root README as implementation progresses. Never use the prototype with private
company data or expose the development servers on the internet.
