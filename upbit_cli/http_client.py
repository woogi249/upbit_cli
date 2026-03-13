"""
HTTP client for Upbit API: async httpx with tenacity backoff and standardized errors.

- Base URL: https://api.upbit.com/v1
- No real requests in tests: mock via respx.
- Retries on 429 and 5xx with exponential backoff.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

BASE_URL = "https://api.upbit.com/v1"


class UpbitAPIError(Exception):
    """
    Base exception for Upbit API failures.

    Attributes:
        error_code: Machine-friendly code (e.g. HTTP_429, NETWORK_ERROR).
        message: Human-readable message.
        status_code: HTTP status if applicable.
        details: Extra context (e.g. response body, Remaining-Req).
        exit_code: Recommended process exit code (1=general, 2=network, 3=auth).
    """

    def __init__(
        self,
        error_code: str,
        message: str,
        *,
        status_code: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
        exit_code: int = 1,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        self.exit_code = exit_code

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"error_code": self.error_code, "message": self.message}
        if self.status_code is not None:
            out["status_code"] = self.status_code
        if self.details:
            out["details"] = self.details
        return out


class NetworkError(UpbitAPIError):
    """Network or timeout failure; exit_code 2."""

    def __init__(self, message: str, *, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            error_code="NETWORK_ERROR",
            message=message,
            status_code=None,
            details=details,
            exit_code=2,
        )


class AuthError(UpbitAPIError):
    """Authentication or JWT error; exit_code 3."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            error_code="AUTH_ERROR",
            message=message,
            status_code=status_code,
            details=details,
            exit_code=3,
        )


class RetryableUpbitError(UpbitAPIError):
    """Transient error (429, 5xx) that tenacity will retry."""

    pass


async def _do_request(
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 10.0,
) -> Any:
    """Single HTTP request; raises RetryableUpbitError, UpbitAPIError, or NetworkError."""
    url = f"{BASE_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method=method.upper(),
                url=url,
                params=params,
                headers=headers,
            )
    except httpx.RequestError as exc:
        raise NetworkError(
            message=f"Network error: {exc.request.url!s}",
            details={"reason": str(exc)},
        ) from exc

    remaining_req = response.headers.get("Remaining-Req")

    if response.status_code in (429, 500, 502, 503, 504):
        try:
            body = response.json()
        except json.JSONDecodeError:
            body = {"raw": response.text}
        raise RetryableUpbitError(
            error_code=f"HTTP_{response.status_code}",
            message="Transient error from Upbit API (retryable).",
            status_code=response.status_code,
            details={"body": body, "remaining_req": remaining_req},
        )

    if not (200 <= response.status_code < 300):
        try:
            body = response.json()
        except json.JSONDecodeError:
            body = {"raw": response.text}
        raise UpbitAPIError(
            error_code=f"HTTP_{response.status_code}",
            message="Non-success response from Upbit API.",
            status_code=response.status_code,
            details={"body": body, "remaining_req": remaining_req},
        )

    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise UpbitAPIError(
            error_code="INVALID_JSON",
            message="Invalid JSON in Upbit response.",
            status_code=response.status_code,
            details={"raw": response.text},
        ) from exc


async def request_json(
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 10.0,
) -> Any:
    """
    Perform JSON request to Upbit with exponential backoff on 429 and 5xx.

    Raises NetworkError, AuthError, or UpbitAPIError with structured to_dict().
    """
    async for attempt in AsyncRetrying(
        retry=retry_if_exception_type(RetryableUpbitError),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
        stop=stop_after_attempt(5),
        reraise=True,
    ):
        with attempt:
            return await _do_request(
                method=method,
                path=path,
                params=params,
                headers=headers,
                timeout=timeout,
            )
    return None  # unreachable
