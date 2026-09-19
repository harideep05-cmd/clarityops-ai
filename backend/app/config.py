import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND = Path(__file__).resolve().parents[1]
MODEL_NAME = "BAAI/bge-small-en-v1.5"
MODEL_REVISION = "52398278842ec682c6f32300af41344b1c0b0bb2"
MODEL_FILES = {
    "model_optimized.onnx",
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
}


@dataclass(frozen=True)
class Settings:
    data_dir: Path = BACKEND / "data"
    access_token: str = field(default="", repr=False)
    gemini_api_key: str = field(default="", repr=False)
    gemini_model: str = "gemini-2.5-flash"
    cors_origins: tuple[str, ...] = (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    )
    max_file_bytes: int = 10 * 1024 * 1024
    max_pages: int = 100
    max_text_chars: int = 500_000
    max_documents: int = 50
    max_chunks: int = 5_000
    extraction_timeout: int = 20
    provider_timeout_ms: int = 30_000
    retrieval_threshold: float = 0.55
    top_k: int = 5
    requests_per_minute: int = 60

    @classmethod
    def from_env(cls):
        load_dotenv(BACKEND / ".env", override=False)
        directory = Path(os.getenv("CLARITYOPS_DATA_DIR", "data")).expanduser()
        if not directory.is_absolute():
            directory = BACKEND / directory
        token = os.getenv("CLARITYOPS_ACCESS_TOKEN", "").strip()
        if token and len(token) < 32:
            raise ValueError("CLARITYOPS_ACCESS_TOKEN must be at least 32 characters")
        origins = tuple(
            filter(
                None,
                (
                    x.strip()
                    for x in os.getenv("CLARITYOPS_CORS_ORIGINS", ",".join(cls.cors_origins)).split(",")
                ),
            )
        )
        if "*" in origins:
            raise ValueError("Explicit CORS origins are required")
        return cls(
            data_dir=directory.resolve(),
            access_token=token,
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            cors_origins=origins,
        )
