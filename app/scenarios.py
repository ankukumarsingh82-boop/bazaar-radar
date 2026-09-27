"""The three ideas recorded on day 1. Fixture mode can run each of them offline."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Scenario(BaseModel):
    slug: str
    keyword: str
    head_term: str
    variants: list[str] = Field(default_factory=list)
    target_price: float
    states: list[str]
    category: str
    blurb: str


SCENARIOS: dict[str, Scenario] = {
    "brass-diya": Scenario(
        slug="brass-diya",
        keyword="brass diya",
        head_term="diya",
        variants=["brass diya set", "akhand diya"],
        target_price=699,
        states=["IN-MH", "IN-DL", "IN-GJ", "IN-RJ"],
        category="Home & Décor",
        blurb="Niche décor term. Daily Trends is sparse, so the head term carries the curve.",
    ),
    "rangoli-colours": Scenario(
        slug="rangoli-colours",
        keyword="rangoli colours",
        head_term="rangoli",
        variants=["rangoli colour powder", "rangoli kit"],
        target_price=199,
        states=["IN-MH", "IN-KA", "IN-TN", "IN-TG"],
        category="Home & Décor",
        blurb="A dense festive search with a sharp Diwali peak and loud review complaints.",
    ),
    "diwali-gift-hamper": Scenario(
        slug="diwali-gift-hamper",
        keyword="diwali gift hamper",
        head_term="diwali gift",
        variants=["corporate diwali hamper", "diwali gift box"],
        target_price=799,
        states=["IN-DL", "IN-MH", "IN-HR", "IN-KA"],
        category="Gifting",
        blurb="A crowded gifting idea. The broad term is sparse, and gift sites buy a lot of ads.",
    ),
}


def suggest_head(keyword: str) -> str:
    """Drop material and colour words so a sparse phrase can fall back to its head term."""
    drop = {
        "brass",
        "steel",
        "copper",
        "silver",
        "gold",
        "wooden",
        "wood",
        "cotton",
        "silk",
        "colours",
        "colors",
        "colour",
        "color",
        "set",
        "sets",
        "pack",
        "kit",
    }
    words = [w for w in keyword.lower().split() if w]
    kept = [w for w in words if w not in drop]
    if not kept or kept == words:
        return keyword.strip()
    return " ".join(kept)
