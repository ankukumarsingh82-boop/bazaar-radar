"""Google Immersive Product store lists. Foreign shops are flagged and dropped."""

from __future__ import annotations

from urllib.parse import urlparse

from app.models import ImmersiveProduct, StoreOffer

_FOREIGN_SUFFIXES = (".ae", ".uk", ".us", ".com.au", ".sg", ".qa", ".sa", ".eu", ".ca", ".hk")
_FOREIGN_NAMES = ("desertcart", "ebay", "aliexpress", "alibaba", "walmart", "target.com")


def search_params(page_token: str) -> dict[str, str]:
    return {
        "engine": "google_immersive_product",
        "page_token": page_token,
        "more_stores": "true",
    }


def is_foreign(name: str, link: str | None) -> bool:
    blob = f"{name} {link or ''}".lower()
    if any(token in blob for token in _FOREIGN_NAMES):
        return True
    host = (urlparse(link or "").hostname or "").lower()
    return host.endswith(_FOREIGN_SUFFIXES)


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
