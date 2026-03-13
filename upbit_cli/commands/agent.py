"""
Agent integration: export-schema (OpenAI/Anthropic tool format), ai-help, mcp-serve placeholder.

Self-discoverable CLI for LLM agents; error responses include suggested_action.
"""

from __future__ import annotations

import json
import sys
from typing import Any, List

import typer

agent_app = typer.Typer(help="Agent integration: schema export, token-optimized help, MCP.")


def _openai_tools_schema() -> List[dict]:
    """OpenAI function calling / Anthropic tool format for upbit CLI commands."""
    def fn(name: str, description: str, parameters: dict) -> dict:
        return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}
    return [
        fn("market_get_ticker", "Get latest ticker for a market. Returns JSON with success and data.",
           {"type": "object", "properties": {"market": {"type": "string", "description": "e.g. KRW-BTC"}, "compact": {"type": "boolean", "default": True}}, "required": ["market"]}),
        fn("market_get_orderbook", "Get orderbook for a market.",
           {"type": "object", "properties": {"market": {"type": "string"}, "limit": {"type": "integer", "default": 5}, "compact": {"type": "boolean", "default": True}}, "required": ["market"]}),
        fn("market_list_markets", "List markets. Optionally filter by quote (KRW, USDT) before limit.",
           {"type": "object", "properties": {"quote": {"type": "string"}, "limit": {"type": "integer", "default": 50}, "compact": {"type": "boolean", "default": True}}}),
        fn("market_get_trades", "Get recent trades. Use sequential_id from response as cursor for next page.",
           {"type": "object", "properties": {"market": {"type": "string"}, "limit": {"type": "integer", "default": 10}, "cursor": {"type": "string"}, "to": {"type": "string", "description": "ISO 8601"}, "compact": {"type": "boolean", "default": True}}, "required": ["market"]}),
        fn("market_get_candles", "Get candles (seconds/minutes/days/weeks/months). Limit capped at 200.",
           {"type": "object", "properties": {"market": {"type": "string"}, "unit": {"type": "string", "enum": ["seconds", "minutes", "days", "weeks", "months"]}, "interval": {"type": "integer"}, "limit": {"type": "integer", "default": 5}, "to": {"type": "string", "description": "ISO 8601"}, "compact": {"type": "boolean", "default": True}}, "required": ["market"]}),
        fn("account_balance", "List account balances. Requires API credentials. total_amount = balance + locked; hide_dust excludes zero.",
           {"type": "object", "properties": {"hide_dust": {"type": "boolean", "default": True}, "compact": {"type": "boolean", "default": True}}}),
        fn("order_place", "Place an order. Uses client-side identifier for idempotency. --max-total caps order value (safety).",
           {"type": "object", "properties": {"market": {"type": "string"}, "side": {"type": "string", "enum": ["bid", "ask"]}, "ord_type": {"type": "string"}, "volume": {"type": "number"}, "price": {"type": "number"}, "max_total": {"type": "number", "default": 0}, "compact": {"type": "boolean", "default": True}}, "required": ["market", "side"]}),
        fn("order_list", "List orders by state (wait/done/cancel).",
           {"type": "object", "properties": {"state": {"type": "string", "default": "wait"}, "market": {"type": "string"}, "compact": {"type": "boolean", "default": True}}}),
        fn("stream_ticker", "Stream ticker as NDJSON. Use --count or --duration to avoid infinite run.",
           {"type": "object", "properties": {"market": {"type": "string"}, "count": {"type": "integer", "default": 0}, "duration": {"type": "integer", "default": 0}, "format_type": {"type": "string"}, "compact": {"type": "boolean", "default": True}}, "required": ["market"]}),
        fn("stream_orderbook", "Stream orderbook as NDJSON. Use --count or --duration to avoid infinite run.",
           {"type": "object", "properties": {"market": {"type": "string"}, "count": {"type": "integer", "default": 0}, "duration": {"type": "integer", "default": 0}, "format_type": {"type": "string"}, "compact": {"type": "boolean", "default": True}}, "required": ["market"]}),
    ]


@agent_app.command("export-schema")
def export_schema(
    format_type: str = typer.Option("openai", "--format", "-f", help="openai (default) or anthropic"),
) -> None:
    """Output OpenAI function calling / Anthropic tool JSON schema. Pipe into agent system prompt."""
    tools = _openai_tools_schema()
    out = {"tools": tools} if format_type.lower() == "openai" else {"tool_use": tools}
    print(json.dumps(out, ensure_ascii=False, indent=2))


def _ai_help_content() -> str:
    """Token-optimized help: command names and essential args only."""
    return json.dumps({
        "commands": [
            {"path": "market get-ticker", "args": ["--market"], "types": {"market": "str"}},
            {"path": "market get-orderbook", "args": ["--market", "--limit"], "types": {"market": "str", "limit": "int"}},
            {"path": "market list-markets", "args": ["--quote", "--limit"], "types": {"quote": "str|None", "limit": "int"}},
            {"path": "market get-trades", "args": ["--market", "--limit", "--cursor", "--to"], "types": {"market": "str", "limit": "int", "cursor": "str|None", "to": "str|None"}},
            {"path": "market get-candles", "args": ["--market", "--unit", "--limit", "--to"], "types": {"market": "str", "unit": "str", "limit": "int", "to": "str|None"}},
            {"path": "account balance", "args": ["--hide-dust", "--compact"], "types": {"hide_dust": "bool", "compact": "bool"}},
            {"path": "order place", "args": ["--market", "--side", "--ord-type", "--volume", "--price", "--max-total"], "types": {"market": "str", "side": "str", "volume": "float|None", "price": "float|None", "max_total": "float"}},
            {"path": "order list", "args": ["--state", "--market"], "types": {"state": "str", "market": "str|None"}},
            {"path": "stream ticker", "args": ["--market", "--count", "--duration"], "types": {"market": "str", "count": "int", "duration": "int"}},
            {"path": "stream orderbook", "args": ["--market", "--count", "--duration"], "types": {"market": "str", "count": "int", "duration": "int"}},
        ],
        "output": "stdout=JSON or JSONL (stream); stderr=errors with suggested_action",
    }, ensure_ascii=False, separators=(",", ":"))


@agent_app.command("help")
def ai_help() -> None:
    """Print token-optimized CLI usage as JSON (command names, args, types only). For LLM consumption."""
    print(_ai_help_content())


@agent_app.command("mcp-serve")
def mcp_serve() -> None:
    """Placeholder: future stdio-based MCP server. Reads JSON-RPC from stdin, responds on stdout."""
    err = json.dumps(
        {"success": False, "error_code": "NOT_IMPLEMENTED", "message": "MCP server not implemented. Architecture reserved for future stdio JSON-RPC."},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    print(err, file=sys.stderr)
    sys.stderr.flush()
    raise typer.Exit(1)
