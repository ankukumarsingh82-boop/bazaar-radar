"""Google Shopping India. Ratings are ignored; they are almost never present."""

from __future__ import annotations

from statistics import median

from app.models import MerchantStat, Offer, ShoppingResult

ALIASES = {
    "amazon.in": "Amazon.in",
    "amazon": "Amazon.in",
    "flipkart": "Flipkart",
    "flipkart.com": "Flipkart",
    "meesho": "Meesho",
    "myntra": "Myntra",
    "jiomart": "JioMart",
    "zepto": "Zepto",
    "blinkit": "Blinkit",
    "blinkit.com": "Blinkit",
    "bigbasket": "bigbasket",
    "bigbasket.com": "bigbasket",
    "fnp": "fnp.com",
    "fnp.com": "fnp.com",
    "igp": "IGP",
    "jaypore": "Jaypore",
    "fabindia": "Fabindia",
    "nykaa": "Nykaa",
    "ajio": "Ajio",
}

DOMAINS = {
    "Flipkart": "flipkart.com",
    "Meesho": "meesho.com",
    "Myntra": "myntra.com",
    "JioMart": "jiomart.com",
    "Zepto": "zepto.com",
    "Blinkit": "blinkit.com",
    "bigbasket": "bigbasket.com",
    "fnp.com": "fnp.com",
    "IGP": "igp.com",
    "Jaypore": "jaypore.com",
    "Fabindia": "fabindia.com",
    "Nykaa": "nykaa.com",
    "Ajio": "ajio.com",
}

QUICK = {"Zepto", "Blinkit", "bigbasket"}


def search_params(keyword: str) -> dict[str, str]:
    return {
        "engine": "google_shopping",
        "q": keyword,
        "gl": "in",
        "hl": "en",
        "google_domain": "google.co.in",
        "location": "India",
    }


def canonical_merchant(source: str | None) -> str:
    if not source or not str(source).strip():
        return "Unknown store"
    text = " ".join(str(source).split())
    return ALIASES.get(text.lower(), text)


def normalize_shopping(payload: dict) -> ShoppingResult:
    seen: set[str] = set()
    items = list(payload.get("shopping_results") or [])
    for category in payload.get("categorized_shopping_results") or []:
        items.extend(category.get("shopping_results") or [])
    offers: list[Offer] = []
    for item in items:
        product_id = str(item.get("product_id") or "")
        if product_id:
            if product_id in seen:
                continue
            seen.add(product_id)
        price = item.get("extracted_price")
        merchant = canonical_merchant(item.get("source"))
        offers.append(
            Offer(
                origin="shopping",
                title=str(item.get("title") or ""),
                price=float(price) if isinstance(price, (int, float)) and price > 0 else None,
                rating=None,
                reviews=0,
                merchant=merchant,
                product_id=product_id or None,
                immersive_token=item.get("immersive_product_page_token"),
            )
        )
    return ShoppingResult(offers=offers, merchants=merchant_stats(offers))


def merchant_stats(offers: list[Offer]) -> list[MerchantStat]:
    grouped: dict[str, list[Offer]] = {}
    for offer in offers:
        name = offer.merchant or "Unknown store"
        grouped.setdefault(name, []).append(offer)
    stats: list[MerchantStat] = []
    for name, rows in grouped.items():
        prices = [row.price for row in rows if row.price is not None]
        stats.append(
            MerchantStat(
                name=name,
                count=len(rows),
                median_price=float(median(prices)) if prices else None,
                domain=DOMAINS.get(name),
                quick=name in QUICK,
            )
        )
    stats.sort(key=lambda row: row.count, reverse=True)
    return stats
