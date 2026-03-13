"""
WebSocket client for Upbit real-time streams.

- Public URL: wss://api.upbit.com/websocket/v1
- Messages are bytes; MUST decode to utf-8 before JSON parse.
- NDJSON to stdout (one JSON object per line, flush=True).
- Optional --count / --duration for agent auto-termination.
- Ping/pong keep-alive; reconnect with exponential backoff on disconnect.
- JWT in subscription payload is masked before any stderr/log output.
"""

from __future__ import annotations

import asyncio
import json
import signal
import sys
import uuid
from copy import deepcopy
from typing import Any, Callable, List, Optional

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

WS_PUBLIC_URL = "wss://api.upbit.com/websocket/v1"
WS_PRIVATE_URL = "wss://api.upbit.com/websocket/v1/private"
PING_INTERVAL = 20.0
PING_TIMEOUT = 20.0
RECONNECT_BASE_DELAY = 1.0
RECONNECT_MAX_DELAY = 60.0


def _looks_like_jwt(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parts = value.split(".")
    return len(parts) == 3 and all(len(p) > 0 for p in parts)


def mask_ws_payload(payload: List[Any]) -> List[Any]:
    """
    Return a deep copy of the subscription payload with any JWT/token values
    replaced by '***' so it is safe to log or print to stderr.
    """
    out = deepcopy(payload)

    def mask_obj(obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, str) and (
                    k in ("token", "jwt", "authorization", "Authorization")
                    or (k.lower().endswith("token") and _looks_like_jwt(v))
                    or _looks_like_jwt(v)
                ):
                    obj[k] = "***"
                else:
                    mask_obj(v)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                if isinstance(item, str) and _looks_like_jwt(item):
                    obj[i] = "***"
                else:
                    mask_obj(item)

    mask_obj(out)
    return out


def build_subscription_payload(
    stream_type: str,
    codes: List[str],
    *,
    format_type: str = "DEFAULT",
    token: Optional[str] = None,
) -> List[Any]:
    """
    Build the JSON array payload for Upbit WebSocket subscription.
    Format: [ {"ticket": "uuid"}, {"type": "<type>", "codes": [...]}, {"format": "DEFAULT"} ]
    For private streams, token is included in the payload per Upbit spec; must be masked when logging.
    """
    ticket = str(uuid.uuid4())
    payload: List[Any] = [
        {"ticket": ticket},
        {"type": stream_type, "codes": codes} if codes else {"type": stream_type},
        {"format": format_type},
    ]
    if token is not None:
        payload.append({"token": token})
    return payload


async def connect_and_stream(
    stream_type: str,
    codes: List[str],
    *,
    format_type: str = "DEFAULT",
    token: Optional[str] = None,
    count: int = 0,
    duration_sec: float = 0,
    ping_interval: float = PING_INTERVAL,
    ping_timeout: float = PING_TIMEOUT,
    on_message: Optional[Callable[[Any], Optional[str]]] = None,
) -> None:
    """
    Connect to Upbit WebSocket, send subscription, and stream messages as NDJSON to stdout.
    - count: stop after this many messages (0 = unlimited).
    - duration_sec: stop after this many seconds (0 = unlimited).
    - on_message: optional callback(msg_dict) -> optional JSON string to print; if None, print msg_dict as-is.
    - Decodes bytes to utf-8 before parsing.
    - On disconnect, log warning to stderr and reconnect with exponential backoff until count/duration/signal.
    """
    url = WS_PRIVATE_URL if token else WS_PUBLIC_URL
    payload = build_subscription_payload(stream_type, codes, format_type=format_type, token=token)
    payload_masked = mask_ws_payload(payload)
    received = 0
    loop = asyncio.get_event_loop()
    start = loop.time()
    shutdown_event: asyncio.Event = asyncio.Event()

    def _request_shutdown() -> None:
        shutdown_event.set()

    try:
        loop.add_signal_handler(signal.SIGTERM, _request_shutdown)
    except (NotImplementedError, ValueError):
        pass

    def _check_limits() -> bool:
        if count > 0 and received >= count:
            shutdown_event.set()
            return True
        if duration_sec > 0 and (loop.time() - start) >= duration_sec:
            shutdown_event.set()
            return True
        return False

    def _graceful_exit(message: str = "Stream terminated gracefully.") -> None:
        err = json.dumps(
            {"success": True, "message": message},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        print(err, file=sys.stderr)
        sys.stderr.flush()

    delay = RECONNECT_BASE_DELAY
    while not shutdown_event.is_set():
        try:
            async with websockets.connect(
                url,
                ping_interval=ping_interval,
                ping_timeout=ping_timeout,
                close_timeout=5,
            ) as ws:
                await ws.send(json.dumps(payload, separators=(",", ":")))
                async for raw_message in ws:
                    if shutdown_event.is_set():
                        break
                    try:
                        if isinstance(raw_message, bytes):
                            text = raw_message.decode("utf-8")
                        else:
                            text = str(raw_message)
                        msg = json.loads(text)
                    except (json.JSONDecodeError, UnicodeDecodeError) as e:
                        err = json.dumps(
                            {
                                "success": False,
                                "error_code": "WS_DECODE_ERROR",
                                "message": str(e),
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                        print(err, file=sys.stderr)
                        sys.stderr.flush()
                        continue
                    line = on_message(msg) if on_message else json.dumps(msg, ensure_ascii=False, separators=(",", ":"))
                    if line is not None:
                        print(line, flush=True)
                    received += 1
                    if _check_limits():
                        break
        except ConnectionClosed as e:
            if shutdown_event.is_set():
                break
            warn = json.dumps(
                {
                    "success": False,
                    "error_code": "WS_CONNECTION_CLOSED",
                    "message": "WebSocket connection closed; reconnecting.",
                    "details": {"reason": str(e)},
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            print(warn, file=sys.stderr)
            sys.stderr.flush()
            await asyncio.sleep(min(delay, RECONNECT_MAX_DELAY))
            delay = min(delay * 2, RECONNECT_MAX_DELAY)
        except (WebSocketException, asyncio.TimeoutError, OSError) as e:
            if shutdown_event.is_set():
                break
            warn = json.dumps(
                {
                    "success": False,
                    "error_code": "WS_ERROR",
                    "message": "WebSocket error; reconnecting.",
                    "details": {"reason": str(e), "payload_masked": payload_masked},
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            print(warn, file=sys.stderr)
            sys.stderr.flush()
            await asyncio.sleep(min(delay, RECONNECT_MAX_DELAY))
            delay = min(delay * 2, RECONNECT_MAX_DELAY)
        else:
            break

    _graceful_exit()
