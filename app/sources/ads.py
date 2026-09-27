"""Google Ads Transparency Center for India (region 2356)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.models import AdSignal

IST = ZoneInfo("Asia/Kolkata")


def search_params(domain: str, today: date) -> dict[str, str]:
    start = today - timedelta(days=30)
    return {
        "engine": "google_ads_transparency_center",
        "text": domain,
        "region": "2356",
        "start_date": start.strftime("%Y%m%d"),
        "end_date": today.strftime("%Y%m%d"),
        "num": "40",
    }


def normalize_ads(payload: dict, domain: str, today: date) -> AdSignal:
    info = payload.get("search_information") or {}
    total = info.get("total_results")
    creatives = payload.get("ad_creatives") or []
    formats: dict[str, int] = {}
    last_shown = None
    advertiser = domain
    for creative in creatives:
        fmt = str(creative.get("format") or "unknown")
        formats[fmt] = formats.get(fmt, 0) + 1
        shown = creative.get("last_shown")
        if isinstance(shown, (int, float)):
            last_shown = int(shown) if last_shown is None else max(last_shown, int(shown))
        if creative.get("advertiser"):
            advertiser = str(creative["advertiser"])
    label = None
    recent = False
    if last_shown:
        when = datetime.fromtimestamp(last_shown, IST)
        label = when.strftime("%d %b %Y")
        recent = (today - when.date()).days <= 7
    return AdSignal(
        domain=domain,
        advertiser=advertiser,
        total_results=int(total) if isinstance(total, (int, float)) else len(creatives),
        formats=formats,
        last_shown=last_shown,
        last_shown_label=label,
        recent=recent,
    )
