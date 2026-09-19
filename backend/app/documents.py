import json
import os
import re
import subprocess
import sys
import unicodedata

from .config import BACKEND, Settings
from .errors import AppError

PDF_ERRORS = {
    "encrypted_pdf": "Password-protected PDFs are unsupported. Upload an unencrypted copy.",
    "empty_document": "This PDF contains no pages.",
    "no_extractable_text": "No readable text was found. Scanned PDFs need a text layer; OCR is not supported yet.",
    "too_many_pages": "PDFs may contain at most 100 pages.",
    "too_much_text": "This PDF contains too much text. Split it into smaller documents.",
    "document_too_complex": "This PDF is too complex to process. Export a simpler text PDF.",
    "malformed_pdf": "This PDF could not be read. Export a fresh text-based PDF and try again.",
}


def validate_upload(filename: str | None, mime: str | None, data: bytes, settings: Settings) -> str:
    name = unicodedata.normalize("NFKC", filename or "").strip()
    if (
        not name
        or len(name) > 180
        or any(c in name for c in "/\\:")
        or any(unicodedata.category(c).startswith("C") for c in name)
    ):
        raise AppError(
            400, "invalid_filename", "Use a PDF filename without paths or special control characters."
        )
    if not name.lower().endswith(".pdf") or mime not in ("application/pdf", "application/octet-stream", None):
        raise AppError(415, "unsupported_file", "Only text-based PDF files are supported.")
    if len(data) > settings.max_file_bytes:
        raise AppError(413, "file_too_large", "PDFs must be 10 MB or smaller.")
    if not data:
        raise AppError(422, "empty_file", "The uploaded file is empty.")
    if not data.startswith(b"%PDF-"):
        raise AppError(415, "invalid_pdf", "The file does not have a valid PDF signature.")
    return name


def extract_pdf(data: bytes, settings: Settings) -> dict:
    worker_env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in {
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "CLARITYOPS_ACCESS_TOKEN",
        }
    }
    try:
        result = subprocess.run(
            [sys.executable, "-m", "app.pdf_worker", str(settings.max_pages), str(settings.max_text_chars)],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=settings.extraction_timeout,
            cwd=BACKEND,
            env=worker_env,
            check=False,
        )
        if result.returncode:
            raise AppError(
                422, "extraction_failed", "The PDF exceeded processing limits or could not be read."
            )
        extracted = json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        raise AppError(
            422, "extraction_timeout", "This PDF took too long to process. Export a simpler PDF."
        ) from None
    except (OSError, ValueError):
        raise AppError(
            503, "extraction_unavailable", "Document processing is temporarily unavailable."
        ) from None
    if "error" in extracted:
        code = extracted["error"]
        raise AppError(422, code, PDF_ERRORS.get(code, PDF_ERRORS["malformed_pdf"]))
    return extracted


def chunk_pages(pages: list[dict], size: int = 1000, overlap: int = 180) -> list[dict]:
    """Page-local, sentence/newline-aware windows, with normalized character offsets.

    ~250 English tokens per window leaves space within BGE's 512-token context.
    18% overlap protects boundary clauses. Embedding code rejects token overflow.
    """
    if not 0 <= overlap < size:
        raise ValueError("overlap must be smaller than size")
    chunks = []
    for page in pages:
        text, start = page["text"], 0
        while start < len(text):
            end = min(start + size, len(text))
            if end < len(text):
                boundaries = list(re.finditer(r"[.!?](?:\s|$)|\n", text[start:end]))
                if boundaries and boundaries[-1].end() >= size * 0.6:
                    end = start + boundaries[-1].end()
            section = text[start:end]
            left = len(section) - len(section.lstrip())
            body = section.strip()
            if body:
                chunks.append(
                    {
                        "page": page["page"],
                        "text": body,
                        "char_start": start + left,
                        "char_end": start + left + len(body),
                    }
                )
            if end == len(text):
                break
            start = max(start + 1, end - overlap)
    return chunks
