"""Thin wrapper around the upstream toolkit client.

All queueing, authentication, framing and timeouts belong to the upstream
``zve10_terminal_client`` module. This wrapper only adds response validation and
error classification.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .errors import ActionError, UnknownResponse
from .upstream import Upstream


class ServiceTimeout(ActionError):
    """The upstream request timed out; a write may still be in progress."""


class ServiceRefused(ActionError):
    """The upstream service returned an error or refused the action."""


def _load_client(upstream: Upstream):
    host = str(upstream.host_dir)
    if host not in sys.path:
        sys.path.insert(0, host)
    import zve10_terminal_client as client  # type: ignore

    return client


def submit(upstream: Upstream, session_dir: Path, payload: dict, timeout: int = 360) -> dict:
    client = _load_client(upstream)
    try:
        answer = client.submit(Path(session_dir), payload, timeout=timeout)
    except Exception as exc:  # the upstream client raises its own timeout type
        if "timeout" in type(exc).__name__.lower() or isinstance(exc, TimeoutError):
            raise ServiceTimeout(f"service request timed out after {timeout}s: {exc!r}") from exc
        raise ActionError(f"service request failed: {exc!r}") from exc

    if not isinstance(answer, dict):
        raise UnknownResponse(f"expected a JSON object, got {type(answer).__name__}")
    if "error" in answer or "refused" in answer:
        raise ServiceRefused(f"upstream refused or failed the action: {answer!r}")
    return answer
