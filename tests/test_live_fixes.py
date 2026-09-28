"""Regressions found in the 27 Sep 2026 live check."""

import json
from datetime import date
from pathlib import Path

from app.analysis.demand import recommend_states
from app.analysis.pricebands import build_bands
from app.analysis.verdict import ads_pressure
from app.config import Settings
from app.db import connect, init_db
from app.models import MerchantStat, Offer, ShoppingResult, StateInterest, StoreOffer
from app.orchestrator import _ads
from app.serp_client import SerpClient, is_empty_result
from app.sources.immersive import is_foreign, normalize_immersive, registrable_domain
from app.sources.shopping import advertiser_domains, is_general_retailer

EMPTY = {
    "search_metadata": {"id": "empty1", "status": "Success"},
    "error": "Google Trends hasn't returned any results for this query.",
}


def _client(tmp_path, live, mode="cache"):
    settings = Settings(
        serpapi_api_key="test-key",
        br_mode=mode,
        db_path=tmp_path / "t.sqlite",
        max_live_calls_per_report=14,
    )
    conn = connect(settings.db_path)
    init_db(conn)
    client = SerpClient(
        settings, conn, "r", live_search=live, account_fetch=lambda key: {"plan_searches_left": 200}
    )
    return client, conn


def test_empty_result_payload_is_cached_so_a_rerun_costs_zero(tmp_path):
    calls = {"n": 0}

    def live(params, api_key):
        calls["n"] += 1
        return dict(EMPTY)

    client, conn = _client(tmp_path, live)
    params = {"engine": "google_trends", "q": "brass toran,brass toran", "data_type": "TIMESERIES"}
    first = client.search(params)
    assert first.source == "live" and first.error
    rerun = SerpClient(
        client.settings,
        conn,
        "r2",
        live_search=live,
        account_fetch=lambda key: {"plan_searches_left": 200},
    )
    second = rerun.search(params)
    assert second.source == "cache"
    assert second.error and "returned any results" in second.error
    assert calls["n"] == 1
    conn.close()


def test_transient_errors_are_not_cached(tmp_path):
    calls = {"n": 0}

    def live(params, api_key):
        calls["n"] += 1
        return {"error": "Your searches for the month are exhausted."}

    client, conn = _client(tmp_path, live)
    params = {"engine": "amazon", "k": "x", "amazon_domain": "amazon.in"}
    client.search(params)
    client.search(params)
    assert calls["n"] == 2
    assert not is_empty_result({"error": "Invalid API key."})
    conn.close()


def test_marketplace_ads_do_not_drive_pressure_and_niche_domains_go_first(tmp_path):
    seen = []

    def live(params, api_key):
        seen.append(params["text"])
        return {
            "search_metadata": {"id": params["text"]},
            "search_information": {"total_results": 3000 if params["text"] == "myntra.com" else 12},
            "ad_creatives": [{"format": "text", "advertiser": params["text"]}],
        }

    client, conn = _client(tmp_path, live)
    shopping = ShoppingResult(
        offers=[Offer(origin="shopping", title="t", price=100)],
        merchants=[
            MerchantStat(name="Myntra", count=5, domain="myntra.com"),
            MerchantStat(name="Jaypore", count=1, domain="jaypore.com"),
            MerchantStat(name="Flipkart", count=4, domain="flipkart.com"),
        ],
    )
    evidence = []
    ads, notes = _ads(
        client, shopping, date(2026, 9, 27), evidence, lambda p, purpose: client.search(p)
    )
    assert seen[0] == "jaypore.com"
    by_domain = {ad.domain: ad for ad in ads}
    assert by_domain["myntra.com"].marketplace is True
    assert by_domain["myntra.com"].context_only is True
    assert by_domain["jaypore.com"].marketplace is False
    assert by_domain["jaypore.com"].context_only is False
    assert any("context" in note for note in notes)
    conn.close()


def test_immersive_store_links_choose_ads_domains_and_skip_marketplaces(tmp_path):
    seen = []

    def live(params, api_key):
        seen.append(params["text"])
        return {
            "search_metadata": {"id": params["text"]},
            "search_information": {"total_results": 12},
            "ad_creatives": [{"format": "text", "advertiser": params["text"]}],
        }

    client, conn = _client(tmp_path, live)
    fixture = json.loads(
        (Path(__file__).resolve().parents[1] / "fixtures" / "google_immersive_product__brass-diya-top.json").read_text(
            encoding="utf-8"
        )
    )
    recorded = normalize_immersive(fixture)
    assert advertiser_domains(recorded.stores) == ["craftvatika.com"]
    assert all("desertcart" not in (store.link or "") for store in recorded.stores)

    stores = [
        StoreOffer(name="Flipkart", link="https://dl.flipkart.com/dl/candle", price=199),
        StoreOffer(name="Myntra", link="https://m.myntra.com/candle", price=249),
        StoreOffer(name="Shoppers Stop", link="https://www.shoppersstop.com/candle", price=399),
        StoreOffer(name="Shoppers Stop", link="https://m.shoppersstop.com/other", price=449),
        StoreOffer(name="Desertcart.in", link="https://www.desertcart.in/products/candle", price=4532),
        StoreOffer(name="Local Wick", link="https://shop.localwick.co.in/candle", price=299),
    ]
    assert registrable_domain("dl.flipkart.com") == "flipkart.com"
    assert registrable_domain("shop.localwick.co.in") == "localwick.co.in"
    assert advertiser_domains(stores) == ["localwick.co.in"]
    assert is_general_retailer("www.shoppersstop.com")
    shopping = ShoppingResult(
        offers=[Offer(origin="shopping", title="candle", price=199, merchant="Flipkart")],
        merchants=[
            MerchantStat(name="Flipkart", count=5, domain="flipkart.com"),
            MerchantStat(name="Myntra", count=4, domain="myntra.com"),
            MerchantStat(name="Jaypore", count=1, domain="jaypore.com"),
        ],
    )
    ads, _notes = _ads(
        client,
        shopping,
        date(2026, 9, 27),
        [],
        lambda params, purpose: client.search(params),
        stores=stores,
    )
    assert seen == ["localwick.co.in", "jaypore.com"]
    assert [ad.domain for ad in ads] == seen
    assert "shoppersstop.com" not in seen
    assert "flipkart.com" not in seen
    assert "myntra.com" not in seen
    assert "desertcart.in" not in seen
    conn.close()


def test_general_retailers_are_context_only_and_do_not_drive_pressure(tmp_path):
    named = [
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
    ]
    assert all(is_general_retailer(host) for host in named)
    assert is_general_retailer("m.shoppersstop.com")
    assert not is_general_retailer("jaypore.com")
    assert not is_general_retailer("fnp.com")
    assert not is_general_retailer("craftvatika.com")
    only_retail = [
        StoreOffer(name="Shoppers Stop", link="https://www.shoppersstop.com/candle", price=399),
        StoreOffer(name="IKEA", link="https://www.ikea.com/in/p/candle", price=299),
    ]
    assert advertiser_domains(only_retail) == []

    seen = []

    def live(params, api_key):
        seen.append(params["text"])
        total = 800 if params["text"] == "shoppersstop.com" else 12
        return {
            "search_metadata": {"id": params["text"]},
            "search_information": {"total_results": total},
            "ad_creatives": [{"format": "text", "advertiser": params["text"]}],
        }

    client, conn = _client(tmp_path, live)
    shopping = ShoppingResult(
        offers=[Offer(origin="shopping", title="candle", price=399)],
        merchants=[
            MerchantStat(name="Myntra", count=4, domain="myntra.com"),
            MerchantStat(name="Jaypore", count=1, domain="jaypore.com"),
        ],
    )
    _ads(
        client,
        shopping,
        date(2026, 9, 27),
        [],
        lambda params, purpose: client.search(params),
        stores=only_retail,
    )
    assert seen[0] == "jaypore.com"
    assert "shoppersstop.com" not in seen

    catalogue = ShoppingResult(
        offers=[Offer(origin="shopping", title="candle", price=399)],
        merchants=[MerchantStat(name="Shoppers Stop", count=3, domain="shoppersstop.com")],
    )
    ads, notes = _ads(
        client,
        catalogue,
        date(2026, 9, 27),
        [],
        lambda params, purpose: client.search(params),
        stores=only_retail,
    )
    assert any(ad.domain == "shoppersstop.com" and ad.context_only and not ad.marketplace for ad in ads)
    kept = [ad.total_results for ad in ads if not ad.context_only and not ad.marketplace]
    assert ads_pressure(kept, None) != "high"
    assert any("context" in note for note in notes)
    conn.close()


def test_one_usable_store_host_fills_the_second_ads_slot(tmp_path):
    seen = []

    def live(params, api_key):
        seen.append(params["text"])
        return {
            "search_metadata": {"id": params["text"]},
            "search_information": {"total_results": 12},
            "ad_creatives": [{"format": "text", "advertiser": params["text"]}],
        }

    client, conn = _client(tmp_path, live)
    shopping = ShoppingResult(
        offers=[Offer(origin="shopping", title="candle", price=299)],
        merchants=[
            MerchantStat(name="Myntra", count=5, domain="myntra.com"),
            MerchantStat(name="Jaypore", count=1, domain="jaypore.com"),
        ],
    )
    one = [StoreOffer(name="Local Wick", link="https://shop.localwick.co.in/candle", price=299)]
    _ads(
        client,
        shopping,
        date(2026, 9, 27),
        [],
        lambda params, purpose: client.search(params),
        stores=one,
    )
    assert seen == ["localwick.co.in", "jaypore.com"]

    two = one + [StoreOffer(name="Debayan Crafts", link="https://debayancrafts.com/p", price=500)]
    ads, _notes = _ads(
        client,
        shopping,
        date(2026, 9, 27),
        [],
        lambda params, purpose: client.search(params),
        stores=two,
    )
    assert [ad.domain for ad in ads] == ["debayancrafts.com", "localwick.co.in"]
    assert "jaypore.com" not in [ad.domain for ad in ads]
    conn.close()


def test_shopping_rows_without_store_links_fall_back_to_the_map(tmp_path):
    seen = []

    def live(params, api_key):
        seen.append(params["text"])
        return {
            "search_metadata": {"id": params["text"]},
            "search_information": {"total_results": 12},
            "ad_creatives": [{"format": "text", "advertiser": params["text"]}],
        }

    client, conn = _client(tmp_path, live)
    shopping = ShoppingResult(
        offers=[
            Offer(
                origin="shopping",
                title="candle",
                price=299,
                merchant="Wick & Co",
                link="https://wickandco.in/candle",
            )
        ],
        merchants=[
            MerchantStat(name="Myntra", count=5, domain="myntra.com"),
            MerchantStat(name="Jaypore", count=1, domain="jaypore.com"),
        ],
    )
    _ads(client, shopping, date(2026, 9, 27), [], lambda params, purpose: client.search(params))
    assert seen[0] == "jaypore.com"
    assert "wickandco.in" not in seen
    conn.close()


def test_debayan_is_not_ebay_and_marketplace_subdomains_are_not_advertisers():
    assert not is_foreign("Debayan Crafts", "https://debayancrafts.com/brass-diya")
    assert advertiser_domains(
        [StoreOffer(name="Debayan Crafts", link="https://www.debayancrafts.com/p", price=500)]
    ) == ["debayancrafts.com"]
    assert is_foreign("Desert Cart", None)
    assert is_foreign("Desertcart.in", "https://desertcart.in/p")
    assert is_foreign("eBay", "https://www.ebay.com/itm/1")
    assert advertiser_domains(
        [
            StoreOffer(name="Flipkart", link="https://dl.flipkart.com/x", price=1),
            StoreOffer(name="Myntra", link="https://m.myntra.com/x", price=1),
        ]
    ) == []


def test_ads_fall_back_to_the_merchant_map_when_no_usable_hostname(tmp_path):
    seen = []

    def live(params, api_key):
        seen.append(params["text"])
        return {
            "search_metadata": {"id": params["text"]},
            "search_information": {"total_results": 12},
            "ad_creatives": [{"format": "text", "advertiser": params["text"]}],
        }

    client, conn = _client(tmp_path, live)
    shopping = ShoppingResult(
        offers=[
            Offer(
                origin="shopping",
                title="candle",
                price=199,
                merchant="Flipkart",
                link="https://www.flipkart.com/candle",
            ),
            Offer(origin="shopping", title="candle", price=100, merchant="Jaypore"),
        ],
        merchants=[
            MerchantStat(name="Myntra", count=5, domain="myntra.com"),
            MerchantStat(name="Jaypore", count=1, domain="jaypore.com"),
            MerchantStat(name="Flipkart", count=4, domain="flipkart.com"),
        ],
    )
    assert advertiser_domains(shopping.offers) == []
    _ads(client, shopping, date(2026, 9, 27), [], lambda params, purpose: client.search(params))
    assert seen[0] == "jaypore.com"
    assert len(seen) == 2
    conn.close()


def test_zero_interest_states_are_not_recommended():
    states = [
        StateInterest(geo="IN-KA", location="Karnataka", value=100),
        StateInterest(geo="IN-BR", location="Bihar", value=0),
        StateInterest(geo="IN-MH", location="Maharashtra", value=0),
    ]
    picked, _ = recommend_states(states, ["IN-MH", "IN-KA", "IN-DL"])
    assert picked == ["Karnataka"]


def test_every_kept_listing_lands_in_a_band():
    # 137 snaps up to 140 and 1,249 snaps down to 1,200; both must still be counted.
    prices = [137, 150, 180, 220, 260, 300, 420, 600, 800, 1249]
    offers = [Offer(origin="shopping", title=str(p), price=p) for p in prices]
    bands = build_bands(offers, target=300)
    assert sum(band.count for band in bands) == len(prices)
    assert bands[0].low <= 137 and bands[-1].high >= 1249


def test_target_on_a_boundary_marks_exactly_one_band():
    prices = [100, 150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 650]
    offers = [Offer(origin="shopping", title=str(p), price=p) for p in prices]
    for band_edge in {b.high for b in build_bands(offers, target=0)}:
        bands = build_bands(offers, target=band_edge)
        assert sum(1 for band in bands if band.contains_target) <= 1
    bands = build_bands(offers, target=300)
    assert sum(1 for band in bands if band.contains_target) == 1
