"""Isolated PDF parser. The parent bounds input and kills timed-out processes."""

import io
import json
import logging
import sys
import unicodedata


def extract(data: bytes, max_pages: int, max_chars: int) -> dict:
    from pypdf import PdfReader

    logging.getLogger("pypdf").setLevel(logging.CRITICAL)
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            return {"error": "encrypted_pdf"}
        if not reader.pages:
            return {"error": "empty_document"}
        if len(reader.pages) > max_pages:
            return {"error": "too_many_pages"}
        pages, total, blank = [], 0, []
        for number, page in enumerate(reader.pages, 1):
            # Bound decompression too; the process memory/time caps cover adversarial PDFs.
            contents = page.get_contents()
            if contents and len(contents.get_data()) > 10 * 1024 * 1024:
                return {"error": "document_too_complex"}
            text = unicodedata.normalize("NFKC", page.extract_text() or "")
            text = "\n".join(" ".join(line.split()) for line in text.splitlines()).strip()
            text = "".join(c for c in text if c == "\n" or not unicodedata.category(c).startswith("C"))
            total += len(text)
            if total > max_chars:
                return {"error": "too_much_text"}
            pages.append({"page": number, "text": text})
            if not text:
                blank.append(number)
        if not any(any(c.isalnum() for c in p["text"]) for p in pages):
            return {"error": "no_extractable_text"}
        return {"pages": pages, "blank_pages": blank}
    except Exception:
        # Parser messages may include private content. Return only a known error code.
        return {"error": "malformed_pdf"}


if __name__ == "__main__":
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    except (ImportError, ValueError, OSError):
        pass  # Windows still has parent-enforced byte, page and wall-clock limits.
    print(json.dumps(extract(sys.stdin.buffer.read(), int(sys.argv[1]), int(sys.argv[2]))))
