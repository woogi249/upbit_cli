"""
Exchange (Private API) tests: auth failure, account balance, order place/cancel-all.

No real HTTP; all requests mocked via respx. Credentials injected via monkeypatch.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import respx
from typer.testing import CliRunner

from upbit_cli.main import app


def test_missing_credentials_auth_error(cli_runner: CliRunner) -> None:
    """Run 'upbit account balance' with get_credentials returning None; expect exit 3 and AUTH_ERROR in stderr."""
    with patch("upbit_cli.commands.account.get_credentials", return_value=None):
        result = cli_runner.invoke(app, ["account", "balance"])
    assert result.exit_code == 3
    err = json.loads(result.stderr)
    assert err.get("error_code") == "AUTH_ERROR"
    assert "success" in err and err["success"] is False


def test_account_balance_authorization_header_present(cli_runner: CliRunner) -> None:
    """Mock GET /v1/accounts; verify request includes Authorization: Bearer <token>."""
    captured = []

    def capture(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=[])

    with patch("upbit_cli.commands.account.get_credentials") as m:
        m.return_value = type("C", (), {"access_key": "ak", "secret_key": "sk"})()
        with respx.mock(assert_all_called=False) as router:
            router.get(url__regex=r"^https://api\.upbit\.com/v1/accounts").mock(side_effect=capture)
            result = cli_runner.invoke(app, ["account", "balance"])
    assert result.exit_code == 0
    assert len(captured) == 1
    auth = captured[0].headers.get("authorization") or captured[0].headers.get("Authorization")
    assert auth is not None and auth.startswith("Bearer ")


def test_account_balance_total_amount_and_hide_dust(cli_runner: CliRunner) -> None:
    """Mock GET /v1/accounts with KRW, BTC, and ETH (dust). Assert total_amount and ETH hidden with default --hide-dust."""
    sample_accounts = [
        {"currency": "KRW", "balance": "1000000.0", "locked": "0.0", "avg_buy_price": "0", "avg_buy_price_modified": False, "unit_currency": "KRW"},
        {"currency": "BTC", "balance": "0.5", "locked": "0.1", "avg_buy_price": "50000000", "avg_buy_price_modified": False, "unit_currency": "KRW"},
        {"currency": "ETH", "balance": "0.0", "locked": "0.0", "avg_buy_price": "0", "avg_buy_price_modified": False, "unit_currency": "KRW"},
    ]
    with patch("upbit_cli.commands.account.get_credentials") as m:
        m.return_value = type("C", (), {"access_key": "ak", "secret_key": "sk"})()
        with respx.mock(assert_all_called=False) as router:
            router.get(url__regex=r"^https://api\.upbit\.com/v1/accounts").mock(
                return_value=httpx.Response(200, json=sample_accounts)
            )
            result = cli_runner.invoke(app, ["account", "balance", "--hide-dust"])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed.get("success") is True
    data = parsed["data"]
    assert isinstance(data, list)
    currencies = [d["currency"] for d in data]
    assert "KRW" in currencies
    assert "BTC" in currencies
    assert "ETH" not in currencies
    for d in data:
        if d["currency"] == "KRW":
            assert "total_amount" in d
            assert float(d["total_amount"]) == 1000000.0
        if d["currency"] == "BTC":
            assert "total_amount" in d
            assert float(d["total_amount"]) == 0.6


def test_order_place_safety_limit_no_http_request(cli_runner: CliRunner) -> None:
    """Run order place with --max-total 50000000 but price*volume = 200000000; expect exit 1 and zero HTTP calls."""
    with patch("upbit_cli.commands.order.get_credentials") as m:
        m.return_value = type("C", (), {"access_key": "ak", "secret_key": "sk"})()
        with respx.mock(assert_all_called=False) as router:
            router.post(url__regex=r"^https://api\.upbit\.com/v1/orders").mock(
                return_value=httpx.Response(200, json={"uuid": "test"})
            )
            result = cli_runner.invoke(
                app,
                [
                    "order", "place",
                    "--market", "KRW-BTC",
                    "--side", "bid",
                    "--price", "100000000",
                    "--volume", "2",
                    "--max-total", "50000000",
                ],
            )
    assert result.exit_code == 1
    err = json.loads(result.stderr)
    assert err.get("error_code") == "SAFETY_LIMIT_EXCEEDED"
    assert len(router.calls) == 0


def test_order_place_sends_identifier(cli_runner: CliRunner) -> None:
    """Mock POST /v1/orders; run valid order place; assert request body contains identifier (UUID)."""
    bodies = []

    def capture(request: httpx.Request) -> httpx.Response:
        import json as _json
        bodies.append(_json.loads(request.content.decode()))
        return httpx.Response(200, json={"uuid": "order-uuid-123", "state": "wait"})

    with patch("upbit_cli.commands.order.get_credentials") as m:
        m.return_value = type("C", (), {"access_key": "ak", "secret_key": "sk"})()
        with respx.mock(assert_all_called=False) as router:
            router.post(url__regex=r"^https://api\.upbit\.com/v1/orders").mock(side_effect=capture)
            result = cli_runner.invoke(
                app,
                [
                    "order", "place",
                    "--market", "KRW-BTC",
                    "--side", "bid",
                    "--price", "50000000",
                    "--volume", "0.001",
                ],
            )
    assert result.exit_code == 0
    assert len(bodies) == 1
    body = bodies[0]
    assert "identifier" in body
    ident = body["identifier"]
    assert isinstance(ident, str) and len(ident) == 32 and ident.isalnum()


def test_order_cancel_all_calls_delete_twice(cli_runner: CliRunner) -> None:
    """Mock GET /v1/orders?state=wait with 2 orders; mock DELETE /v1/order; run cancel-all; assert DELETE called exactly twice."""
    wait_orders = [
        {"uuid": "uuid-1", "market": "KRW-BTC", "side": "bid", "state": "wait", "ord_type": "limit", "price": "100", "volume": "1"},
        {"uuid": "uuid-2", "market": "KRW-BTC", "side": "ask", "state": "wait", "ord_type": "limit", "price": "200", "volume": "0.5"},
    ]
    delete_calls = []

    def capture_delete(request: httpx.Request) -> httpx.Response:
        delete_calls.append(request)
        return httpx.Response(200, json={"uuid": "ok"})

    with patch("upbit_cli.commands.order.get_credentials") as m:
        m.return_value = type("C", (), {"access_key": "ak", "secret_key": "sk"})()
        with respx.mock(assert_all_called=False) as router:
            router.get(url__regex=r"^https://api\.upbit\.com/v1/orders").mock(
                return_value=httpx.Response(200, json=wait_orders)
            )
            router.delete(url__regex=r"^https://api\.upbit\.com/v1/order").mock(side_effect=capture_delete)
            result = cli_runner.invoke(app, ["order", "cancel-all", "--market", "KRW-BTC"])
    assert result.exit_code == 0
    assert len(delete_calls) == 2
