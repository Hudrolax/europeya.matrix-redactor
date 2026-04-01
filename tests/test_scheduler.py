from __future__ import annotations

from europeya_matrix_redactor.cli import build_parser
from europeya_matrix_redactor.scheduler import render_crontab


def test_render_crontab_uses_custom_command() -> None:
    command = "python -m europeya_matrix_redactor.cli --env-file /app/.env run-once"

    rendered = render_crontab("0 * * * *", timezone="Europe/Moscow", command=command)

    assert rendered == f"TZ=Europe/Moscow\n0 * * * * {command}\n"


def test_parser_accepts_render_crontab_command_argument() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "--env-file",
            "/app/.env",
            "render-crontab",
            "--output",
            "/app/var/crontab",
            "--command",
            "python -m europeya_matrix_redactor.cli --env-file /app/.env run-once",
        ]
    )

    assert args.env_file == "/app/.env"
    assert args.command == "render-crontab"
    assert args.output == "/app/var/crontab"
    assert args.scheduler_command == "python -m europeya_matrix_redactor.cli --env-file /app/.env run-once"
