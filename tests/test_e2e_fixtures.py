import socket

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.orchestrator import build_report
from app.scenarios import SCENARIOS


class Boom(socket.socket):
    def connect(self, *args, **kwargs):
        raise AssertionError("network")


def _settings(tmp_path):
    return Settings(serpapi_api_key="", br_mode="fixtures", db_path=tmp_path / "bazaar.sqlite")


def test_three_scenarios_run_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(socket, "socket", Boom)
    settings = _settings(tmp_path)
    reports = {}
    for slug, scenario in SCENARIOS.items():
        report = build_report(
            keyword=scenario.keyword,
            head_term=scenario.head_term,
            variants=scenario.variants,
            target_price=scenario.target_price,
            states=scenario.states,
            category=scenario.category,
            settings=settings,
            today=__import__("datetime").date(2026, 9, 26),
        )
        reports[slug] = report
        assert report.usage.live == 0
        assert report.usage.cache == 0
        assert report.decision.verdict in {"GO", "GO-with-positioning", "CAUTION", "SKIP"}
        assert report.demand.states
        assert report.competition.bands
        assert report.complaints
        assert "api_key" not in report.model_dump_json()
        assert all(
            item.engine != "google_trends" or "gprop" not in item.params for item in report.evidence
        )
        assert not any(item.params.get("gprop") == "froogle" for item in report.evidence)

    brass = reports["brass-diya"]
    assert brass.demand.momentum_label == "Rising"
    assert brass.demand.momentum is not None and brass.demand.momentum > 1.2
    assert brass.demand.used_head_term
    assert brass.competition.sponsored_share is None
    assert any(ad.domain == "jaypore.com" for ad in brass.ads)
    assert any(row.theme == "Size" for row in brass.complaints)

    rangoli = reports["rangoli-colours"]
    assert rangoli.demand.days_before is not None
    assert rangoli.competition.sponsored_share == 12 / 60
    assert any(row.theme == "Quality" for row in rangoli.complaints)

    hamper = reports["diwali-gift-hamper"]
    assert hamper.demand.momentum is None
    assert "not enough" in hamper.demand.momentum_source
    assert hamper.ads_pressure == "high"
    assert hamper.decision.verdict in {"CAUTION", "SKIP"}
    assert hamper.demand.sparse or hamper.decision.confidence != "high"
    assert any(ad.domain == "fnp.com" for ad in hamper.ads)


def test_http_report_and_markdown(tmp_path, monkeypatch):
    monkeypatch.setattr(socket, "socket", Boom)
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        _assert_http(client)


def _assert_http(client):
    home = client.get("/")
    assert home.status_code == 200
    assert "Know the gap before you stock." in home.text
    assert "cheapest offer" not in home.text.lower() or "never" in home.text.lower()
    page = client.get("/s/brass-diya")
    assert page.status_code == 200
    assert "Bazaar Radar" in page.text
    assert "jaypore.com" in page.text
    report_id = page.text.split("/report/")[1].split(".md")[0]
    markdown = client.get(f"/report/{report_id}.md")
    assert markdown.status_code == 200
    assert "Verdict" in markdown.text
    assert "api_key" not in markdown.text
    credits = client.get("/credits", headers={"accept": "application/json"})
    assert credits.json()["plan_searches_left"] is None
