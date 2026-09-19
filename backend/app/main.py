from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from PyPDF2 import PdfReader

from app.gemini_service import ask_gemini

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"

app = FastAPI(
    title="ClarityOps AI",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Prompt(BaseModel):
    prompt: str


@app.get("/")
def root():
    return {"message": "Welcome to ClarityOps AI"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask")
def ask(prompt: Prompt):
    try:
        answer = ask_gemini(prompt.prompt)
        return {"response": answer}
    except Exception as e:
        return {"response": f"Error: {str(e)}"}


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    file_path = UPLOAD_DIR / file.filename
    contents = await file.read()
    file_path.write_bytes(contents)

    return {
        "filename": file.filename,
        "message": "File uploaded successfully",
    }


@app.post("/read-pdf")
async def read_pdf(file: UploadFile = File(...)):
    contents = await file.read()
    reader = PdfReader(BytesIO(contents))

    pages_text = []
    for page in reader.pages:
        pages_text.append(page.extract_text() or "")

    return {
        "filename": file.filename,
        "text": "\n".join(pages_text),
    }
