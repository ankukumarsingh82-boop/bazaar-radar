from app.analysis.pricebands import (
    build_bands,
    iqr_fences,
    near_target,
    recommend_band,
    trim_offers,
)
from app.models import Offer
from app.sources.amazon import parse_bought


def test_bought_parser_maps_buckets():
    assert parse_bought("1K+ bought in past month") == 1000
    assert parse_bought("50+ bought in past month") == 50
    assert parse_bought("600+ bought in past month") == 600
    assert parse_bought(None) == 0
    assert parse_bought("") == 0


def test_iqr_drops_the_diya_outlier():
    prices = [100, 120, 180, 200, 220, 260, 300, 340, 400, 78750]
    offers = [Offer(origin="shopping", title=str(price), price=price) for price in prices]
    kept, removed = trim_offers(offers)
    assert removed == 1
    assert all(offer.price < 10000 for offer in kept)
    low, high = iqr_fences(prices)
    assert 78750 > high
    assert low < 100


def test_whitespace_when_demand_exceeds_listings_and_ratings_are_weak():
    offers = []
    # Cheap band: many listings, strong ratings, little bought.
    for index in range(8):
        offers.append(
            Offer(
                origin="amazon",
                title=f"cheap {index}",
                price=150 + index,
                rating=4.6,
                reviews=20,
                bought=10,
            )
        )
    # Target band: fewer listings, weak ratings, most of the bought proxy.
    for index in range(3):
        offers.append(
            Offer(
                origin="amazon",
                title=f"mid {index}",
                price=680 + index,
                rating=3.6,
                reviews=80,
                bought=400,
            )
        )
    bands = build_bands(offers, target=699, bins=4)
    targetish = [band for band in bands if near_target(band, 699)]
    assert any(band.whitespace for band in targetish)
    chosen = recommend_band(bands, 699, "GO")
    assert chosen is not None
    assert chosen.low <= 699 <= chosen.high or near_target(chosen, 699)


def test_shopping_ratings_are_not_required_for_a_band():
    offers = [
        Offer(origin="shopping", title="a", price=100, merchant="Flipkart"),
        Offer(origin="shopping", title="b", price=180, merchant="Meesho"),
        Offer(origin="amazon", title="c", price=220, rating=4.5, reviews=10, bought=20),
    ]
    bands = build_bands(offers, target=150, bins=2)
    assert bands
    assert all(band.median_rating is None or band.amazon_count for band in bands)
