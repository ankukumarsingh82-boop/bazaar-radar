"""Deterministic GO / GO-with-positioning / CAUTION / SKIP rules."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models import WhyItem


class VerdictFacts(BaseModel):
    momentum: float | None = None
    momentum_label: str = "Unknown"
    whitespace_near: bool = False
    quality_gap_near: bool = False
    crowded: bool = False
    sponsored_share: float | None = None
    ads_pressure: str = "n/a"
    sparse: bool = False
    used_head_term: bool = False
    ambiguous_head: bool = False
    failed: list[str] = Field(default_factory=list)
    series_term: str = ""
    peak_phrase: str = ""
    price_label: str | None = None
    target_states: list[str] = Field(default_factory=list)
    state_warning: str | None = None


def ads_pressure(total_results: list[int], sponsored_share: float | None) -> str:
    if not total_results and sponsored_share is None:
        return "n/a"
    if any(total >= 500 for total in total_results):
        return "high"
    if sponsored_share is not None and sponsored_share > 0.50:
        return "high"
    if any(total >= 40 for total in total_results) or (sponsored_share or 0) >= 0.15:
        return "medium"
    return "low"


def decide(facts: VerdictFacts) -> str:
    falling = facts.momentum_label == "Falling"
    no_gap = not facts.whitespace_near and not facts.quality_gap_near
    sponsored_high = facts.sponsored_share is not None and facts.sponsored_share > 0.50
    ad_pressure = sponsored_high or facts.ads_pressure == "high"

    if falling and facts.crowded and no_gap:
        return "SKIP"
    if falling or ad_pressure:
        return "CAUTION"
    if (
        facts.whitespace_near
        and facts.momentum is not None
        and facts.momentum >= 1.0
        and not facts.sparse
    ):
        return "GO"
    if facts.quality_gap_near or facts.whitespace_near:
        return "GO-with-positioning"
    return "CAUTION"


def confidence(facts: VerdictFacts) -> str:
    score = 2
    if facts.sparse or facts.momentum is None:
        score -= 1
    if facts.ambiguous_head and facts.used_head_term:
        score -= 1
    if facts.failed:
        score -= 1
    return ("low", "medium", "high")[max(0, min(2, score))]


def why_items(facts: VerdictFacts, verdict: str) -> list[WhyItem]:
    items: list[WhyItem] = []
    if facts.momentum is None:
        items.append(
            WhyItem(
                text="Momentum is unknown because the Trends series is missing or too thin to compare.",
                anchor="demand",
            )
        )
    else:
        source = f" on “{facts.series_term}”" if facts.series_term else ""
        items.append(
            WhyItem(
                text=(
                    f"Momentum is {facts.momentum:.2f}× ({facts.momentum_label}){source}, "
                    "from weekly Trends versus the same weeks last year."
                ),
                anchor="demand",
            )
        )
    if facts.peak_phrase:
        items.append(WhyItem(text=facts.peak_phrase, anchor="demand"))
    if facts.state_warning:
        items.append(WhyItem(text=facts.state_warning, anchor="demand"))
    elif facts.target_states:
        items.append(
            WhyItem(
                text="Target states follow Google Trends interest inside the states you ship to.",
                anchor="demand",
            )
        )
    if facts.whitespace_near and facts.price_label:
        items.append(
            WhyItem(
                text=(
                    f"{facts.price_label} has more of the demand proxy than of the listings, "
                    "and few 4.2★ Amazon results."
                ),
                anchor="competition",
            )
        )
    elif facts.quality_gap_near and facts.price_label:
        items.append(
            WhyItem(
                text=f"{facts.price_label} is crowded with listings whose median rating is under 4.0 or short of 4.2★.",
                anchor="competition",
            )
        )
    elif facts.crowded:
        items.append(
            WhyItem(
                text="The band around your target price is crowded, with no white-space gap.",
                anchor="competition",
            )
        )
    if facts.sponsored_share is not None and facts.sponsored_share > 0.50:
        items.append(
            WhyItem(
                text=f"Amazon sponsored share is {facts.sponsored_share:.0%}, above the 50% caution line.",
                anchor="ads",
            )
        )
    elif facts.ads_pressure == "high":
        items.append(
            WhyItem(
                text="A competitor domain has heavy recent Google ad volume in India (Ads Transparency).",
                anchor="ads",
            )
        )
    elif facts.sponsored_share is None and facts.ads_pressure in {"n/a", "low"}:
        items.append(
            WhyItem(
                text="Amazon did not flag sponsored results on this search, so that share is shown as n/a.",
                anchor="ads",
            )
        )
    if verdict == "SKIP":
        items.append(
            WhyItem(
                text="Falling demand, a crowded band, and no quality gap add up to a skip.",
                anchor="decision",
            )
        )
    return items


def limitations(facts: VerdictFacts) -> list[str]:
    notes = [
        "Google Trends is relative interest, not unit sales.",
        "“Bought in past month” is a bucket such as 50+ or 1K+, not an exact count.",
        "These are signals for a stocking decision, not a promise of sales.",
    ]
    if facts.sparse:
        notes.append("The Trends series is sparse, so the momentum number is a weak signal.")
    if facts.ambiguous_head and facts.used_head_term:
        notes.append(
            f"The head term “{facts.series_term}” is broader than the product and can include non-shopping searches."
        )
    if facts.sponsored_share is None:
        notes.append("Sponsored share is hidden unless Amazon actually returns a sponsored field.")
    return notes
