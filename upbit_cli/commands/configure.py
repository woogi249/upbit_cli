"""
Configure command: interactive prompt for access_key and secret_key, save to ~/.upbit/config.json.
"""

from __future__ import annotations

from pathlib import Path

import typer

from upbit_cli.auth import DEFAULT_CONFIG_PATH, UpbitCredentials, save_config

configure_app = typer.Typer(help="Configure Upbit API credentials (saved to ~/.upbit/config.json).")


@configure_app.callback(invoke_without_command=True)
def configure(
    ctx: typer.Context,
    config_path: Path = typer.Option(
        None,
        "--config-path",
        "-c",
        path_type=Path,
        help="Override config file path (default: ~/.upbit/config.json).",
    ),
) -> None:
    """
    Interactively set Upbit API credentials and save to config file.

    Prompts for access_key and secret_key (secret_key is masked). If the config
    file already exists, asks for confirmation before overwriting. File is
    written with permissions 0o600 (read/write owner only).
    """
    path = config_path or DEFAULT_CONFIG_PATH
    if path.exists():
        overwrite = typer.confirm(
            f"Config file already exists at {path}. Overwrite?",
            default=False,
        )
        if not overwrite:
            typer.echo("Aborted.", err=True)
            raise typer.Exit(0)
    access_key = typer.prompt("Upbit Access Key", hide_input=False)
    secret_key = typer.prompt("Upbit Secret Key", hide_input=True)
    if not access_key or not secret_key:
        typer.echo("Access key and secret key are required.", err=True)
        raise typer.Exit(1)
    creds = UpbitCredentials(access_key=access_key.strip(), secret_key=secret_key.strip())
    save_config(creds, path=path)
    typer.echo(f"Credentials saved to {path} (mode 0o600).", err=True)
