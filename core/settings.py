"""
core/settings.py
Quản lý cấu hình tập trung (Centralized Settings) cho toàn bộ MediMind.
Sử dụng Pydantic Settings v2 để thẩm định, phân giải đường dẫn, tải biến môi trường
và bảo vệ thông tin nhạy cảm (Zero Secret Leaks).
"""
import os
import logging
from pathlib import Path
from typing import Optional, Any, List
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("MediMindSettings")

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _mask_secret(val: Optional[str]) -> str:
    """Mask secret value for safe logging and repr."""
    if not val or not str(val).strip():
        return "<EMPTY>"
    s = str(val).strip()
    if len(s) <= 8:
        return "***"
    return f"{s[:3]}...{s[-4:]}"


class GeminiSettings(BaseModel):
    """Cấu hình cho Google Gemini AI API."""
    api_key: Optional[str] = Field(default=None)
    chat_api_key: Optional[str] = Field(default=None)
    nutrition_api_key: Optional[str] = Field(default=None)
    chat_model: str = Field(default="gemini-flash-lite-latest")
    expansion_model: str = Field(default="gemini-flash-lite-latest")
    nutrition_model: str = Field(default="gemini-flash-lite-latest")
    ocr_model: str = Field(default="gemini-flash-lite-latest")
    interpretation_model: str = Field(default="gemini-flash-lite-latest")

    timeout_chat: float = Field(default=25.0)
    timeout_expansion: float = Field(default=3.0)
    timeout_nutrition: float = Field(default=15.0)
    timeout_ocr: float = Field(default=30.0)
    timeout_interpretation: float = Field(default=20.0)
    timeout_default: float = Field(default=25.0)

    def __repr__(self) -> str:
        return (
            f"GeminiSettings(api_key={_mask_secret(self.api_key)}, "
            f"chat_model={self.chat_model}, timeout_chat={self.timeout_chat}s)"
        )


class RetrySettings(BaseModel):
    """Cấu hình chiến lược Retry & Exponential Backoff."""
    max_attempts: int = Field(default=3)
    base_delay_seconds: float = Field(default=0.5)
    max_delay_seconds: float = Field(default=4.0)
    jitter: bool = Field(default=True)


class CircuitBreakerSettings(BaseModel):
    """Cấu hình bộ ngắt mạch Circuit Breaker."""
    enabled: bool = Field(default=True)
    failure_threshold: int = Field(default=5)
    cooldown_seconds: float = Field(default=30.0)


class RAGSettings(BaseModel):
    """Cấu hình Grounded RAG & MedlinePlus Knowledge Base."""
    query_expansion_enabled: bool = Field(default=False)
    query_expansion_provider: str = Field(default="gemini")
    query_expansion_timeout_seconds: float = Field(default=3.0)
    vector_search_enabled: bool = Field(default=False)
    rerank_enabled: bool = Field(default=False)
    rerank_model_path: str = Field(default="BAAI/bge-reranker-v2-m3")
    rerank_timeout_seconds: float = Field(default=3.0)
    acceptance_threshold: float = Field(default=0.35)
    bm25_no_df_cutoff: bool = Field(default=True)


class IngestionSettings(BaseModel):
    """Cấu hình Ingestion Pipeline & Text Chunking cho MedlinePlus RAG."""
    chunk_max_chars: int = Field(default=2000)
    chunk_overlap_chars: int = Field(default=200)
    min_chunk_chars: int = Field(default=200)
    hard_max_chars: int = Field(default=2200)
    batch_size: int = Field(default=50)
    chunking_version: str = Field(default="v2_sentence_contextual")
    embedding_model: str = Field(default="all-MiniLM-L6-v2")
    embedding_dimension: int = Field(default=384)


class SecuritySettings(BaseModel):
    """Cấu hình an ninh, Session Cookie và OAuth credentials."""
    secret_key: Optional[str] = Field(default=None)
    session_cookie_secure: bool = Field(default=False)
    session_lifetime_minutes: int = Field(default=120)
    trust_proxy_headers: bool = Field(default=False)
    trusted_proxy_count: int = Field(default=1)
    ocr_draft_retention_hours: int = Field(default=24)
    temp_upload_retention_hours: int = Field(default=24)
    seed_demo_accounts: bool = Field(default=False)
    dev_seed_users: bool = Field(default=False)
    cors_allowed_origins: List[str] = Field(default_factory=list)
    google_client_id: Optional[str] = Field(default=None)
    google_client_secret: Optional[str] = Field(default=None)
    google_redirect_uri: Optional[str] = Field(default=None)
    google_maps_api_key: Optional[str] = Field(default=None)

    def __repr__(self) -> str:
        return (
            f"SecuritySettings(secret_key={_mask_secret(self.secret_key)}, "
            f"cookie_secure={self.session_cookie_secure}, "
            f"cors_origins={len(self.cors_allowed_origins)}, "
            f"google_client_id={_mask_secret(self.google_client_id)})"
        )


class MessagingSettings(BaseModel):
    """Cấu hình SMS và Email OTP."""
    twilio_account_sid: Optional[str] = Field(default=None)
    twilio_auth_token: Optional[str] = Field(default=None)
    twilio_phone_number: Optional[str] = Field(default=None)
    speedsms_auth_token: Optional[str] = Field(default=None)

    smtp_server: Optional[str] = Field(default=None)
    smtp_port: int = Field(default=587)
    smtp_username: Optional[str] = Field(default=None)
    smtp_password: Optional[str] = Field(default=None)
    smtp_sender_name: str = Field(default="MediMind AI")
    smtp_use_tls: bool = Field(default=True)

    def __repr__(self) -> str:
        return f"MessagingSettings(twilio={bool(self.twilio_account_sid)}, smtp={bool(self.smtp_server)})"


class PathSettings(BaseModel):
    """Quản lý các đường dẫn tệp tin và cơ sở dữ liệu bền vững."""
    project_root: Path = Field(default=PROJECT_ROOT)
    data_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "instance")
    upload_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "uploads")
    chroma_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "medical_vectordb")
    static_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "static")
    templates_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "templates")
    database_path: Path = Field(default_factory=lambda: PROJECT_ROOT / "instance" / "medimind.db")
    database_url: str = Field(default="")

    def model_post_init(self, __context: Any) -> None:
        try:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        if not self.database_url:
            # Chuẩn hóa path SQLite bền vững tương thích cả Host và Docker
            db_file = self.database_path.resolve().as_posix()
            self.database_url = f"sqlite:///{db_file}"


class ServerSettings(BaseModel):
    """Cấu hình máy chủ web và môi trường thực thi."""
    env: str = Field(default="development")
    debug: bool = Field(default=False)
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    system_metrics_enabled: bool = Field(default=True)
    testing: bool = Field(default=False)

    @property
    def is_production(self) -> bool:
        return self.env.lower() in ("production", "prod")


class Settings(BaseSettings):
    """Cấu hình tổng hợp toàn bộ hệ thống MediMind Clinical Engine."""
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False
    )

    # Core raw environment mappings
    env: str = Field(default="development", validation_alias="FLASK_ENV")
    app_env: str = Field(default="development", validation_alias="ENV")
    app_env_explicit: Optional[str] = Field(default=None, validation_alias="APP_ENV")
    debug: bool = Field(default=False, validation_alias="FLASK_DEBUG")
    port: int = Field(default=8000, validation_alias="PORT")
    host: str = Field(default="0.0.0.0", validation_alias="HOST")
    testing_flag: bool = Field(default=False, validation_alias="TESTING")

    secret_key: Optional[str] = Field(default=None, validation_alias="SECRET_KEY")
    database_url: Optional[str] = Field(default=None, validation_alias="DATABASE_URL")
    session_cookie_secure: bool = Field(default=False, validation_alias="SESSION_COOKIE_SECURE")
    session_lifetime_minutes: int = Field(default=120, validation_alias="SESSION_LIFETIME_MINUTES")
    trust_proxy_headers: bool = Field(default=False, validation_alias="TRUST_PROXY_HEADERS")
    trusted_proxy_count: int = Field(default=1, validation_alias="TRUSTED_PROXY_COUNT")
    ocr_draft_retention_hours: int = Field(default=24, validation_alias="OCR_DRAFT_RETENTION_HOURS")
    temp_upload_retention_hours: int = Field(default=24, validation_alias="TEMP_UPLOAD_RETENTION_HOURS")
    seed_demo_accounts: bool = Field(default=False, validation_alias="SEED_DEMO_ACCOUNTS")
    dev_seed_users: bool = Field(default=False, validation_alias="DEV_SEED_USERS")
    cors_allowed_origins: str = Field(default="", validation_alias="CORS_ALLOWED_ORIGINS")

    gemini_api_key: Optional[str] = Field(default=None, validation_alias="GEMINI_API_KEY")
    google_api_key: Optional[str] = Field(default=None, validation_alias="GOOGLE_API_KEY")
    gemini_chat_api_key: Optional[str] = Field(default=None, validation_alias="GEMINI_CHAT_API_KEY")
    gemini_nutrition_api_key: Optional[str] = Field(default=None, validation_alias="GEMINI_NUTRITION_API_KEY")
    gemini_model: str = Field(default="gemini-flash-lite-latest", validation_alias="GEMINI_MODEL")
    gemini_chat_model: Optional[str] = Field(default=None, validation_alias="GEMINI_CHAT_MODEL")
    gemini_expansion_model: Optional[str] = Field(default=None, validation_alias="GEMINI_EXPANSION_MODEL")
    gemini_nutrition_model: str = Field(default="gemini-flash-lite-latest", validation_alias="GEMINI_NUTRITION_MODEL")
    ocr_model: str = Field(default="gemini-flash-lite-latest", validation_alias="OCR_MODEL")
    interpretation_model: str = Field(default="gemini-flash-lite-latest", validation_alias="INTERPRETATION_MODEL")

    gemini_generation_timeout_seconds: float = Field(default=25.0, validation_alias="GEMINI_GENERATION_TIMEOUT_SECONDS")
    query_expansion_timeout_seconds: float = Field(default=3.0, validation_alias="QUERY_EXPANSION_TIMEOUT_SECONDS")
    ocr_ai_timeout_seconds: float = Field(default=30.0, validation_alias="OCR_AI_TIMEOUT_SECONDS")

    ai_retry_max_attempts: int = Field(default=3, validation_alias="AI_RETRY_MAX_ATTEMPTS")
    ai_retry_base_delay_seconds: float = Field(default=0.5, validation_alias="AI_RETRY_BASE_DELAY_SECONDS")
    ai_retry_max_delay_seconds: float = Field(default=4.0, validation_alias="AI_RETRY_MAX_DELAY_SECONDS")

    ai_circuit_breaker_enabled: bool = Field(default=True, validation_alias="AI_CIRCUIT_BREAKER_ENABLED")
    ai_circuit_failure_threshold: int = Field(default=5, validation_alias="AI_CIRCUIT_FAILURE_THRESHOLD")
    ai_circuit_cooldown_seconds: float = Field(default=30.0, validation_alias="AI_CIRCUIT_COOLDOWN_SECONDS")

    rag_query_expansion_enabled: bool = Field(default=False, validation_alias="RAG_QUERY_EXPANSION_ENABLED")
    rag_query_expansion_provider: str = Field(default="gemini", validation_alias="RAG_QUERY_EXPANSION_PROVIDER")
    rag_vector_search_enabled: bool = Field(default=False, validation_alias="RAG_VECTOR_SEARCH_ENABLED")
    rag_rerank_enabled: bool = Field(default=False, validation_alias="RAG_RERANK_ENABLED")
    rag_rerank_model_path: str = Field(default="BAAI/bge-reranker-v2-m3", validation_alias="RAG_RERANK_MODEL_PATH")
    rag_rerank_timeout_seconds: float = Field(default=3.0, validation_alias="RAG_RERANK_TIMEOUT_SECONDS")
    rag_acceptance_threshold: float = Field(default=0.35, validation_alias="RAG_ACCEPTANCE_THRESHOLD")
    rag_bm25_no_df_cutoff: bool = Field(default=True, validation_alias="RAG_BM25_NO_DF_CUTOFF")

    ingest_chunk_max_chars: int = Field(default=2000, validation_alias="INGEST_CHUNK_MAX_CHARS")
    ingest_chunk_overlap_chars: int = Field(default=200, validation_alias="INGEST_CHUNK_OVERLAP_CHARS")
    ingest_min_chunk_chars: int = Field(default=200, validation_alias="INGEST_MIN_CHUNK_CHARS")
    ingest_batch_size: int = Field(default=50, validation_alias="INGEST_BATCH_SIZE")
    ingest_chunking_version: str = Field(default="v2_sentence_contextual", validation_alias="INGEST_CHUNKING_VERSION")
    ingest_embedding_model: str = Field(default="all-MiniLM-L6-v2", validation_alias="INGEST_EMBEDDING_MODEL")
    ingest_embedding_dimension: int = Field(default=384, validation_alias="INGEST_EMBEDDING_DIMENSION")

    google_client_id: Optional[str] = Field(default=None, validation_alias="GOOGLE_CLIENT_ID")
    google_client_secret: Optional[str] = Field(default=None, validation_alias="GOOGLE_CLIENT_SECRET")
    google_redirect_uri: Optional[str] = Field(default=None, validation_alias="GOOGLE_REDIRECT_URI")
    google_maps_api_key: Optional[str] = Field(default=None, validation_alias="GOOGLE_MAPS_API_KEY")

    twilio_account_sid: Optional[str] = Field(default=None, validation_alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: Optional[str] = Field(default=None, validation_alias="TWILIO_AUTH_TOKEN")
    twilio_phone_number: Optional[str] = Field(default=None, validation_alias="TWILIO_PHONE_NUMBER")
    speedsms_auth_token: Optional[str] = Field(default=None, validation_alias="SPEEDSMS_AUTH_TOKEN")

    smtp_server: Optional[str] = Field(default=None, validation_alias="SMTP_SERVER")
    smtp_port: int = Field(default=587, validation_alias="SMTP_PORT")
    smtp_username: Optional[str] = Field(default=None, validation_alias="SMTP_USERNAME")
    smtp_password: Optional[str] = Field(default=None, validation_alias="SMTP_PASSWORD")
    smtp_sender_name: str = Field(default="MediMind AI", validation_alias="SMTP_SENDER_NAME")
    smtp_use_tls: bool = Field(default=True, validation_alias="SMTP_USE_TLS")

    system_metrics_enabled: bool = Field(default=True, validation_alias="SYSTEM_METRICS_ENABLED")

    # Composite Sub-domain namespaces
    gemini: GeminiSettings = Field(default_factory=GeminiSettings)
    retry: RetrySettings = Field(default_factory=RetrySettings)
    circuit_breaker: CircuitBreakerSettings = Field(default_factory=CircuitBreakerSettings)
    rag: RAGSettings = Field(default_factory=RAGSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    messaging: MessagingSettings = Field(default_factory=MessagingSettings)
    paths: PathSettings = Field(default_factory=PathSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    ingestion: IngestionSettings = Field(default_factory=IngestionSettings)

    def model_post_init(self, __context: Any) -> None:
        effective_env = self.app_env_explicit or (self.app_env if self.app_env != "development" else self.env)
        self.server.env = effective_env
        self.server.debug = self.debug
        self.server.host = self.host
        self.server.port = self.port
        self.server.testing = self.testing_flag
        self.server.system_metrics_enabled = self.system_metrics_enabled

        # Resolve primary Gemini API key
        resolved_key = (self.gemini_api_key or self.google_api_key or "").strip() or None
        self.gemini.api_key = resolved_key
        self.gemini.chat_api_key = (self.gemini_chat_api_key or "").strip() or None
        self.gemini.nutrition_api_key = (self.gemini_nutrition_api_key or "").strip() or None

        self.gemini.chat_model = (self.gemini_chat_model or self.gemini_model or "gemini-flash-lite-latest").strip()
        self.gemini.expansion_model = (self.gemini_expansion_model or self.gemini.chat_model).strip()
        self.gemini.nutrition_model = self.gemini_nutrition_model.strip()
        self.gemini.ocr_model = self.ocr_model.strip()
        self.gemini.interpretation_model = self.interpretation_model.strip()

        self.gemini.timeout_chat = self.gemini_generation_timeout_seconds
        self.gemini.timeout_expansion = self.query_expansion_timeout_seconds
        self.gemini.timeout_ocr = self.ocr_ai_timeout_seconds

        self.retry.max_attempts = self.ai_retry_max_attempts
        self.retry.base_delay_seconds = self.ai_retry_base_delay_seconds
        self.retry.max_delay_seconds = self.ai_retry_max_delay_seconds

        self.circuit_breaker.enabled = self.ai_circuit_breaker_enabled
        self.circuit_breaker.failure_threshold = self.ai_circuit_failure_threshold
        self.circuit_breaker.cooldown_seconds = self.ai_circuit_cooldown_seconds

        self.rag.query_expansion_enabled = self.rag_query_expansion_enabled
        self.rag.query_expansion_provider = self.rag_query_expansion_provider
        self.rag.query_expansion_timeout_seconds = self.query_expansion_timeout_seconds
        self.rag.vector_search_enabled = self.rag_vector_search_enabled
        self.rag.rerank_enabled = self.rag_rerank_enabled
        self.rag.rerank_model_path = self.rag_rerank_model_path
        self.rag.rerank_timeout_seconds = self.rag_rerank_timeout_seconds
        self.rag.acceptance_threshold = self.rag_acceptance_threshold
        self.rag.bm25_no_df_cutoff = self.rag_bm25_no_df_cutoff

        self.ingestion.chunk_max_chars = self.ingest_chunk_max_chars
        self.ingestion.chunk_overlap_chars = self.ingest_chunk_overlap_chars
        self.ingestion.min_chunk_chars = self.ingest_min_chunk_chars
        self.ingestion.hard_max_chars = 2200
        self.ingestion.batch_size = self.ingest_batch_size
        self.ingestion.chunking_version = self.ingest_chunking_version
        self.ingestion.embedding_model = self.ingest_embedding_model
        self.ingestion.embedding_dimension = self.ingest_embedding_dimension

        self.security.secret_key = self.secret_key
        self.security.session_cookie_secure = self.session_cookie_secure
        self.security.session_lifetime_minutes = self.session_lifetime_minutes
        self.security.trust_proxy_headers = self.trust_proxy_headers
        self.security.trusted_proxy_count = max(1, self.trusted_proxy_count)
        self.security.ocr_draft_retention_hours = self.ocr_draft_retention_hours
        self.security.temp_upload_retention_hours = self.temp_upload_retention_hours
        self.security.seed_demo_accounts = self.seed_demo_accounts
        self.security.dev_seed_users = self.dev_seed_users

        raw_cors = (self.cors_allowed_origins or os.getenv("CORS_ALLOWED_ORIGINS") or "").strip()
        if raw_cors:
            origins = [o.strip() for o in raw_cors.split(",") if o.strip()]
        elif not self.server.is_production:
            origins = [
                "http://localhost:5000",
                "http://localhost:8000",
                "http://127.0.0.1:5000",
                "http://127.0.0.1:8000",
            ]
        else:
            origins = []
        self.security.cors_allowed_origins = origins

        self.security.google_client_id = self.google_client_id
        self.security.google_client_secret = self.google_client_secret
        self.security.google_redirect_uri = self.google_redirect_uri
        self.security.google_maps_api_key = self.google_maps_api_key

        self.messaging.twilio_account_sid = self.twilio_account_sid
        self.messaging.twilio_auth_token = self.twilio_auth_token
        self.messaging.twilio_phone_number = self.twilio_phone_number
        self.messaging.speedsms_auth_token = self.speedsms_auth_token
        self.messaging.smtp_server = self.smtp_server
        self.messaging.smtp_port = self.smtp_port
        self.messaging.smtp_username = self.smtp_username
        self.messaging.smtp_password = self.smtp_password
        self.messaging.smtp_sender_name = self.smtp_sender_name
        self.messaging.smtp_use_tls = self.smtp_use_tls

        # Database URL resolution
        if self.database_url:
            self.paths.database_url = self.database_url
        else:
            db_file = self.paths.database_path.resolve().as_posix()
            self.paths.database_url = f"sqlite:///{db_file}"

    def get_effective_secret_key(self, testing: bool = False) -> str:
        """
        Lấy SECRET_KEY an toàn theo chính sách Phase 5.4:
        1. Explicit SECRET_KEY trong .env -> dùng ngay.
        2. Production (và không testing) thiếu SECRET_KEY -> raise RuntimeError ngay lập tức.
        3. Local dev thiếu SECRET_KEY -> dùng stable fallback xác định (không xoay session ngẫu nhiên) + log warning.
        """
        key = (self.security.secret_key or os.getenv("SECRET_KEY") or "").strip()
        if key:
            return key

        is_prod = self.server.is_production or os.getenv("FLASK_ENV") == "production" or os.getenv("ENV") == "production"
        if is_prod and not (testing or self.server.testing):
            raise RuntimeError("Yêu cầu cấu hình SECRET_KEY an toàn trong môi trường Production!")

        # VULN-07 FIX: Replace static hard-coded fallback with per-process random key.
        # Sessions are invalidated on each restart (acceptable for dev).
        import secrets as _secrets
        _random_dev_key = _secrets.token_hex(32)
        logger.warning(
            "CẢNH BÁO BẢO MẬT [VULN-07]: Không tìm thấy SECRET_KEY trong cấu hình! "
            "Đang sử dụng per-process random secret key cho phiên chạy này — "
            "mọi session sẽ bị vô hiệu khi khởi động lại. "
            "Vui lòng thiết lập SECRET_KEY rõ ràng trong file .env để ổn định session."
        )
        return _random_dev_key

    def __repr__(self) -> str:
        return (
            f"<Settings env={self.server.env} "
            f"database_url={self.paths.database_url} "
            f"gemini_model={self.gemini.chat_model}>"
        )


_settings_instance: Optional[Settings] = None


def get_settings() -> Settings:
    """Singleton getter trả về cấu hình ứng dụng MediMind."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance


def reset_settings() -> Settings:
    """Đặt lại singleton cấu hình (dành riêng cho Unit Testing)."""
    global _settings_instance
    _settings_instance = Settings()
    return _settings_instance


# Convenience export
settings = get_settings()
