"""Startup notes. Importing this module must not raise."""

from __future__ import annotations

import logging
import re
from datetime import timedelta, timezone, tzinfo

logger = logging.getLogger("bazaar.startup")

# Process-wide notes that happen before a Settings object exists (for example timezone).
PROCESS_FALLBACKS: list[str] = []

_SECRET = re.compile(r"(?i)(api_key|key|token|secret)=([^\s&]+)")


def note(code: str, exc: BaseException | None = None, bucket: list[str] | None = None) -> None:
    """Record a fallback code. The code is safe to show; the exception is logged redacted."""
    if bucket is not None and code not in bucket:
        bucket.append(code)
    if exc is None:
        logger.error("startup fallback: %s", code)
        return
    logger.error("startup fallback: %s (%s)", code, _public_exc(exc))


def note_process(code: str, exc: BaseException | None = None) -> None:
    if code not in PROCESS_FALLBACKS:
        PROCESS_FALLBACKS.append(code)
    note(code, exc, bucket=None)


def public_fallbacks(extra: list[str] | None = None) -> list[str]:
    merged: list[str] = []
    for code in PROCESS_FALLBACKS + list(extra or []):
        if code not in merged:
            merged.append(code)
    return merged


def load_kolkata() -> tzinfo:
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("Asia/Kolkata")
    except Exception as exc:  # missing tzdata on a slim serverless image
        note_process("timezone:fixed-offset", exc)
        return timezone(timedelta(hours=5, minutes=30), name="IST")


def _public_exc(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}"
    text = _SECRET.sub(r"\1=REDACTED", text)
    if len(text) > 300:
        text = text[:300] + "…"
    return text


IST = load_kolkata()
