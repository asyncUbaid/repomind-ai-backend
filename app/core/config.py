from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "RepoMind AI"
    debug: bool = False
    database_url: str = "mysql+pymysql://root:password@localhost:3306/repomind"
    jwt_secret_key: str = "change_me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "qwen2.5-coder:1.5b"
    ollama_embedding_model: str = "qwen3-embedding:0.6b"
    ollama_chat_context_length: int = 4096
    ollama_chat_max_tokens: int = 512
    ollama_request_timeout_seconds: int = 120
    llm_max_concurrent_requests: int = 1
    rag_chunk_limit: int = 4
    qdrant_path: str = "./qdrant_data"
    github_token: str = ""
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    max_repository_files: int = 5000
    max_file_size_bytes: int = 1_000_000

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @field_validator("llm_max_concurrent_requests")
    @classmethod
    def validate_concurrency(cls, value: int) -> int:
        if value != 1:
            raise ValueError("RepoMind MVP requires exactly one concurrent LLM request")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
