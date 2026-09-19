import os
from pathlib import Path
from dotenv import load_dotenv
from google import genai

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def ask_gemini(prompt: str):
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("Gemini is not configured")
    with genai.Client(api_key=key) as client:
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=prompt
        )
        return response.text
