"""Buyer-pain themes from Amazon review insights."""

from __future__ import annotations

from app.models import ComplaintView, ProductPage


def complaint_themes(products: list[ProductPage], limit: int = 3) -> list[ComplaintView]:
    grouped: dict[str, dict] = {}
    for product in products:
        for insight in product.insights:
            if not _is_complaint(insight.sentiment, insight.negative, insight.total):
                continue
            key = insight.title.lower()
            bucket = grouped.setdefault(
                key,
                {
                    "theme": insight.title,
                    "negative": 0,
                    "total": 0,
                    "sentiment": insight.sentiment,
                    "summary": insight.summary,
                    "snippet": insight.snippet,
                    "products": [],
                },
            )
            bucket["negative"] += insight.negative
            bucket["total"] += insight.total
            if insight.sentiment == "negative":
                bucket["sentiment"] = "negative"
            if product.title and product.title not in bucket["products"]:
                bucket["products"].append(product.title)
            if len(insight.summary) > len(bucket["summary"]):
                bucket["summary"] = insight.summary
                bucket["snippet"] = insight.snippet
    rows = []
    for bucket in grouped.values():
        ratio = bucket["negative"] / bucket["total"] if bucket["total"] else 0.0
        rows.append(
            ComplaintView(
                theme=bucket["theme"],
                sentiment=bucket["sentiment"],
                negative=bucket["negative"],
                total=bucket["total"],
                ratio=ratio,
                summary=bucket["summary"],
                snippet=bucket["snippet"],
                products=bucket["products"],
            )
        )
    rows.sort(key=lambda row: (row.negative, row.ratio), reverse=True)
    return rows[:limit]


def _is_complaint(sentiment: str, negative: int, total: int) -> bool:
    if negative <= 0:
        return False
    if sentiment in {"negative", "mixed"}:
        return True
    if total and (negative / total) > 0.30:
        return True
    return False
