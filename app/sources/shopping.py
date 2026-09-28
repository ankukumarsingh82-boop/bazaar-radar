"""Google Shopping India. Ratings are ignored; they are almost never present."""

from __future__ import annotations

from statistics import median

from app.models import MerchantStat, Offer, ShoppingResult
from app.sources.immersive import hostname, is_foreign

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

# Marketplaces advertise their whole catalogue, so their Ads Transparency volume says
# nothing about one product idea. They are shown for context but never drive ad pressure.
MARKETPLACE_DOMAINS = {
    "flipkart.com",
    "myntra.com",
    "meesho.com",
    "jiomart.com",
    "zepto.com",
    "blinkit.com",
    "bigbasket.com",
    "ajio.com",
    "nykaa.com",
}


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
        link = item.get("link")
        link = link.strip() if isinstance(link, str) and link.strip() else None
        if is_foreign(merchant, link):
            continue
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
                link=link,
            )
        )
    return ShoppingResult(offers=offers, merchants=merchant_stats(offers))


def advertiser_domains(offers: list[Offer]) -> list[str]:
    """Seller hostnames from offer links. Marketplaces and foreign shops are left out.

    The hard-coded merchant map is not consulted here. Callers fall back to it
    only when this list is empty.
    """
    counts: dict[str, int] = {}
    for offer in offers:
        host = hostname(offer.link)
        if not _usable_advertiser_host(host):
            continue
        counts[host] = counts.get(host, 0) + 1
    return sorted(counts, key=lambda host: (-counts[host], host))


def _usable_advertiser_host(host: str) -> bool:
    if not host or "." not in host:
        return False
    if host in MARKETPLACE_DOMAINS or host in {"amazon.in", "amazon.com"}:
        return False
    if (
        host == "google.com"
        or host.endswith(".google.com")
        or host == "google.co.in"
        or host.endswith(".google.co.in")
        or host.endswith("gstatic.com")
        or host.endswith("googleusercontent.com")
    ):
        return False
    if is_foreign(host, f"https://{host}/"):
        return False
    return True


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
