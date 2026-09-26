"""Decision-card export for WhatsApp. Plain Markdown, no API keys."""

from __future__ import annotations

from app.format import inr, pct, verdict_title
from app.models import Report
from app.states import STATE_NAMES


def to_markdown(report: Report) -> str:
    decision = report.decision
    demand = report.demand
    competition = report.competition
    lines = [
        f"# Bazaar Radar — {report.keyword}",
        "",
        f"**Verdict: {verdict_title(decision.verdict)}** · confidence {decision.confidence}",
        "",
        f"- Category: {report.category}",
        f"- Your target price: {inr(report.target_price)}",
        f"- Suggested band: {decision.price_label or 'none'}",
        f"- Head term: {report.head_term}",
        (
            "- States you ship to: "
            + ", ".join(STATE_NAMES.get(code, code) for code in report.states_served)
        ),
        "",
        "## Why",
        "",
    ]
    for item in decision.why:
        lines.append(f"- {item.text}")
    lines += [
        "",
        "## Stock this",
        "",
        f"- Price band: {decision.price_label or 'no band recommended'}",
        "- States: " + (", ".join(decision.states) or "—"),
        "- Listing keywords: " + (", ".join(decision.keywords) or "—"),
        "- Fix these complaints: " + ("; ".join(decision.complaints) or "—"),
        "",
        "## Demand",
        "",
        (
            f"- Momentum: {demand.momentum:.2f}× ({demand.momentum_label})"
            if demand.momentum is not None
            else "- Momentum: unknown"
        ),
        f"- Source: {demand.momentum_source}",
        f"- {demand.peak_phrase}",
    ]
    if demand.projected_label:
        lines.append(f"- A similar peak this season would begin around {demand.projected_label}.")
    if demand.state_warning:
        lines.append(f"- {demand.state_warning}")
    lines += ["", "Top states:", ""]
    for state in demand.states[:8]:
        mark = " (you ship here)" if state.served else ""
        lines.append(f"- {state.location}: {state.value}{mark}")
    lines += ["", "## Competition", ""]
    lines.append(f"- Amazon sponsored share: {pct(competition.sponsored_share)}")
    lines.append(f"- Bought-in-past-month coverage: {competition.bought_coverage:.0%}")
    lines.append(f"- Outlier prices removed: {competition.outliers_removed}")
    lines.append("")
    for band in competition.bands:
        flags = []
        if band.whitespace:
            flags.append("white space")
        if band.quality_gap:
            flags.append("quality gap")
        if band.contains_target:
            flags.append("your price")
        suffix = f" — {', '.join(flags)}" if flags else ""
        rating = (
            f"{band.median_rating:.1f}★" if band.median_rating is not None else "no Amazon rating"
        )
        lines.append(
            f"- {band.label}: {band.count} listings, {rating}, "
            f"bought proxy {band.bought_sum:,}{suffix}"
        )
    if competition.merchants:
        lines += ["", "Where Shopping India lists it:", ""]
        for merchant in competition.merchants:
            quick = " · quick commerce" if merchant.quick else ""
            lines.append(
                f"- {merchant.name}: {merchant.count} listings, median {inr(merchant.median_price)}{quick}"
            )
    if report.ads:
        lines += ["", "## Ad pressure", ""]
        for ad in report.ads:
            formats = ", ".join(f"{name} {count}" for name, count in ad.formats.items())
            lines.append(
                f"- {ad.domain}: {ad.total_results:,} creatives in India "
                f"({ad.advertiser}). Last shown {ad.last_shown_label or '—'}. Formats: {formats}."
            )
    if report.complaints:
        lines += ["", "## Complaints to beat", ""]
        for row in report.complaints:
            lines.append(
                f"- {row.theme}: {row.negative} negative of {row.total} mentions ({row.sentiment}). {row.summary}"
            )
    lines += ["", "## Limits", ""]
    for note in decision.limitations:
        lines.append(f"- {note}")
    for note in report.notes:
        lines.append(f"- {note}")
    usage = report.usage
    lines += [
        "",
        "## SerpApi usage",
        "",
        (
            f"This report read {usage.served} searches "
            f"({usage.fixture} fixtures, {usage.cache} cache, {usage.live} live). "
            f"Missing in this mode: {usage.missing}. Blocked: {usage.blocked}."
        ),
        "",
        "Evidence:",
        "",
    ]
    for item in report.evidence:
        ident = item.search_id or item.source
        lines.append(f"- {item.purpose} · `{item.engine}` · {item.source} · {ident}")
    lines.append("")
    return "\n".join(lines)
