"""
Authentication module: credentials loading, config file, secret masking, JWT generation.

- Environment variables (UPBIT_ACCESS_KEY, UPBIT_SECRET_KEY) take priority for AI agents.
- Optional ~/.upbit/config.json for interactive use; save_config uses chmod 0o600.
- Secrets are never logged or repr'd in plain text; use mask_secret() for any display.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import jwt
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_CONFIG_PATH = Path.home() / ".upbit" / "config.json"


def mask_secret(value: str, *, visible: int = 4) -> str:
    """
    Mask a secret so it is safe to log or display.

    Example: 'abcd1234wxyz' -> 'abcd****wxyz'.
    Never use raw secrets in stderr, stdout, or logs.
    """
    if not value:
        return "***"
    if len(value) <= visible * 2:
        return "*" * len(value)
    prefix = value[:visible]
    suffix = value[-visible:]
    return f"{prefix}{'*' * 4}{suffix}"


class UpbitCredentials(BaseModel):
    """Upbit API credentials for private endpoints (JWT). Quotation APIs do not require them."""

    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=False)

    access_key: str = Field(..., description="Upbit API access key.")
    secret_key: str = Field(..., description="Upbit API secret key.")

    def masked_dict(self) -> dict:
        """Return a dict with masked secrets for logging."""
        return {
            "access_key": mask_secret(self.access_key),
            "secret_key": mask_secret(self.secret_key),
        }

    def __repr__(self) -> str:
        return f"UpbitCredentials({self.masked_dict()})"

    def __str__(self) -> str:
        return self.__repr__()


def load_from_env() -> Optional[UpbitCredentials]:
    """
    Load credentials from environment variables.

    Expected: UPBIT_ACCESS_KEY, UPBIT_SECRET_KEY.
    Returns None if either is missing or empty.
    """
    access = os.getenv("UPBIT_ACCESS_KEY")
    secret = os.getenv("UPBIT_SECRET_KEY")
    if not access or not secret:
        return None
    return UpbitCredentials(access_key=access, secret_key=secret)


def load_from_config(path: Optional[Path] = None) -> Optional[UpbitCredentials]:
    """
    Load credentials from a JSON config file.

    Default path: ~/.upbit/config.json.
    Returns None if file does not exist, is invalid JSON, or missing required keys.
    """
    cfg_path = path or DEFAULT_CONFIG_PATH
    if not cfg_path.exists():
        return None
    try:
        with cfg_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    try:
        return UpbitCredentials.model_validate(data)
    except Exception:
        return None


def get_credentials(path: Optional[Path] = None) -> Optional[UpbitCredentials]:
    """
    Resolve credentials: environment variables first, then config file.

    Use this for any command that needs JWT (e.g. account, order).
    """
    creds = load_from_env()
    if creds is not None:
        return creds
    return load_from_config(path=path)


def save_config(credentials: UpbitCredentials, path: Optional[Path] = None) -> None:
    """
    Write credentials to config file and set file mode to 0o600 (read/write owner only).

    Creates parent directory if needed. Used by `upbit configure`.
    """
    cfg_path = path or DEFAULT_CONFIG_PATH
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "access_key": credentials.access_key,
        "secret_key": credentials.secret_key,
    }
    with cfg_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    try:
        cfg_path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600
    except OSError:
        pass  # e.g. Windows may not support chmod as on Unix


@dataclass
class JWTOptions:
    """Options for JWT generation (Upbit private API)."""

    nonce: Optional[str] = None
    query_hash: Optional[str] = None
    query_hash_alg: str = "SHA512"


def generate_jwt(credentials: UpbitCredentials, options: Optional[JWTOptions] = None) -> str:
    """
    Generate a JWT for Upbit private REST API.

    Payload includes access_key and nonce; optionally query_hash and query_hash_alg
    for endpoints that require query signing. Caller must never print this token.
    """
    opts = options or JWTOptions()
    payload = {
        "access_key": credentials.access_key,
        "nonce": opts.nonce or "",
    }
    if opts.query_hash is not None:
        payload["query_hash"] = opts.query_hash
        payload["query_hash_alg"] = opts.query_hash_alg
    token = jwt.encode(payload, credentials.secret_key, algorithm="HS256")
    return token if isinstance(token, str) else token.decode("utf-8")
