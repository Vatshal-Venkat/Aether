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

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    # PostgreSQL — holds the medical record (clinical_db)
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_admin_user: str = "postgres"
    pg_admin_password: str = ""
    pg_sslmode: str = ""          # cloud Postgres (Neon): "require" — connections must be encrypted

    # MySQL — holds billing: providers, insurers, claims (billing_db)
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_admin_user: str = "root"
    mysql_admin_password: str = ""
    # Cloud MySQL (Aiven, TiDB): path of the certificate that proves the server is who it says (Aiven: the project's
    # ca.pem; TiDB: the system bundle /etc/ssl/certs/ca-certificates.crt). Empty = local, no encryption.
    mysql_ssl_ca: str = ""
    # Where the read-only account may log in from: "localhost" on your computer, "%" (anywhere) on a cloud
    # database, because the backend connects from Render.
    mysql_ro_host: str = "localhost"

    # Websites allowed to call this API from a browser, comma-separated (the Vercel address once deployed).
    # localhost on any port is always allowed, for development.
    cors_origins: str = ""

    # Port the backend listens on (python -m scripts.serve). The website reads the same AETHER_API_PORT
    # line from this .env file, so changing it here moves both. Default 8000.
    api_port: int = Field(8000, validation_alias=AliasChoices("AETHER_API_PORT", "API_PORT"), ge=1, le=65535)

    # Password of the read-only "chatbot_ro" account the chatbot uses in BOTH databases
    ro_password: str = ""

    # Key that signs the "who is asking" note for PostgreSQL row-level security.
    # Optional: if empty, it is derived from the PostgreSQL admin password.
    rls_secret: str = ""

    # Which AI service writes SQL and answers
    llm_provider: Literal["groq", "gemini", "ollama"] = "groq"
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"
    # Used automatically when the main Groq model's daily allowance runs out (it has its own allowance).
    # Leave empty to switch the fallback off.
    groq_fallback_model: str = "openai/gpt-oss-20b"
    # Fast lightweight model for classification/routing tasks (low latency).
    groq_fast_model: str = "openai/gpt-oss-20b"
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

    # Conversation memory: where turns are kept and how many recent ones a follow-up may use
    memory_path: Path = BACKEND_DIR / "data" / "memory.sqlite"
    memory_turns: int = 3

    # AI allowance logbook (tokens per model, last 24 h) for the website's "model limits" panel, and the
    # known free daily token limits (Groq states them in its limit messages; these are the defaults).
    usage_path: Path = BACKEND_DIR / "data" / "usage.sqlite"
    # Saved queries (app/memory/saved_queries.py): the same question reuses the SQL that answered it cleanly before
    saved_queries: bool = True
    saved_queries_path: Path = BACKEND_DIR / "data" / "saved_queries.sqlite"
    daily_token_limits: dict[str, int] = {"openai/gpt-oss-120b": 200_000, "openai/gpt-oss-20b": 200_000}

    # Service habits (Plan 5): audit log, answer cache, result pages, rate limit, AI queue
    audit_path: Path = BACKEND_DIR / "data" / "audit.sqlite"
    enable_audit_api: bool = False   # GET /api/audit shows every patient's questions: off unless you turn it on
    cache_size: int = 256            # answers remembered
    cache_ttl_s: int = 600           # ...for 10 minutes
    results_ttl_s: int = 1800        # big tables can be paged for 30 minutes
    page_size: int = 100             # rows per page
    rate_limit: int = 20             # questions per address...
    rate_window_s: int = 60          # ...per minute
    max_concurrent_chats: int = 2    # questions worked on at once (the free AI tier is the bottleneck)

    # Drug-label library (RAG): where it is stored and how many passages to look up
    chroma_dir: Path = BACKEND_DIR / "chroma"
    rag_top_k: int = 6          # passages for a general drug question
    rag_per_drug_k: int = 3     # passages per named medicine (fewer when many medicines are involved)
    rag_max_drugs: int = 12     # most medicines looked up for one question
    rag_max_chunks: int = 18    # total passages budget for one answer
    # Reranker (app/rag/rerank.py): fetch a few more passages than needed, keep the ones that best answer the question
    rag_query_rewrite: bool = True  # also search with the router's label-wording rewrites of the question
    rag_max_rewrites: int = 2       # most rewrites searched per question (each one is another search)
    # Threshold scoring: passages below the cut-off never reach the AI. Measured on our labels (2026-11-23): relevant
    # passages scored -4.2 or more, off-topic ones -6.2 or less. Without the reranker, a looser distance cut-off.
    rag_relevance_threshold: bool = True
    rag_min_score: float = -5.0      # reranker score (higher = more relevant)
    rag_max_distance: float = 0.75   # search distance, when the reranker is off (lower = closer)
    rag_rerank: bool = True
    rag_rerank_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    rag_rerank_pool: int = 3            # candidates fetched per passage kept (3 -> 18 read for a top 6)
    rag_rerank_max_candidates: int = 36  # cap on passages read per question (keeps it under about 2 s)

    def rls_key(self) -> str:
        """The signing key: RLS_SECRET if set, otherwise derived from the PG admin password."""
        if self.rls_secret:
            return self.rls_secret
        return hashlib.sha256(f"aether-rls|{self.pg_admin_password}".encode()).hexdigest()

    def clinical_url(self, admin: bool = False) -> str:
        """Connection address for PostgreSQL clinical_db (read-only user unless admin=True)."""
        user, pw = (self.pg_admin_user, self.pg_admin_password) if admin else ("chatbot_ro", self.ro_password)
        ssl = f"?sslmode={quote(self.pg_sslmode, safe='')}" if self.pg_sslmode else ""
        return f"postgresql+psycopg://{quote(user, safe='')}:{quote(pw, safe='')}@{self.pg_host}:{self.pg_port}/clinical_db{ssl}"

    def billing_url(self, admin: bool = False) -> str:
        """Connection address for MySQL billing_db (read-only user unless admin=True)."""
        user, pw = (self.mysql_admin_user, self.mysql_admin_password) if admin else ("chatbot_ro", self.ro_password)
        return (
            f"mysql+pymysql://{quote(user, safe='')}:{quote(pw, safe='')}@{self.mysql_host}:{self.mysql_port}"
            "/billing_db?charset=utf8mb4"
            + (f"&ssl_ca={quote(self.mysql_ssl_ca, safe='')}" if self.mysql_ssl_ca else "")
        )

    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
