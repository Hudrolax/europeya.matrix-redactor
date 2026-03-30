from __future__ import annotations

from pathlib import Path


DEFAULT_SCHEDULER_COMMAND = "python -m europeya_matrix_redactor.cli run-once"


def render_crontab(
    schedule: str,
    *,
    timezone: str,
    command: str = DEFAULT_SCHEDULER_COMMAND,
) -> str:
    return f"TZ={timezone}\n{schedule} {command}\n"


def write_crontab(
    path: str | Path,
    schedule: str,
    *,
    timezone: str,
    command: str = DEFAULT_SCHEDULER_COMMAND,
) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_crontab(schedule, timezone=timezone, command=command), encoding="utf-8")
    return destination
