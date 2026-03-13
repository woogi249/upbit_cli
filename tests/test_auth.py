"""
Auth module tests: masking, config load/save, no real ~/.upbit writes.

Uses tmp_path and monkeypatch so the user's real config is never touched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from upbit_cli.auth import (
    UpbitCredentials,
    load_from_config,
    load_from_env,
    mask_secret,
    save_config,
)


class TestMaskSecret:
    """mask_secret must never expose full key in logs or errors."""

    def test_masks_long_value(self) -> None:
        assert mask_secret("abcd1234wxyz") == "abcd****wxyz"

    def test_short_value_all_stars(self) -> None:
        assert mask_secret("ab") == "**"

    def test_empty_returns_safe_placeholder(self) -> None:
        assert mask_secret("") == "***"

    def test_very_short_visible_prefix_suffix(self) -> None:
        # len 10: prefix 4 + **** + suffix 4 = abcd****ghij
        out = mask_secret("abcdefghij")
        assert out == "abcd****ghij"

    def test_no_raw_secret_in_output(self) -> None:
        secret = "my-super-secret-key-12345"
        masked = mask_secret(secret)
        assert secret not in masked
        assert "****" in masked


class TestLoadFromConfig:
    """load_from_config must not crash; use tmp_path to avoid real ~/.upbit."""

    def test_returns_none_when_file_does_not_exist(self, tmp_path: Path) -> None:
        path = tmp_path / "nonexistent" / "config.json"
        assert not path.exists()
        assert load_from_config(path=path) is None

    def test_returns_credentials_when_file_valid(self, tmp_path: Path) -> None:
        path = tmp_path / "config.json"
        path.write_text(
            json.dumps({"access_key": "ak", "secret_key": "sk"}, indent=2),
            encoding="utf-8",
        )
        creds = load_from_config(path=path)
        assert creds is not None
        assert isinstance(creds, UpbitCredentials)
        assert creds.access_key == "ak"
        assert creds.secret_key == "sk"

    def test_returns_none_when_file_invalid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "config.json"
        path.write_text("not json {", encoding="utf-8")
        assert load_from_config(path=path) is None

    def test_returns_none_when_file_missing_required_keys(self, tmp_path: Path) -> None:
        path = tmp_path / "config.json"
        path.write_text(json.dumps({"access_key": "ak"}), encoding="utf-8")
        assert load_from_config(path=path) is None


class TestUpbitCredentialsRepr:
    """Credentials must never expose raw secrets in __repr__/__str__."""

    def test_repr_does_not_contain_raw_secrets(self) -> None:
        c = UpbitCredentials(access_key="secret_access_123", secret_key="secret_key_456")
        r = repr(c)
        assert "secret_access_123" not in r
        assert "secret_key_456" not in r
        assert "****" in r or "*" in r


class TestSaveConfig:
    """save_config writes to given path; use tmp_path only."""

    def test_writes_valid_json_and_creates_dir(self, tmp_path: Path) -> None:
        cfg_dir = tmp_path / "upbit"
        path = cfg_dir / "config.json"
        assert not path.exists()
        creds = UpbitCredentials(access_key="ak", secret_key="sk")
        save_config(creds, path=path)
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["access_key"] == "ak"
        assert data["secret_key"] == "sk"


class TestLoadFromEnv:
    """load_from_env respects environment; use monkeypatch to avoid leaking real env."""

    def test_returns_none_when_vars_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("UPBIT_ACCESS_KEY", raising=False)
        monkeypatch.delenv("UPBIT_SECRET_KEY", raising=False)
        assert load_from_env() is None

    def test_returns_credentials_when_both_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("UPBIT_ACCESS_KEY", "env_ak")
        monkeypatch.setenv("UPBIT_SECRET_KEY", "env_sk")
        creds = load_from_env()
        assert creds is not None
        assert creds.access_key == "env_ak"
        assert creds.secret_key == "env_sk"

    def test_returns_none_when_one_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("UPBIT_ACCESS_KEY", "ak")
        monkeypatch.delenv("UPBIT_SECRET_KEY", raising=False)
        assert load_from_env() is None
