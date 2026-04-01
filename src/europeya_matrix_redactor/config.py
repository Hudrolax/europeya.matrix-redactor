from __future__ import annotations

import logging
from pathlib import Path

from croniter import croniter
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

DEFAULT_EVENT_TYPE_ALLOWLIST = (
    "m.room.encrypted",
    "m.room.message",
    "m.reaction",
)

VALID_LOG_LEVELS = {
    "CRITICAL",
    "ERROR",
    "WARNING",
    "INFO",
    "DEBUG",
    "NOTSET",
}


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        enable_decoding=False,
        extra="ignore",
        populate_by_name=True,
    )

    synapse_base_url: str = Field(alias="SYNAPSE_BASE_URL", min_length=1)
    synapse_db_url: str = Field(alias="SYNAPSE_DB_URL", min_length=1)
    ttl_hours: int = Field(default=24, alias="TTL_HOURS", gt=0)
    cron_schedule: str = Field(default="0 5 * * *", alias="CRON_SCHEDULE", min_length=1)
    timezone: str = Field(default="UTC", alias="TZ", min_length=1)
    dry_run: bool = Field(default=False, alias="DRY_RUN")
    redaction_reason: str = Field(default="Expired by policy", alias="REDACTION_REASON", min_length=1)
    batch_size: int = Field(default=200, alias="BATCH_SIZE", gt=0)
    max_concurrent_senders: int = Field(default=8, alias="MAX_CONCURRENT_SENDERS", gt=0)
    request_timeout_seconds: float = Field(default=15.0, alias="REQUEST_TIMEOUT_SECONDS", gt=0)
    max_retries: int = Field(default=3, alias="MAX_RETRIES", ge=0)
    rate_limit_sleep_ms: int = Field(default=0, alias="RATE_LIMIT_SLEEP_MS", ge=0)
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    app_state_db_url: str = Field(
        default="sqlite+pysqlite:////app/var/state.db",
        alias="APP_STATE_DB_URL",
        min_length=1,
    )
    lock_file_path: Path = Field(default=Path("/app/var/run.lock"), alias="LOCK_FILE_PATH")
    event_type_allowlist: tuple[str, ...] = Field(
        default=DEFAULT_EVENT_TYPE_ALLOWLIST,
        alias="EVENT_TYPE_ALLOWLIST",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Mounted .env must win over container env so docker compose restart
        # picks up fresh file contents without recreating the container.
        return init_settings, dotenv_settings, env_settings, file_secret_settings

    @field_validator("synapse_base_url")
    @classmethod
    def _normalize_base_url(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("cron_schedule")
    @classmethod
    def _validate_cron(cls, value: str) -> str:
        if not croniter.is_valid(value):
            raise ValueError("CRON_SCHEDULE must be a valid cron expression")
        return value

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in VALID_LOG_LEVELS:
            raise ValueError(
                f"LOG_LEVEL must be one of: {', '.join(sorted(VALID_LOG_LEVELS))}",
            )
        return normalized

    @field_validator("event_type_allowlist", mode="before")
    @classmethod
    def _normalize_allowlist(cls, value: object) -> tuple[str, ...]:
        if value is None:
            return DEFAULT_EVENT_TYPE_ALLOWLIST
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",")]
        elif isinstance(value, (tuple, list, set)):
            items = [str(item).strip() for item in value]
        else:
            raise TypeError("EVENT_TYPE_ALLOWLIST must be a comma-separated string or sequence")

        normalized = tuple(item for item in items if item)
        if not normalized:
            raise ValueError("EVENT_TYPE_ALLOWLIST cannot be empty")
        return normalized


def load_config(env_file: str | Path | None = None, **overrides: object) -> AppConfig:
    if env_file is None:
        return AppConfig(**overrides)
    return AppConfig(_env_file=str(env_file), **overrides)


def validate_logging_level(level_name: str) -> int:
    return logging.getLevelName(level_name)
