"""Google Immersive Product store lists. Foreign shops are flagged and dropped."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from app.models import ImmersiveProduct, StoreOffer

_FOREIGN_SUFFIXES = (".ae", ".uk", ".us", ".com.au", ".sg", ".qa", ".sa", ".eu", ".ca", ".hk")
# Whole seller labels only. A substring match treats "Debayan Crafts" as eBay.
_FOREIGN_MARKERS = ("desertcart", "ebay", "aliexpress", "alibaba", "walmart")
# Public-suffix-style second levels used by Indian and a few other shops. Not a full PSL.
_MULTI_SUFFIXES = (
    "co.in",
    "com.in",
    "net.in",
    "org.in",
    "gen.in",
    "firm.in",
    "ind.in",
    "ac.in",
    "res.in",
    "gov.in",
    "nic.in",
    "edu.in",
    "co.uk",
    "org.uk",
    "ac.uk",
    "com.au",
    "net.au",
    "org.au",
    "co.nz",
    "com.sg",
    "com.hk",
    "co.za",
)


def hostname(link: str | None) -> str:
    host = (urlparse(link or "").hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def registrable_domain(host: str) -> str:
    """eTLD+1. `dl.flipkart.com` and `shop.brand.co.in` collapse to one domain."""
    host = hostname(host) if "://" in (host or "") else (host or "").lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host:
        return host
    parts = host.split(".")
    for suffix in _MULTI_SUFFIXES:
        suffix_parts = suffix.split(".")
        size = len(suffix_parts)
        if len(parts) > size and parts[-size:] == suffix_parts:
            return ".".join(parts[-(size + 1) :])
    return ".".join(parts[-2:])


def _name_has_marker(name: str) -> bool:
    tokens = re.findall(r"[a-z0-9]+", (name or "").lower())
    for marker in _FOREIGN_MARKERS:
        if marker in tokens:
            return True
        for start in range(len(tokens)):
            joined = ""
            for token in tokens[start:]:
                joined += token
                if joined == marker:
                    return True
                if len(joined) > len(marker):
                    break
    return False


def is_foreign(name: str, link: str | None) -> bool:
    host = hostname(link)
    registered = registrable_domain(host) if host else ""
    label = registered.split(".")[0] if registered else ""
    if label in _FOREIGN_MARKERS or registered == "target.com":
        return True
    if _name_has_marker(name):
        return True
    if re.sub(r"\s+", "", (name or "").lower()) == "target.com":
        return True
    return bool(registered) and registered.endswith(_FOREIGN_SUFFIXES)


def search_params(page_token: str) -> dict[str, str]:
    return {
        "engine": "google_immersive_product",
        "page_token": page_token,
        "more_stores": "true",
    }


def normalize_immersive(payload: dict) -> ImmersiveProduct:
    product = payload.get("product_results") or {}
    stores: list[StoreOffer] = []
    for row in product.get("stores") or []:
        name = str(row.get("name") or "").strip()
        link = row.get("link")
        price = row.get("extracted_price")
        total = row.get("extracted_total")
        stores.append(
            StoreOffer(
                name=name or "Store",
                price=float(price) if isinstance(price, (int, float)) else None,
                total=float(total) if isinstance(total, (int, float)) else None,
                tag=row.get("tag"),
                link=link,
                foreign=is_foreign(name, link),
            )
        )
    kept = [store for store in stores if not store.foreign]
    prices = sorted(store.price for store in kept if store.price)
    if len(prices) >= 4:
        mid = prices[len(prices) // 2]
        for store in kept:
            if store.price and mid and (store.price > mid * 2.5 or store.price < mid / 2.5):
                store.pack_outlier = True
    return ImmersiveProduct(
        title=str(product.get("title") or ""),
        brand=product.get("brand"),
        price_range=product.get("price_range"),
        stores=kept,
    )
