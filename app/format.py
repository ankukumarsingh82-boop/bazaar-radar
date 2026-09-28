"""Small display helpers shared by the templates and the Markdown export."""

from __future__ import annotations


def inr(value: float | int | None) -> str:
    if value is None:
        return "—"
    number = float(value)
    if abs(number - round(number)) < 0.05:
        return f"₹{round(number):,}"
    return f"₹{number:,.2f}"


def pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.0%}"


def verdict_title(verdict: str) -> str:
    return {
        "GO": "GO",
        "GO-with-positioning": "GO with positioning",
        "CAUTION": "CAUTION",
        "SKIP": "SKIP",
        "insufficient": "Not enough data",
    }.get(verdict, verdict)


def verdict_blurb(verdict: str) -> str:
    return {
        "GO": "Demand is holding up, and a price band near your target has room for a better listing.",
        "GO-with-positioning": "There is room only if the listing clearly beats what buyers already complain about.",
        "CAUTION": "Do not bet the full budget yet. Demand, the price bands, or ad pressure is not a clean go.",
        "SKIP": "Demand is falling and the shelf is crowded, with no quality gap to stand in.",
        "insufficient": (
            "This idea is not in the offline recordings, and no live search ran. "
            "Open brass diya, rangoli colours, or diwali gift hamper, or set BR_MODE=cache with a SerpApi key."
        ),
    }.get(verdict, "")
