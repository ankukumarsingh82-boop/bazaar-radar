"""Amazon.in search and product pages."""

from __future__ import annotations

import re

from app.models import AmazonSearch, Insight, Offer, ProductPage

_BOUGHT = re.compile(r"(\d+(?:\.\d+)?)\s*([kK])?")


def parse_bought(text: str | None) -> int:
    if not text:
        return 0
    match = _BOUGHT.search(str(text))
    if not match:
        return 0
    number = float(match.group(1))
    if match.group(2):
        number *= 1000
    return int(number)


def search_params(keyword: str) -> dict[str, str]:
    return {"engine": "amazon", "k": keyword, "amazon_domain": "amazon.in"}


def product_params(asin: str) -> dict[str, str]:
    return {"engine": "amazon_product", "asin": asin, "amazon_domain": "amazon.in"}


def normalize_search(payload: dict) -> AmazonSearch:
    organic = payload.get("organic_results") or []
    offers: list[Offer] = []
    sponsored_seen = False
    sponsored_true = 0
    bought_hits = 0
    choice_count = 0
    for item in organic:
        if "sponsored" in item:
            sponsored_seen = True
            if item.get("sponsored") is True:
                sponsored_true += 1
        badges = [str(b) for b in (item.get("badges") or []) if b]
        choice = any("amazon's choice" in b.lower() for b in badges)
        if choice:
            choice_count += 1
        bought_text = item.get("bought_last_month")
        if bought_text:
            bought_hits += 1
        price = item.get("extracted_price")
        rating = item.get("rating")
        reviews = item.get("reviews")
        offers.append(
            Offer(
                origin="amazon",
                title=str(item.get("title") or ""),
                price=float(price) if isinstance(price, (int, float)) and price > 0 else None,
                rating=float(rating) if isinstance(rating, (int, float)) else None,
                reviews=int(reviews) if isinstance(reviews, (int, float)) else 0,
                bought=parse_bought(bought_text),
                sponsored=True
                if item.get("sponsored") is True
                else (False if "sponsored" in item else None),
                asin=item.get("asin"),
                merchant="Amazon.in",
                badges=badges,
                choice=choice,
            )
        )
    brands = []
    for brand in (payload.get("sponsored_brands") or {}).get("brands") or []:
        name = str(brand.get("name") or "").strip()
        if name and name not in brands:
            brands.append(name)
    info = payload.get("search_information") or {}
    total = info.get("total_results")
    share = (sponsored_true / len(organic)) if sponsored_seen and organic else None
    return AmazonSearch(
        offers=offers,
        related_searches=[
            str(row.get("query"))
            for row in (payload.get("related_searches") or [])
            if row.get("query")
        ],
        sponsored_share=share,
        sponsored_observed=sponsored_seen,
        sponsored_brand_names=brands,
        total_results=int(total) if isinstance(total, (int, float)) else None,
        bought_coverage=(bought_hits / len(organic)) if organic else 0.0,
        choice_count=choice_count,
    )


def normalize_product(payload: dict) -> ProductPage:
    product = payload.get("product_results") or {}
    reviews = payload.get("reviews_information") or {}
    summary = reviews.get("summary") or {}
    insights_raw = []
    if isinstance(summary, dict):
        insights_raw = summary.get("insights") or []
    insights: list[Insight] = []
    for item in insights_raw:
        mentions = item.get("mentions") or {}
        examples = item.get("examples") or []
        snippet = ""
        if examples and isinstance(examples[0], dict):
            snippet = str(examples[0].get("snippet") or "")
        insights.append(
            Insight(
                title=str(item.get("title") or "").strip(),
                sentiment=str(item.get("sentiment") or "").lower(),
                negative=_as_int(mentions.get("negative")),
                positive=_as_int(mentions.get("positive")),
                total=_as_int(mentions.get("total")),
                summary=str(item.get("summary") or ""),
                snippet=snippet,
            )
        )
    details = payload.get("product_details") or {}
    ranks = details.get("best_sellers_rank") if isinstance(details, dict) else None
    bsr_text = None
    bsr_rank = None
    if isinstance(ranks, list) and ranks:
        # Amazon lists the broad storefront first and the tighter category last.
        chosen = ranks[-1]
        bsr_text = str(chosen.get("text") or "")
        extracted = chosen.get("extracted_rank")
        bsr_rank = int(extracted) if isinstance(extracted, (int, float)) else None
    summary_text = ""
    if isinstance(summary, dict):
        summary_text = str(summary.get("text") or "")
    price = product.get("extracted_price")
    rating = product.get("rating")
    review_count = product.get("reviews")
    return ProductPage(
        asin=str(product.get("asin") or ""),
        title=str(product.get("title") or ""),
        brand=_clean_brand(product.get("brand")),
        price=float(price) if isinstance(price, (int, float)) and price > 0 else None,
        rating=float(rating) if isinstance(rating, (int, float)) else None,
        reviews=int(review_count) if isinstance(review_count, (int, float)) else None,
        bsr=bsr_text,
        bsr_rank=bsr_rank,
        summary_text=summary_text,
        insights=[row for row in insights if row.title],
    )


def _as_int(value) -> int:
    return int(value) if isinstance(value, (int, float)) else 0


def _clean_brand(value) -> str | None:
    if not value:
        return None
    text = str(value)
    text = text.removeprefix("Visit the ").removesuffix(" Store").strip()
    return text or None
