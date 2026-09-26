"""Google Trends: YoY timeseries, states, related queries, and a 5-year weekly curve."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from app.models import DailyPoint, RelatedQuery, StateInterest

_DATE = re.compile(
    r"([A-Za-z]{3,9})\s+(\d{1,2})(?:\s*[-–—]\s*(?:([A-Za-z]{3,9})\s+)?(\d{1,2}))?,?\s*(\d{4})"
)


def yoy_date_param(today: date) -> str:
    start = date(today.year, 8, 1)
    if start > today:
        start = today - timedelta(days=56)
    last_end = date(today.year - 1, today.month, today.day)
    last_start = date(start.year - 1, start.month, start.day)
    return (
        f"{last_start.isoformat()} {last_end.isoformat()},{start.isoformat()} {today.isoformat()}"
    )


def yoy_params(term: str, today: date) -> dict[str, str]:
    return {
        "engine": "google_trends",
        "data_type": "TIMESERIES",
        "geo": "IN",
        "q": f"{term},{term}",
        "date": yoy_date_param(today),
        "tz": "-330",
    }


def geo_params(term: str) -> dict[str, str]:
    return {
        "engine": "google_trends",
        "data_type": "GEO_MAP_0",
        "geo": "IN",
        "region": "REGION",
        "q": term,
        "tz": "-330",
    }


def related_params(term: str, window: str = "today 3-m") -> dict[str, str]:
    return {
        "engine": "google_trends",
        "data_type": "RELATED_QUERIES",
        "geo": "IN",
        "q": term,
        "date": window,
        "tz": "-330",
    }


def five_year_params(term: str) -> dict[str, str]:
    return {
        "engine": "google_trends",
        "data_type": "TIMESERIES",
        "geo": "IN",
        "q": term,
        "date": "today 5-y",
        "tz": "-330",
    }


def parse_trend_date(label: str) -> date | None:
    text = label.replace("\u2009", " ").replace("\u2013", "-").replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text).strip()
    match = _DATE.match(text)
    if not match:
        return None
    month, day, year = match.group(1), int(match.group(2)), int(match.group(5))
    for fmt in ("%b %d %Y", "%B %d %Y"):
        try:
            return datetime.strptime(f"{month} {day} {year}", fmt).date()
        except ValueError:
            continue
    return None


def normalize_yoy(payload: dict) -> list[DailyPoint]:
    """Multi-date TIMESERIES keeps date and timestamp on each value, not the point."""
    timeline = (payload.get("interest_over_time") or {}).get("timeline_data") or []
    points: list[DailyPoint] = []
    for point in timeline:
        values = point.get("values") or []
        # Single-date shape keeps the date on the point. Multi-date moves it onto values.
        point_date = parse_trend_date(str(point.get("date") or ""))
        for value in values:
            label = str(value.get("date") or point.get("date") or "")
            when = parse_trend_date(label) or point_date
            if when is None:
                continue
            extracted = value.get("extracted_value")
            number = float(extracted) if isinstance(extracted, (int, float)) else 0.0
            points.append(DailyPoint(when=when.isoformat(), value=number, series=str(when.year)))
    return points


def normalize_five_year(payload: dict, wanted: str) -> tuple[str, list[DailyPoint]]:
    timeline = (payload.get("interest_over_time") or {}).get("timeline_data") or []
    names: list[str] = []
    for point in timeline:
        for value in point.get("values") or []:
            query = str(value.get("query") or "")
            if query and query not in names:
                names.append(query)
        if names:
            break
    chosen = _choose_term(names, wanted)
    points: list[DailyPoint] = []
    if chosen is None:
        return wanted, points
    for point in timeline:
        when = parse_trend_date(str(point.get("date") or ""))
        if when is None:
            continue
        for value in point.get("values") or []:
            if str(value.get("query") or "") != chosen:
                continue
            if point.get("partial_data"):
                continue
            extracted = value.get("extracted_value")
            number = float(extracted) if isinstance(extracted, (int, float)) else 0.0
            points.append(DailyPoint(when=when.isoformat(), value=number, series="week"))
    return chosen, points


def normalize_geo(payload: dict, served: set[str]) -> list[StateInterest]:
    rows = []
    for item in payload.get("interest_by_region") or []:
        geo = str(item.get("geo") or "")
        value = item.get("extracted_value")
        number = int(value) if isinstance(value, (int, float)) else 0
        rows.append(
            StateInterest(
                geo=geo,
                location=str(item.get("location") or geo),
                value=number,
                served=geo in served,
            )
        )
    rows.sort(key=lambda row: row.value, reverse=True)
    return rows


def normalize_related(payload: dict) -> list[RelatedQuery]:
    block = payload.get("related_queries") or {}
    found: list[RelatedQuery] = []
    for kind in ("rising", "top"):
        for item in block.get(kind) or []:
            extracted = item.get("extracted_value")
            found.append(
                RelatedQuery(
                    query=str(item.get("query") or "").strip(),
                    value_label=str(item.get("value") or ""),
                    extracted_value=int(extracted) if isinstance(extracted, (int, float)) else 0,
                    kind=kind,
                )
            )
    return [row for row in found if row.query]


def _choose_term(names: list[str], wanted: str) -> str | None:
    if not names:
        return None
    wanted_l = wanted.lower().strip()
    for name in names:
        if name.lower() == wanted_l:
            return name
    for name in names:
        if wanted_l.startswith(name.lower() + " ") or name.lower().startswith(wanted_l + " "):
            return name
    return None
