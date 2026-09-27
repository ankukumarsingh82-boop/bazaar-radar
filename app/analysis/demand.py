"""Momentum, days-to-peak, states, and listing keywords."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta
from statistics import mean

from app.festive import DIWALI, diwali, format_day, peak_window
from app.models import DailyPoint, RelatedQuery, StateInterest, WeeklyPoint, YearPeak

GENERIC_EXACT = {
    "diwali",
    "diwali 2024",
    "diwali 2025",
    "diwali 2026",
    "diwali 2027",
    "holi",
    "navratri",
    "gift",
    "gifts",
    "decoration",
    "decor",
}

AMBIGUOUS_HEADS = {"diya", "diwali"}
ZERO_DENSITY_LIMIT = 0.40


def zero_fraction(points: list[DailyPoint]) -> float:
    if not points:
        return 1.0
    by_series: dict[str, list[DailyPoint]] = defaultdict(list)
    for point in points:
        by_series[point.series].append(point)
    # A multi-date comparison is only as dense as its thinner year.
    fractions = [
        sum(1 for point in rows if point.value <= 0) / len(rows) for rows in by_series.values()
    ]
    return max(fractions) if fractions else 1.0


def to_weeks(points: list[DailyPoint]) -> dict[str, list[WeeklyPoint]]:
    grouped: dict[tuple[str, date], list[float]] = defaultdict(list)
    partials: set[tuple[str, date]] = set()
    for point in points:
        when = date.fromisoformat(point.when)
        monday = when - timedelta(days=when.weekday())
        grouped[(point.series, monday)].append(point.value)
        if point.series == "partial":
            partials.add((point.series, monday))
    out: dict[str, list[WeeklyPoint]] = defaultdict(list)
    for (series, monday), values in grouped.items():
        out[series].append(
            WeeklyPoint(
                week_start=monday.isoformat(),
                label=_label(monday),
                value=mean(values),
                partial=(series, monday) in partials,
            )
        )
    for series in out:
        out[series].sort(key=lambda row: row.week_start)
    return out


def momentum_ratio(recent: list[float], prior: list[float]) -> float | None:
    if not recent or not prior:
        return None
    prior_mean = mean(prior)
    if prior_mean <= 0:
        return None
    return mean(recent) / prior_mean


def momentum_from_yoy(weeks: dict[str, list[WeeklyPoint]]) -> tuple[float | None, str, str]:
    years = sorted(weeks)
    if len(years) < 2:
        return None, "", ""
    last_year, this_year = years[0], years[-1]
    last_rows = weeks[last_year]
    this_rows = weeks[this_year]
    n = min(4, len(last_rows), len(this_rows))
    if n == 0:
        return None, last_year, this_year
    ratio = momentum_ratio(
        [row.value for row in this_rows[-n:]],
        [row.value for row in last_rows[-n:]],
    )
    return ratio, last_year, this_year


def momentum_from_history(weeks: list[WeeklyPoint]) -> float | None:
    rows = [row for row in weeks if not row.partial]
    if len(rows) < 8:
        return None
    recent = rows[-4:]
    prior: list[WeeklyPoint] = []
    for row in recent:
        target = date.fromisoformat(row.week_start) - timedelta(days=364)
        nearest = min(
            rows, key=lambda item: abs((date.fromisoformat(item.week_start) - target).days)
        )
        if abs((date.fromisoformat(nearest.week_start) - target).days) <= 10:
            prior.append(nearest)
    if len(prior) < 3:
        return None
    return momentum_ratio([row.value for row in recent], [row.value for row in prior])


def label_momentum(ratio: float | None) -> str:
    if ratio is None:
        return "Unknown"
    if ratio >= 1.2:
        return "Rising"
    if ratio >= 0.8:
        return "Flat"
    return "Falling"


def align_yoy(
    weeks: dict[str, list[WeeklyPoint]],
) -> tuple[list[str], list[float], list[float], str, str]:
    years = sorted(weeks)
    if len(years) < 2:
        return [], [], [], "", ""
    last_year, this_year = years[0], years[-1]
    last_rows = weeks[last_year]
    this_rows = weeks[this_year]
    n = min(len(last_rows), len(this_rows))
    labels = [_label(date.fromisoformat(row.week_start)) for row in this_rows[:n]]
    return (
        labels,
        [round(row.value, 1) for row in last_rows[:n]],
        [round(row.value, 1) for row in this_rows[:n]],
        last_year,
        this_year,
    )


def days_to_peak(points: list[DailyPoint]) -> tuple[int | None, list[YearPeak], str, str]:
    """Return last year's offset, each year's peak, a phrase, and the projected 2026 date."""
    peaks: list[YearPeak] = []
    for year in (2023, 2024, 2025):
        window = peak_window(year)
        day = diwali(year)
        if window is None or day is None:
            continue
        start, end = window
        in_window = [
            point
            for point in points
            if start <= date.fromisoformat(point.when) <= end and point.series != "partial"
        ]
        if not in_window:
            continue
        best = max(in_window, key=lambda point: point.value)
        if best.value < 5:
            continue
        week = date.fromisoformat(best.when)
        peaks.append(
            YearPeak(
                year=year,
                week_label=_label(week),
                value=best.value,
                days_before=(day - week).days,
            )
        )
    last = next((peak for peak in peaks if peak.year == 2025), None)
    if last is None and peaks:
        last = peaks[-1]
    if last is None:
        return None, peaks, "No clear festive peak in the 5-year series.", ""
    phrase = _peak_phrase(last)
    projected = ""
    target = DIWALI.get(2026)
    if target is not None:
        projected_day = target - timedelta(days=last.days_before)
        projected = format_day(projected_day)
    return last.days_before, peaks, phrase, projected


def five_year_chart(
    points: list[DailyPoint], start: date = date(2023, 1, 1)
) -> tuple[list[str], list[float], list[dict[str, str]]]:
    rows = [
        point
        for point in points
        if date.fromisoformat(point.when) >= start and point.series != "partial"
    ]
    rows.sort(key=lambda point: point.when)
    labels = [_label(date.fromisoformat(point.when)) for point in rows]
    values = [point.value for point in rows]
    markers: list[dict[str, str]] = []
    for year, day in DIWALI.items():
        if day < start or not rows:
            continue
        if day > date.fromisoformat(rows[-1].when) + timedelta(days=6):
            continue
        containing = [
            point
            for point in rows
            if date.fromisoformat(point.when)
            <= day
            <= date.fromisoformat(point.when) + timedelta(days=6)
        ]
        if not containing:
            continue
        markers.append(
            {"label": _label(date.fromisoformat(containing[0].when)), "text": f"Diwali {year}"}
        )
    return labels, values, markers


def recommend_states(
    states: list[StateInterest], served: list[str]
) -> tuple[list[str], str | None]:
    ranked = sorted(states, key=lambda row: row.value, reverse=True)
    top10 = {row.geo for row in ranked[:10]}
    served_set = set(served)
    served_ranked = [row for row in ranked if row.geo in served_set]
    warning = None
    if served and not any(row.geo in top10 for row in served_ranked):
        warning = "None of the states you ship to are in the top 10 for this search."
    elif served:
        silent = [code for code in served if code not in {row.geo for row in states}]
        if silent and served_ranked:
            warning = (
                "Some states you ship to have no measurable Trends interest, so they count as 0."
            )
    # A state at 0 has no measurable interest, so it is never recommended.
    served_live = [row for row in served_ranked if row.value > 0]
    if served_live:
        pick = served_live[:3]
    elif served_ranked:
        # Every served state is 0. Do not fall through to states the seller does not ship to.
        pick = []
        warning = warning or "None of the states you ship to have measurable Trends interest."
    else:
        pick = [row for row in ranked if row.value > 0][:3] or ranked[:3]
        if not served:
            warning = warning or "No states were selected, so these are the national leaders."
    return [row.location for row in pick], warning


def is_generic(query: str) -> bool:
    text = query.lower().strip()
    if text in GENERIC_EXACT:
        return True
    return re.fullmatch(r"diwali\s+20\d{2}", text) is not None


def is_brand_only(query: str, brands: set[str]) -> bool:
    return query.lower().strip() in brands


def tag_queries(queries: list[RelatedQuery], brands: set[str]) -> list[RelatedQuery]:
    tagged: list[RelatedQuery] = []
    for row in queries:
        tag = None
        if is_generic(row.query):
            tag = "generic"
        elif is_brand_only(row.query, brands):
            tag = "brand"
        tagged.append(row.model_copy(update={"tag": tag}))
    return tagged


def listing_keywords(
    queries: list[RelatedQuery],
    variants: list[str],
    amazon_related: list[str],
    keyword: str,
    brands: set[str],
    limit: int = 5,
) -> list[str]:
    chosen: list[str] = []

    def add(text: str) -> None:
        cleaned = " ".join(text.split())
        if not cleaned or cleaned.lower() == keyword.lower():
            return
        if is_generic(cleaned) or is_brand_only(cleaned, brands):
            return
        if any(cleaned.lower() == have.lower() for have in chosen):
            return
        chosen.append(cleaned)

    rising = [row.query for row in queries if row.kind == "rising" and row.tag != "generic"]
    top = [row.query for row in queries if row.kind == "top" and row.tag != "generic"]
    for query in rising + top + variants + amazon_related:
        add(query)
        if len(chosen) >= limit:
            break
    return chosen[:limit]


def _peak_phrase(peak: YearPeak) -> str:
    when = _offset_phrase(peak.days_before)
    if 0 <= peak.days_before <= 6:
        return (
            f"Last year the peak week started {when} "
            f"(week of {peak.week_label}, inside Diwali week)."
        )
    return f"Last year demand peaked about {when} (week of {peak.week_label})."


def _offset_phrase(days: int) -> str:
    if days == 0:
        return "on Diwali"
    word = "day" if abs(days) == 1 else "days"
    if days > 0:
        return f"{days} {word} before Diwali"
    return f"{abs(days)} {word} after Diwali"


def _label(day: date) -> str:
    return f"{day.day} {day.strftime('%b')}"
