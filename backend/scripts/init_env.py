"""Create a private .env with a random workspace token; never print secrets."""

import os
import secrets
from pathlib import Path

backend = Path(__file__).resolve().parents[1]
target = backend / ".env"
if target.exists():
    raise SystemExit("backend/.env already exists; no changes made.")
text = (
    (backend / ".env.example")
    .read_text()
    .replace("CLARITYOPS_ACCESS_TOKEN=\n", "CLARITYOPS_ACCESS_TOKEN=" + secrets.token_urlsafe(32) + "\n")
)
fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as file:
    file.write(text)
print(
    "Created backend/.env. Add your Gemini key locally; copy the workspace token into the app's unlock screen."
)
