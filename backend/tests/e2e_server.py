"""Browser-test server: real PDF/index/retrieval, explicit test-only answer generator."""

import os
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings  # noqa: E402
from app.embeddings import LocalEmbeddings  # noqa: E402
from app.gemini_service import Claim, GroundedResponse, insufficient, validate_answer  # noqa: E402
from app.main import create_app  # noqa: E402

if os.getenv("CLARITYOPS_E2E") != "1":
    raise SystemExit("This test server requires CLARITYOPS_E2E=1")


class SyntheticAnswerer:
    def answer(self, question, evidence):
        if "Simulate provider outage" in question:
            from app.errors import AppError

            raise AppError(
                502,
                "provider_unavailable",
                "The answer service is temporarily unavailable. Please try again.",
            )
        if "casual leave" not in question.lower():
            return insufficient()
        quote = "Employees receive 12 casual leave days per calendar year."
        for source in evidence:
            if quote in source["text"]:
                return validate_answer(
                    GroundedResponse(
                        supported=True, claims=[Claim(text=quote, quote=quote, source_id=source["source_id"])]
                    ),
                    evidence,
                )
        return insufficient()


if __name__ == "__main__":
    import uvicorn

    base = Settings.from_env()
    model = LocalEmbeddings(base)
    model.load()
    with tempfile.TemporaryDirectory(prefix="clarityops-e2e-") as directory:
        settings = replace(
            base,
            data_dir=Path(directory),
            access_token="browser-test-only-token-" + "x" * 32,
            gemini_api_key="test-double-no-network",
            cors_origins=("http://127.0.0.1:15173",),
            requests_per_minute=1000,
        )
        app = create_app(settings, model, SyntheticAnswerer())
        uvicorn.run(app, host="127.0.0.1", port=18000, log_level="warning", access_log=False)
