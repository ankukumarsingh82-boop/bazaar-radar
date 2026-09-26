import json
from pathlib import Path

from app.analysis.demand import zero_fraction as demand_zero
from app.sources.ads import normalize_ads
from app.sources.amazon import normalize_product, normalize_search
from app.sources.immersive import normalize_immersive
from app.sources.shopping import normalize_shopping
from app.sources.trends import normalize_five_year, normalize_geo, normalize_related, normalize_yoy

ROOT = Path(__file__).resolve().parents[1] / "fixtures"


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_yoy_reads_dates_from_values_in_multi_date_mode():
    points = normalize_yoy(load("google_trends__yoy-brass-diya.json"))
    assert len(points) == 57 * 2
    assert {point.series for point in points} == {"2025", "2026"}
    assert demand_zero(points) > 0.40
    diya = normalize_yoy(load("google_trends__yoy-diya.json"))
    assert demand_zero(diya) == 0


def test_five_year_picks_one_term_and_finds_rangoli_peak():
    term, points = normalize_five_year(
        load("google_trends__5y-diya-rangoli-diwali-gift.json"), "rangoli"
    )
    assert term == "rangoli"
    assert len(points) > 200
    gift_term, gift_points = normalize_five_year(
        load("google_trends__5y-diya-rangoli-diwali-gift.json"), "diwali gift hamper"
    )
    assert gift_term == "diwali gift"
    assert demand_zero(gift_points) > 0.40


def test_geo_and_related_queries():
    states = normalize_geo(load("google_trends__geo-brass-diya.json"), {"IN-MH", "IN-DL"})
    assert states[0].geo == "IN-KA"
    assert any(state.served and state.geo == "IN-MH" for state in states)
    related = normalize_related(load("google_trends__related-brass-diya-3m.json"))
    assert sum(1 for row in related if row.kind == "rising") == 5
    hamper = normalize_related(load("google_trends__related-diwali-gift-hamper-12m.json"))
    assert any(row.query == "diwali 2026" for row in hamper)


def test_amazon_sponsored_is_absent_unless_the_field_exists():
    brass = normalize_search(load("amazon__brass-diya.json"))
    assert brass.sponsored_share is None
    assert brass.sponsored_observed is False
    assert brass.bought_coverage >= 0.7
    rangoli = normalize_search(load("amazon__rangoli-colours.json"))
    assert rangoli.sponsored_observed is True
    assert rangoli.sponsored_share == 12 / 60
    assert "CraftVatika" in rangoli.sponsored_brand_names
    assert rangoli.offers[0].price > 0


def test_insights_live_under_summary():
    page = normalize_product(load("amazon_product__B00EZMNH9A-brass-diya.json"))
    assert page.brand == "Borosil"
    assert len(page.insights) == 8
    assert page.insights[0].title == "Quality"
    assert page.bsr and "Home & Décor" in page.bsr
    hamper = normalize_product(load("amazon_product__B08KF3QKZ6-diwali-gift-hamper.json"))
    assert hamper.bsr is None


def test_shopping_dedupes_and_normalises_merchants():
    shopping = normalize_shopping(load("google_shopping__brass-diya.json"))
    ids = [offer.product_id for offer in shopping.offers if offer.product_id]
    assert len(ids) == len(set(ids))
    assert all(offer.rating is None for offer in shopping.offers)
    names = [merchant.name for merchant in shopping.merchants]
    assert "Amazon.in" in names
    assert "amazon.in" not in names
    assert any(merchant.quick for merchant in shopping.merchants)
    rangoli = normalize_shopping(load("google_shopping__rangoli-colours.json"))
    assert any(offer.merchant == "Unknown store" for offer in rangoli.offers)


def test_ads_and_immersive_filters():
    from datetime import date

    ad = normalize_ads(
        load("google_ads_transparency_center__fnp-com-in.json"), "fnp.com", date(2026, 9, 26)
    )
    assert ad.total_results == 2000
    assert ad.advertiser.startswith("FNP")
    assert ad.recent
    jaypore = normalize_ads(
        load("google_ads_transparency_center__jaypore-com-in.json"),
        "jaypore.com",
        date(2026, 9, 26),
    )
    assert jaypore.domain == "jaypore.com"
    assert "Xplanck" in jaypore.advertiser
    product = normalize_immersive(load("google_immersive_product__brass-diya-top.json"))
    assert all("desertcart" not in store.name.lower() for store in product.stores)
    assert any(store.name == "Flipkart" for store in product.stores)
