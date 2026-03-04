from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    bot_token: str

    # Database
    database_url: str = "postgresql+asyncpg://visa:visa@postgres:5432/visa_bot"
    database_url_sync: str = "postgresql://visa:visa@postgres:5432/visa_bot"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Encryption
    sessions_encryption_key: str = ""

    # Monitoring
    monitor_interval_min: int = 60
    monitor_interval_max: int = 180
    monitor_jitter: int = 15

    # Dedup
    slot_dedup_minutes: int = 30

    # Service accounts (fallback when user has no credentials)
    vfs_email: str = ""
    vfs_password: str = ""
    tls_email: str = ""
    tls_password: str = ""
    bls_email: str = ""
    bls_password: str = ""

    # VFS Global direct API token (from browser session)
    vfs_authorize: str = ""
    vfs_clientsource: str = ""
    vfs_route: str = ""  # e.g. "kaz/ru/aut"
    vfs_cf_clearance: str = ""  # Cloudflare cf_clearance cookie

    # Admin (receives alerts when token refresh fails)
    admin_user_id: int = 0

    # Logging
    log_level: str = "INFO"


settings = Settings()  # type: ignore[call-arg]
