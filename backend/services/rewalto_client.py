
"""Small Rewalto client with safe, typed errors for API routes."""

import re
from typing import Any

import requests

from backend.config import settings

BASE_URL = "https://api.rewalto.com"


class RewaltoError(Exception):
    """An upstream failure without credentials or response-body contents."""

    def __init__(
        self,
        code: str,
        upstream_status: int | None = None,
        retry_after: str | None = None,
    ) -> None:
        self.code = code
        self.upstream_status = upstream_status
        self.retry_after = retry_after
        super().__init__(code)


def get_headers() -> dict[str, str]:
    """Build authorization headers, failing clearly when configuration is absent."""
    api_key = settings.rewalto_api_key
    if api_key is None or not api_key.get_secret_value().strip():
        raise RewaltoError("missing_configuration")

    return {
        "Authorization": f"Bearer {api_key.get_secret_value()}",
        "Accept": "application/json",
    }


def _request_json(path: str, *, params: dict[str, Any] | None = None, timeout: int = 20) -> Any:
    """Make one Rewalto request and translate failures without exposing body text."""
    try:
        response = requests.get(
            f"{BASE_URL}{path}",
            headers=get_headers(),
            params=params,
            timeout=timeout,
        )
    except RewaltoError:
        raise
    except requests.Timeout as exc:
        raise RewaltoError("timeout") from exc
    except requests.RequestException as exc:
        raise RewaltoError("connection_error") from exc

    status_code = response.status_code
    retry_header = response.headers.get("Retry-After", "")
    retry_after = retry_header if re.fullmatch(r"[0-9]{1,6}", retry_header) else None

    if status_code == 401:
        raise RewaltoError("authentication", status_code)
    if status_code == 402:
        raise RewaltoError("credits_exhausted", status_code)
    if status_code == 403:
        raise RewaltoError("permission_denied", status_code)
    if status_code == 429:
        raise RewaltoError("rate_limited", status_code, retry_after)
    if not 200 <= status_code < 300:
        # Rewalto's error envelope documents a small set of machine codes.
        # Preserve only an allowlisted code; never return upstream text or data.
        error_code = None
        try:
            body = response.json()
            candidate = (body.get("error") or {}).get("code")
            if candidate in {"unavailable", "invalid_request"}:
                error_code = candidate
        except (ValueError, AttributeError, TypeError):
            pass
        raise RewaltoError(error_code or "upstream_error", status_code)

    try:
        return response.json()
    except (ValueError, requests.exceptions.JSONDecodeError) as exc:
        raise RewaltoError("invalid_response", status_code) from exc


def check_connection():
    """Verify API authentication; call only from an explicit operator command."""
    return _request_json("/v1/whoami", timeout=20)


def search_products(
    query: str,
    retailer: str = "blinkit",
    pincode: str | None = None,
    limit: int = 5,
    brand: str | None = None,
    mode: str = "words",
):
    """Search Rewalto listings and include their latest price."""

    params: dict[str, Any] = {
        "q": query,
        "retailer": retailer,
        "limit": limit,
        "include": "latest",
    }
    if pincode is not None:
        params["pincode"] = pincode
    if brand is not None:
        params["brand"] = brand
    if mode != "words":
        params["mode"] = mode
    return _request_json("/v1/data/listings/search", params=params, timeout=30)


def get_retailers():
    """Get retailers currently tracked by Rewalto."""
    return _request_json("/v1/data/retailers", timeout=20)
