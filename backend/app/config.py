"""App settings.

Plain English: this is the app's "settings card". It reads values (database addresses,
passwords, which AI service to use) from the file backend/.env so that secrets never
live inside the code. Every other part of the app asks get_settings() instead of
hard-coding anything.
"""

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    # PostgreSQL — holds the medical record (clinical_db)
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_admin_user: str = "postgres"
    pg_admin_password: str = ""

    # MySQL — holds billing: providers, insurers, claims (billing_db)
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_admin_user: str = "root"
    mysql_admin_password: str = ""

    # Password of the read-only "chatbot_ro" account the chatbot uses in BOTH databases
    ro_password: str = ""

    # Key that signs the "who is asking" note for PostgreSQL row-level security.
    # Optional: if empty, it is derived from the PostgreSQL admin password.
    rls_secret: str = ""

    # Which AI service writes SQL and answers
    llm_provider: Literal["groq", "gemini", "ollama"] = "groq"
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-coder:7b"

    # Safety and performance limits
    sql_timeout_seconds: int = 10
    max_sql_attempts: int = 3
    rows_stored_cap: int = 1000
    rows_to_llm: int = 50

    data_dir: Path = BACKEND_DIR / "data"

    # Drug-label library (RAG): where it is stored and how many passages to look up
    chroma_dir: Path = BACKEND_DIR / "chroma"
    rag_top_k: int = 6          # passages for a general drug question
    rag_per_drug_k: int = 3     # passages per named medicine (fewer when many medicines are involved)
    rag_max_drugs: int = 12     # most medicines looked up for one question
    rag_max_chunks: int = 18    # total passages budget for one answer

    def rls_key(self) -> str:
        """The signing key: RLS_SECRET if set, otherwise derived from the PG admin password."""
        if self.rls_secret:
            return self.rls_secret
        return hashlib.sha256(f"aether-rls|{self.pg_admin_password}".encode()).hexdigest()

    def clinical_url(self, admin: bool = False) -> str:
        """Connection address for PostgreSQL clinical_db (read-only user unless admin=True)."""
        user, pw = (self.pg_admin_user, self.pg_admin_password) if admin else ("chatbot_ro", self.ro_password)
        return f"postgresql+psycopg://{quote(user, safe='')}:{quote(pw, safe='')}@{self.pg_host}:{self.pg_port}/clinical_db"

    def billing_url(self, admin: bool = False) -> str:
        """Connection address for MySQL billing_db (read-only user unless admin=True)."""
        user, pw = (self.mysql_admin_user, self.mysql_admin_password) if admin else ("chatbot_ro", self.ro_password)
        return (
            f"mysql+pymysql://{quote(user, safe='')}:{quote(pw, safe='')}@{self.mysql_host}:{self.mysql_port}"
            "/billing_db?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
