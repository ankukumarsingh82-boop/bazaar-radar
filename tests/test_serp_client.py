import socket
from datetime import date

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import connect, init_db
from app.main import create_app
from app.serp_client import SerpClient
from app.sources.trends import five_year_params, yoy_params


class Boom(socket.socket):
    def connect(self, *args, **kwargs):
        raise AssertionError("fixture mode tried to use the network")


def test_fixture_mode_matches_yoy_and_five_year_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(socket, "socket", Boom)
    settings = Settings(
        serpapi_api_key="",
        br_mode="fixtures",
        db_path=tmp_path / "t.sqlite",
    )
    conn = connect(settings.db_path)
    init_db(conn)
    client = SerpClient(settings, conn, "t1")
    yoy = client.search(yoy_params("brass diya", date(2026, 9, 26)))
    assert yoy.source == "fixture"
    assert yoy.search_id
    five = client.search(five_year_params("rangoli"))
    assert five.source == "fixture"
    assert five.file.endswith("5y-diya-rangoli-diwali-gift.json")
    missing = client.search(yoy_params("kurta set", date(2026, 9, 26)))
    assert missing.source == "missing"
    account = client.account()
    assert account["plan_searches_left"] is None
    assert account["mode"] == "fixtures"
    assert account["message"].startswith("Fixture mode")
    conn.close()


def test_cache_mode_without_a_key_reports_cache_not_fixture_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(socket, "socket", Boom)
    settings = Settings(
        serpapi_api_key="",
        br_mode="cache",
        db_path=tmp_path / "t.sqlite",
    )
    conn = connect(settings.db_path)
    init_db(conn)
    client = SerpClient(settings, conn, "t-cache")
    account = client.account()
    assert account["mode"] == "cache"
    assert account["plan_searches_left"] is None
    assert "Fixture mode" not in account["message"]
    assert account["message"].startswith("Cache mode")
    conn.close()
    app = create_app(settings)
    with TestClient(app) as http:
        page = http.get("/credits")
        body = http.get("/credits", headers={"accept": "application/json"})
    assert page.status_code == 200
    assert "Fixture mode" not in page.text
    assert "cache, 0 credits" in page.text
    assert body.json()["mode"] == "cache"
    assert "Fixture mode" not in body.json()["message"]


def test_cache_serves_the_second_call_and_live_is_guarded(tmp_path):
    settings = Settings(
        serpapi_api_key="test-key",
        br_mode="cache",
        db_path=tmp_path / "t.sqlite",
        daily_cap=40,
        max_live_calls_per_report=2,
        min_searches_left=20,
    )
    conn = connect(settings.db_path)
    init_db(conn)
    calls = {"n": 0}

    def live(params, api_key):
        calls["n"] += 1
        assert api_key == "test-key"
        return {
            "search_metadata": {
                "id": "abc",
                "json_endpoint": "https://serpapi.com/searches/abc.json?api_key=test-key",
            },
            "organic_results": [],
        }

    def account(api_key):
        return {"plan_searches_left": 25, "this_month_usage": 1, "plan_name": "Free Plan"}

    client = SerpClient(settings, conn, "r1", live_search=live, account_fetch=account)
    params = {"engine": "amazon", "k": "brass diya", "amazon_domain": "amazon.in"}
    first = client.search(params)
    second = client.search(params)
    assert first.source == "live"
    assert second.source == "cache"
    assert calls["n"] == 1
    assert "api_key" not in (first.json_endpoint or "")
    third = client.search({"engine": "amazon", "k": "other", "amazon_domain": "amazon.in"})
    assert third.source == "live"
    blocked = client.search({"engine": "amazon", "k": "third", "amazon_domain": "amazon.in"})
    assert blocked.source == "blocked"
    assert "live searches" in (blocked.error or "")
    conn.close()


def test_hard_stop_below_20_credits(tmp_path):
    settings = Settings(
        serpapi_api_key="test-key",
        br_mode="live",
        db_path=tmp_path / "t.sqlite",
        min_searches_left=20,
    )
    conn = connect(settings.db_path)
    init_db(conn)

    def live(params, api_key):
        raise AssertionError("should not spend a search")

    def account(api_key):
        return {"plan_searches_left": 19}

    client = SerpClient(settings, conn, "r2", live_search=live, account_fetch=account)
    hit = client.search({"engine": "amazon", "k": "diya", "amazon_domain": "amazon.in"})
    assert hit.source == "blocked"
    assert "19" in (hit.error or "")
    conn.close()


def test_daily_cap(tmp_path):
    settings = Settings(
        serpapi_api_key="test-key",
        br_mode="live",
        db_path=tmp_path / "t.sqlite",
        daily_cap=1,
        max_live_calls_per_report=14,
    )
    conn = connect(settings.db_path)
    init_db(conn)

    def live(params, api_key):
        return {"search_metadata": {"id": "x"}, "ok": True}

    def account(api_key):
        return {"plan_searches_left": 200}

    client = SerpClient(settings, conn, "r3", live_search=live, account_fetch=account)
    assert (
        client.search({"engine": "amazon", "k": "one", "amazon_domain": "amazon.in"}).source
        == "live"
    )
    blocked = client.search({"engine": "amazon", "k": "two", "amazon_domain": "amazon.in"})
    assert blocked.source == "blocked"
    assert "Daily cap" in (blocked.error or "")
    conn.close()
