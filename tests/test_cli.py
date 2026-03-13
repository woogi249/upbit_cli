"""
CLI integration tests: agent-readable JSON guarantee, error standardization, no real HTTP.

Uses Typer CliRunner and respx to mock Upbit API. No network calls.
"""

from __future__ import annotations

import json

import httpx
import respx
from typer.testing import CliRunner

from upbit_cli.main import app


class TestAgentReadableJsonGuarantee:
    """Ensure stdout is strictly parseable JSON with no extraneous text."""

    def test_get_ticker_stdout_is_valid_json(
        self,
        cli_runner: CliRunner,
        sample_ticker_response: list,
    ) -> None:
        with respx.mock(assert_all_called=False) as router:
            router.get(url__regex=r"^https://api\.upbit\.com/v1/ticker").mock(
                return_value=httpx.Response(200, json=sample_ticker_response)
            )
            result = cli_runner.invoke(
                app,
                ["market", "get-ticker", "--market", "KRW-BTC", "--compact"],
            )
        assert result.exit_code == 0, f"stderr: {result.stderr}"
        parsed = json.loads(result.stdout)
        assert parsed.get("success") is True
        assert "data" in parsed
        assert isinstance(parsed["data"], list)
        assert len(parsed["data"]) >= 1
        first = parsed["data"][0]
        assert "market" in first and first["market"] == "KRW-BTC"
        assert "trade_price" in first
        stripped = result.stdout.strip()
        assert stripped.startswith("{") and stripped.endswith("}")

    def test_get_ticker_stdout_has_no_rich_or_logs(
        self,
        cli_runner: CliRunner,
        sample_ticker_response: list,
    ) -> None:
        with respx.mock(assert_all_called=False) as router:
            router.get(url__regex=r"^https://api\.upbit\.com/v1/ticker").mock(
                return_value=httpx.Response(200, json=sample_ticker_response)
            )
            result = cli_runner.invoke(
                app,
                ["market", "get-ticker", "--market", "KRW-BTC", "--compact"],
            )
        assert result.exit_code == 0
        stdout = result.stdout
        assert "\x1b" not in stdout
        assert stdout.strip().startswith("{")


class TestErrorStandardization:
    """Errors must be JSON on stderr, non-zero exit, stdout empty."""

    def test_429_returns_standardized_error_on_stderr(
        self,
        cli_runner: CliRunner,
    ) -> None:
        with respx.mock(assert_all_called=False) as router:
            router.get(url__regex=r"^https://api\.upbit\.com/v1/ticker").mock(
                return_value=httpx.Response(
                    429,
                    json={"error": {"message": "Too Many Requests"}},
                    headers={"Remaining-Req": "group=market; min=0; sec=0"},
                )
            )
            result = cli_runner.invoke(
                app,
                ["market", "get-ticker", "--market", "KRW-BTC", "--compact"],
            )
        assert result.exit_code != 0
        assert (result.stdout or "").strip() == ""
        err = json.loads(result.stderr)
        assert err.get("success") is False
        assert "error_code" in err
        assert "message" in err
        assert err.get("status_code") == 429 or "429" in str(err.get("error_code", ""))

    def test_network_error_exit_code_and_stderr(
        self,
        cli_runner: CliRunner,
    ) -> None:
        def _raise_connect_error(request: httpx.Request) -> None:
            raise httpx.ConnectError("Connection refused")

        with respx.mock(assert_all_called=False) as router:
            router.get(url__regex=r"^https://api\.upbit\.com/v1/ticker").mock(side_effect=_raise_connect_error)
            result = cli_runner.invoke(
                app,
                ["market", "get-ticker", "--market", "KRW-BTC", "--compact"],
            )
        assert result.exit_code != 0
        err = json.loads(result.stderr)
        assert err.get("success") is False
        assert "error_code" in err


class TestGetTickerNoCompact:
    """Raw (--no-compact) still returns valid JSON with expected shape."""

    def test_get_ticker_no_compact_returns_full_shape(
        self,
        cli_runner: CliRunner,
        sample_ticker_response: list,
    ) -> None:
        with respx.mock(assert_all_called=False) as router:
            router.get(url__regex=r"^https://api\.upbit\.com/v1/ticker").mock(
                return_value=httpx.Response(200, json=sample_ticker_response)
            )
            result = cli_runner.invoke(
                app,
                ["market", "get-ticker", "--market", "KRW-BTC", "--no-compact"],
            )
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed.get("success") is True
        assert "data" in parsed
        first = parsed["data"][0]
        assert "opening_price" in first
        assert "high_price" in first
        assert "low_price" in first
