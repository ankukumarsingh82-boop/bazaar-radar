"""Price bands, outlier trimming, and the white-space test."""

from __future__ import annotations

import math

from app.models import Band, Offer

HIGH_RATING = 4.2
LOW_MEDIAN = 4.0


def percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * pct / 100
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return sorted_values[int(rank)]
    weight = rank - low
    return sorted_values[low] * (1 - weight) + sorted_values[high] * weight


def iqr_fences(prices: list[float], factor: float = 1.5) -> tuple[float, float]:
    ordered = sorted(prices)
    q1 = percentile(ordered, 25)
    q3 = percentile(ordered, 75)
    iqr = q3 - q1
    return q1 - factor * iqr, q3 + factor * iqr


def trim_offers(offers: list[Offer]) -> tuple[list[Offer], int]:
    prices = [offer.price for offer in offers if offer.price is not None]
    if len(prices) < 8:
        return offers, 0
    low, high = iqr_fences([price for price in prices if price is not None])
    kept: list[Offer] = []
    removed = 0
    for offer in offers:
        if offer.price is None or low <= offer.price <= high:
            kept.append(offer)
        else:
            removed += 1
    return kept, removed


def build_bands(offers: list[Offer], target: float, bins: int = 6) -> list[Band]:
    priced = [offer for offer in offers if offer.price is not None]
    if not priced:
        return []
    prices = sorted(offer.price for offer in priced if offer.price is not None)
    edges = _edges(prices, bins)
    bands: list[Band] = []
    for index, (low, high) in enumerate(zip(edges, edges[1:])):
        last = index == len(edges) - 2
        group = [
            offer
            for offer in priced
            if offer.price is not None
            and (low <= offer.price < high or (last and offer.price == high))
        ]
        if not group and not (low <= target <= high):
            continue
        bands.append(_band(group, low, high, target))
    total = sum(band.count for band in bands) or 1
    demand_total = sum(band.bought_sum for band in bands)
    review_total = sum(band.total_reviews for band in bands)
    use_bought = demand_total > 0
    for band in bands:
        band.listing_share = band.count / total
        if use_bought:
            band.demand_share = band.bought_sum / demand_total
        elif review_total:
            band.demand_share = band.total_reviews / review_total
        else:
            band.demand_share = 0.0
        _mark(band)
    return bands


def near_target(band: Band, target: float) -> bool:
    if band.low <= target <= band.high:
        return True
    mid = (band.low + band.high) / 2
    return abs(mid - target) <= max(150.0, 0.25 * target)


def recommend_band(bands: list[Band], target: float, verdict: str) -> Band | None:
    if verdict == "SKIP" or not bands:
        return None
    whitespace = [band for band in bands if band.whitespace and near_target(band, target)]
    gaps = [band for band in bands if band.quality_gap and near_target(band, target)]
    pool = whitespace or gaps
    if verdict == "GO" and whitespace:
        pool = whitespace
    elif verdict == "GO-with-positioning" and (gaps or whitespace):
        pool = gaps or whitespace
    elif verdict == "CAUTION":
        pool = whitespace or gaps or [band for band in bands if band.contains_target]
    if not pool:
        pool = [min(bands, key=lambda band: abs(((band.low + band.high) / 2) - target))]
    return min(pool, key=lambda band: abs(((band.low + band.high) / 2) - target))


def _edges(prices: list[float], bins: int) -> list[float]:
    raw = [percentile(prices, 100 * index / bins) for index in range(bins + 1)]
    snapped = [_snap(value) for value in raw]
    edges = [snapped[0]]
    for value in snapped[1:]:
        if value <= edges[-1]:
            bump = 50 if edges[-1] >= 200 else 10
            value = edges[-1] + bump
        edges.append(value)
    if len(set(edges)) < 3:
        low, high = prices[0], prices[-1]
        if high <= low:
            high = low + 100
        step = (high - low) / bins
        edges = [round(low + step * index) for index in range(bins + 1)]
    return edges


def _snap(value: float) -> float:
    if value >= 1000:
        return float(round(value / 100) * 100)
    if value >= 200:
        return float(round(value / 50) * 50)
    return float(round(value / 10) * 10)


def _band(group: list[Offer], low: float, high: float, target: float) -> Band:
    amazon = [offer for offer in group if offer.origin == "amazon"]
    shopping = [offer for offer in group if offer.origin == "shopping"]
    ratings = sorted(offer.rating for offer in amazon if offer.rating is not None)
    median_rating = None
    if ratings:
        mid = len(ratings) // 2
        median_rating = ratings[mid] if len(ratings) % 2 else (ratings[mid - 1] + ratings[mid]) / 2
    high_rated = sum(
        1 for offer in amazon if offer.rating is not None and offer.rating >= HIGH_RATING
    )
    return Band(
        label=_band_label(low, high),
        low=low,
        high=high,
        count=len(group),
        amazon_count=len(amazon),
        shopping_count=len(shopping),
        listing_share=0.0,
        median_rating=median_rating,
        total_reviews=sum(offer.reviews for offer in amazon),
        bought_sum=sum(offer.bought for offer in amazon),
        high_rating_count=high_rated,
        contains_target=low <= target <= high,
    )


def _mark(band: Band) -> None:
    few_good = band.amazon_count >= 2 and (band.high_rating_count / band.amazon_count) < 0.30
    low_median = (
        band.median_rating is not None
        and band.median_rating < LOW_MEDIAN
        and band.amazon_count >= 2
    )
    band.quality_gap = bool(few_good or low_median)
    demand_ahead = band.demand_share > band.listing_share + 0.03
    band.whitespace = bool(demand_ahead and band.quality_gap and band.count >= 2)


def _band_label(low: float, high: float) -> str:
    return f"₹{_compact(low)}–{_compact(high)}"


def _compact(value: float) -> str:
    number = int(round(value))
    return f"{number:,}"
