"""A small, defensive HTTP helper.

Every external call goes through :func:`get_json`, which guarantees:
  * a connect/read timeout,
  * bounded retries with exponential backoff,
  * a *graceful* failure: it returns ``(None, error_string)`` instead of
    raising, so a single bad source can never crash a run,
  * optional caching of the raw response in SQLite.

Keeping all network behaviour in one place keeps the collectors simple.
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

import httpx

DEFAULT_TIMEOUT = 20.0
DEFAULT_RETRIES = 3
BACKOFF_BASE = 1.5

_USER_AGENT = "dia-alpha-monitor/0.1 (+local research tool)"


def get_json(
    url: str,
    *,
    params: Optional[dict[str, Any]] = None,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    cache=None,
    cache_source: str = "",
    cache_key: str = "",
) -> tuple[Optional[Any], str]:
    """Fetch JSON, returning ``(data, error)``.

    On success ``error`` is an empty string. On failure ``data`` is ``None``
    and ``error`` describes what went wrong. Never raises for network/HTTP
    issues.
    """
    last_err = ""
    for attempt in range(1, retries + 1):
        try:
            headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
            resp = httpx.get(url, params=params, timeout=timeout, headers=headers)
            if resp.status_code == 429:
                # Rate limited: back off and retry.
                last_err = "HTTP 429 rate limited"
                time.sleep(BACKOFF_BASE**attempt)
                continue
            resp.raise_for_status()
            data = resp.json()
            if cache is not None and cache_source:
                try:
                    cache.cache_raw(
                        cache_source,
                        cache_key or url,
                        "ok",
                        json.dumps(data)[:2_000_000],
                    )
                except Exception:
                    # Caching must never break a collection run.
                    pass
            return data, ""
        except (httpx.HTTPError, ValueError) as exc:  # ValueError = bad JSON
            last_err = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                time.sleep(BACKOFF_BASE**attempt)
        except Exception as exc:  # pragma: no cover - defensive catch-all
            last_err = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                time.sleep(BACKOFF_BASE**attempt)

    if cache is not None and cache_source:
        try:
            cache.cache_raw(cache_source, cache_key or url, "error", last_err)
        except Exception:
            pass
    return None, last_err


def get_text(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
) -> tuple[Optional[str], str]:
    """GET a URL and return ``(text, error)`` — used for non-JSON (e.g. RSS/XML).

    Same graceful contract as :func:`get_json`: never raises for network/HTTP
    issues; on failure ``text`` is ``None`` and ``error`` is populated.
    """
    last_err = ""
    for attempt in range(1, retries + 1):
        try:
            headers = {"User-Agent": _USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml, */*"}
            resp = httpx.get(url, timeout=timeout, headers=headers, follow_redirects=True)
            if resp.status_code == 429:
                last_err = "HTTP 429 rate limited"
                time.sleep(BACKOFF_BASE**attempt)
                continue
            resp.raise_for_status()
            return resp.text, ""
        except httpx.HTTPError as exc:
            last_err = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                time.sleep(BACKOFF_BASE**attempt)
        except Exception as exc:  # pragma: no cover - defensive catch-all
            last_err = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                time.sleep(BACKOFF_BASE**attempt)
    return None, last_err


def post_json(
    url: str,
    payload: dict[str, Any],
    *,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
) -> tuple[Optional[Any], str]:
    """POST JSON and return ``(data, error)`` — used for JSON-RPC calls.

    Same graceful contract as :func:`get_json`: never raises for network/HTTP
    issues; on failure ``data`` is ``None`` and ``error`` is populated.
    """
    last_err = ""
    for attempt in range(1, retries + 1):
        try:
            headers = {"User-Agent": _USER_AGENT, "Content-Type": "application/json"}
            resp = httpx.post(url, json=payload, timeout=timeout, headers=headers)
            if resp.status_code == 429:
                last_err = "HTTP 429 rate limited"
                time.sleep(BACKOFF_BASE**attempt)
                continue
            resp.raise_for_status()
            return resp.json(), ""
        except (httpx.HTTPError, ValueError) as exc:
            last_err = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                time.sleep(BACKOFF_BASE**attempt)
        except Exception as exc:  # pragma: no cover - defensive catch-all
            last_err = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                time.sleep(BACKOFF_BASE**attempt)
    return None, last_err
