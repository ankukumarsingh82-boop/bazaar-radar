"""Regressions found in the 27 Sep 2026 live check."""

from datetime import date

from app.analysis.demand import recommend_states
from app.analysis.pricebands import build_bands
from app.config import Settings
from app.db import connect, init_db
from app.models import MerchantStat, Offer, ShoppingResult, StateInterest
from app.orchestrator import _ads
from app.serp_client import SerpClient, is_empty_result

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
    assert by_domain["jaypore.com"].marketplace is False
    assert any("context" in note for note in notes)
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
