import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

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
    auth_mode: str = "demo"
    deployment: str = "local"
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
    max_workspaces: int = 20
    max_members: int = 100

    def __post_init__(self):
        if self.auth_mode not in {"demo", "members"} or self.deployment not in {"local", "private"}:
            raise ValueError("Choose a supported authentication and deployment mode")
        if self.deployment == "private" and self.auth_mode != "members":
            raise ValueError("Private hosting requires member authentication")
        if not self.cors_origins:
            raise ValueError("At least one explicit frontend origin is required")
        for origin in self.cors_origins:
            url = urlsplit(origin)
            if (url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password
                    or url.path or url.query or url.fragment or "*" in origin):
                raise ValueError("CORS entries must be explicit HTTP(S) origins without paths")
            if self.deployment == "private" and url.scheme != "https":
                raise ValueError("Private hosting requires HTTPS frontend origins")

    @classmethod
    def from_env(cls):
        load_dotenv(BACKEND / ".env", override=False)
        directory = Path(os.getenv("CLARITYOPS_DATA_DIR", "data")).expanduser()
        if not directory.is_absolute():
            directory = BACKEND / directory
        token = os.getenv("CLARITYOPS_ACCESS_TOKEN", "").strip()
        mode = os.getenv("CLARITYOPS_AUTH_MODE", "demo").strip()
        if mode not in {"demo", "members"}:
            raise ValueError("CLARITYOPS_AUTH_MODE must be demo or members")
        if mode == "demo" and token and len(token) < 32:
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
            auth_mode=mode,
            deployment=os.getenv("CLARITYOPS_DEPLOYMENT", "local").strip(),
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            cors_origins=origins,
        )
