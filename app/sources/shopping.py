"""Google Shopping India. Ratings are ignored; they are almost never present."""

from __future__ import annotations

from statistics import median

from app.models import MerchantStat, Offer, ShoppingResult
from app.sources.immersive import hostname, is_foreign, registrable_domain

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

# Department stores and large general retailers also advertise the whole catalogue.
# Nykaa and Ajio are already marketplaces. These hosts are still eligible to be shown,
# but they are not niche advertisers and their creative counts never drive the verdict.
GENERAL_RETAILER_DOMAINS = {
    "shoppersstop.com",
    "tatacliq.com",
    "ikea.com",
    "ikea.in",
    "homecentre.com",
    "homecentre.in",
    "nykaafashion.com",
    "reliancedigital.in",
    "lifestylestores.com",
    "pepperfry.com",
    "croma.com",
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


def is_marketplace(domain: str) -> bool:
    registered = registrable_domain(domain)
    return registered in MARKETPLACE_DOMAINS or registered in {"amazon.in", "amazon.com"}


def is_general_retailer(domain: str) -> bool:
    return registrable_domain(domain) in GENERAL_RETAILER_DOMAINS


def is_context_only(domain: str) -> bool:
    """Catalogue-wide advertisers. Shown for context; excluded from ad pressure."""
    return is_marketplace(domain) or is_general_retailer(domain)


def advertiser_domains(rows) -> list[str]:
    """Registrable niche seller domains from Immersive store links (or any row with a link).

    Marketplaces (including subdomains such as dl.flipkart.com), general retailers
    such as Shoppers Stop, and foreign shops are left out. The curated merchant map
    is not consulted here.
    """
    counts: dict[str, int] = {}
    for row in rows:
        link = row if isinstance(row, str) else getattr(row, "link", None)
        registered = registrable_domain(hostname(link))
        if not _usable_advertiser_host(registered):
            continue
        counts[registered] = counts.get(registered, 0) + 1
    return sorted(counts, key=lambda host: (-counts[host], host))


def _usable_advertiser_host(registered: str) -> bool:
    if not registered or "." not in registered:
        return False
    if is_context_only(registered):
        return False
    if registered in {"google.com", "google.co.in", "gstatic.com", "googleusercontent.com"}:
        return False
    if is_foreign(registered, f"https://{registered}/"):
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
