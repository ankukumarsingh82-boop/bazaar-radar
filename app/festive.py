"""Diwali dates used to align demand curves. 2025 and 2026 follow the build plan."""

from __future__ import annotations

from datetime import date, timedelta

# Lakshmi Puja / main Diwali day. 2025-10-20 and 2026-11-08 are the plan dates
# (some calendars list 21 Oct 2025).
DIWALI: dict[int, date] = {
    2021: date(2021, 11, 4),
    2022: date(2022, 10, 24),
    2023: date(2023, 11, 12),
    2024: date(2024, 11, 1),
    2025: date(2025, 10, 20),
    2026: date(2026, 11, 8),
}

# Sale window cited in the pitch: festive sales open around 8 Oct 2026.
SALE_WINDOW_OPENS = date(2026, 10, 8)


def diwali(year: int) -> date | None:
    return DIWALI.get(year)


def peak_window(year: int) -> tuple[date, date] | None:
    day = diwali(year)
    if day is None:
        return None
    return day - timedelta(days=21), day + timedelta(days=7)


def format_day(day: date) -> str:
    return f"{day.day} {day.strftime('%b %Y')}"
