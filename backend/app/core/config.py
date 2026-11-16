import json
from pathlib import Path
from typing import List, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_CANDIDATES = [
    str(_REPO_ROOT / ".env"),
    str(_REPO_ROOT / "backend" / ".env"),
    ".env",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_CANDIDATES,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = "postgresql://algorevive:algorevive@localhost:5432/algorevive"
    TEST_DATABASE_URL: str = "postgresql://algorevive:algorevive@localhost:5432/algorevive_test"
    REDIS_URL: str = "redis://localhost:6379/0"
    STORAGE_BACKEND: str = "local"  # "s3" or "local"
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET: str = "algorevive"
    LOCAL_STORAGE_DIR: str = "/tmp/algorevive-storage"
    JWT_SECRET: str = "super-secret-development-jwt-token-key-32chars"
    JWT_EXPIRE_MINUTES: int = 1440
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    MAX_UPLOAD_MB: int = 50
    SANDBOX_IMAGE: str = "algorevive-sandbox:latest"
    SANDBOX_TIMEOUT_S: int = 60
    SANDBOX_MEMORY_MB: int = 512
    SANDBOX_CPUS: float = 1.0
    LLM_PROVIDER: str = "none"  # "none" or "openai_compatible"
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_API_KEY: str = "none"
    LLM_MODEL: str = "gpt-4o-mini"
    SENTRY_DSN: Optional[str] = None
    VITE_API_URL: Optional[str] = "http://localhost:8000"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: object) -> List[str]:
        if isinstance(v, str):
            v_str = v.strip()
            if v_str.startswith("[") and v_str.endswith("]"):
                try:
                    return json.loads(v_str)
                except Exception:
                    pass
            return [i.strip() for i in v_str.split(",") if i.strip()]
        elif isinstance(v, list):
            return [str(item) for item in v]
        return ["http://localhost:5173", "http://127.0.0.1:5173"]


settings = Settings()
