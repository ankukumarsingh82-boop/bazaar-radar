"""Serverless filesystem and the fixture-mode default on Vercel."""

import os
import socket
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app.boot import PROCESS_FALLBACKS, load_kolkata
from app.config import ROOT, Settings, get_settings
from app.db import connect, init_db
from app.main import create_app
from app.serp_client import SerpClient


class _Boom(socket.socket):
    def connect(self, *args, **kwargs):
        raise AssertionError("network")


def test_local_settings_keep_the_data_directory(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("BR_DB_PATH", raising=False)
    monkeypatch.delenv("BR_MODE", raising=False)
    monkeypatch.setenv("SERPAPI_API_KEY", "")
    settings = get_settings()
    assert settings.db_path == ROOT / "data" / "bazaar.sqlite"
    assert settings.mode == "fixtures"
    assert settings.on_vercel is False


def test_vercel_uses_tmp_and_stays_offline_even_with_a_key(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("SERPAPI_API_KEY", "secret-not-used")
    monkeypatch.delenv("BR_MODE", raising=False)
    monkeypatch.delenv("BR_DB_PATH", raising=False)
    settings = get_settings()
    assert settings.db_path == Path("/tmp/bazaar-radar/bazaar.sqlite")
    assert settings.mode == "fixtures"
    assert settings.on_vercel is True
    conn = connect(settings.db_path)
    init_db(conn)
    conn.execute("SELECT COUNT(*) FROM reports")
    conn.close()


def test_explicit_br_mode_still_wins_on_vercel(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("BR_MODE", "cache")
    monkeypatch.setenv("SERPAPI_API_KEY", "k")
    monkeypatch.delenv("BR_DB_PATH", raising=False)
    assert get_settings().mode == "cache"


def test_unwritable_db_path_falls_back_to_tmp(tmp_path):
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("x", encoding="utf-8")
    fallback = Path("/tmp/bazaar-radar/fallback-check.sqlite")
    fallback.unlink(missing_ok=True)
    conn = connect(blocked / "fallback-check.sqlite")
    init_db(conn)
    conn.execute(
        "INSERT INTO reports (id, created_at, keyword, payload_json) VALUES ('a', 't', 'k', '{}')"
    )
    conn.commit()
    assert conn.execute("SELECT COUNT(*) AS n FROM reports").fetchone()["n"] == 1
    conn.close()
    assert fallback.exists()


def test_empty_numeric_env_does_not_force_fixtures(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setenv("SERPAPI_DAILY_CAP", "  ")
    monkeypatch.setenv("BR_MODE", "cache")
    monkeypatch.setenv("SERPAPI_API_KEY", "k")
    monkeypatch.delenv("BR_DB_PATH", raising=False)
    monkeypatch.delenv("BR_FIXTURES_DIR", raising=False)
    settings = get_settings()
    assert settings.mode == "cache"
    assert settings.daily_cap == 40
    assert "env:daily-cap" not in settings.startup_fallbacks


def test_bad_numeric_env_forces_fixtures_and_healthz_hides_the_key(tmp_path, monkeypatch):
    monkeypatch.setattr(socket, "socket", _Boom)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setenv("SERPAPI_API_KEY", "super-secret-key")
    monkeypatch.setenv("SERPAPI_DAILY_CAP", "nope")
    monkeypatch.setenv("MAX_LIVE_CALLS_PER_REPORT", "lots")
    monkeypatch.setenv("MIN_SEARCHES_LEFT", "x")
    monkeypatch.setenv("BR_MODE", "live")
    monkeypatch.setenv("BR_DB_PATH", str(tmp_path / "ok.sqlite"))
    monkeypatch.delenv("BR_FIXTURES_DIR", raising=False)
    settings = get_settings()
    assert settings.mode == "fixtures"
    assert settings.daily_cap == 40
    assert "env:daily-cap" in settings.startup_fallbacks
    assert "env:max-live-calls" in settings.startup_fallbacks
    assert "env:min-searches-left" in settings.startup_fallbacks
    assert "mode:fixtures" in settings.startup_fallbacks
    app = create_app(settings)
    with TestClient(app) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        body = health.json()
        assert body["ok"] is True
        assert body["mode"] == "fixtures"
        assert "env:daily-cap" in body["fallbacks"]
        assert "mode:fixtures" in body["fallbacks"]
        assert "super-secret-key" not in health.text
        home = client.get("/")
        assert home.status_code == 200
        assert "super-secret-key" not in home.text
        page = client.get("/s/rangoli-colours")
        assert page.status_code == 200
        assert "super-secret-key" not in page.text


def test_unknown_mode_and_missing_fixtures_dir_force_fixtures(monkeypatch, tmp_path):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setenv("BR_MODE", "production")
    monkeypatch.setenv("SERPAPI_API_KEY", "k")
    monkeypatch.setenv("BR_FIXTURES_DIR", str(tmp_path / "missing-fixtures"))
    monkeypatch.delenv("BR_DB_PATH", raising=False)
    settings = get_settings()
    assert settings.mode == "fixtures"
    assert settings.fixtures_dir == ROOT / "fixtures"
    assert "env:mode" in settings.startup_fallbacks
    assert "env:fixtures-dir" in settings.startup_fallbacks


def test_bad_env_is_logged(caplog, monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setenv("SERPAPI_DAILY_CAP", "nope")
    monkeypatch.delenv("BR_MODE", raising=False)
    monkeypatch.setenv("SERPAPI_API_KEY", "")
    monkeypatch.delenv("BR_DB_PATH", raising=False)
    monkeypatch.delenv("BR_FIXTURES_DIR", raising=False)
    with caplog.at_level("ERROR", logger="bazaar.startup"):
        settings = get_settings()
    assert settings.mode == "fixtures"
    assert any("env:daily-cap" in record.message for record in caplog.records)


def test_connect_falls_back_to_memory_when_disk_open_fails(monkeypatch):
    def boom(path):
        raise OSError("read-only")

    monkeypatch.setattr("app.db._open", boom)
    bucket: list[str] = []
    conn = connect(Path("/tmp/bazaar-radar/will-not-open.sqlite"), bucket)
    init_db(conn)
    conn.execute("SELECT 1")
    assert "db:memory" in bucket
    assert "db:configured" in bucket
    conn.close()


def test_account_failure_stays_up_and_hides_the_key(tmp_path, monkeypatch):
    monkeypatch.setattr(socket, "socket", _Boom)

    def boom(api_key: str):
        raise RuntimeError(f"https://serpapi.com/account.json?api_key={api_key}")

    monkeypatch.setattr("app.serp_client.default_account_fetch", boom)
    settings = Settings(
        serpapi_api_key="super-secret-key",
        br_mode="live",
        db_path=tmp_path / "db.sqlite",
        startup_fallbacks=[],
    )
    app = create_app(settings)
    with TestClient(app) as client:
        home = client.get("/")
        assert home.status_code == 200
        assert "super-secret-key" not in home.text
        health = client.get("/healthz")
        assert health.status_code == 200
        assert "meter:offline" in health.json()["fallbacks"]
        assert "super-secret-key" not in health.text


def test_live_search_error_redacts_the_key(tmp_path):
    settings = Settings(
        serpapi_api_key="super-secret-key",
        br_mode="live",
        db_path=tmp_path / "db.sqlite",
        min_searches_left=0,
        startup_fallbacks=[],
    )
    conn = connect(settings.db_path)
    init_db(conn)

    def boom(params, api_key):
        raise RuntimeError(f"https://serpapi.com/search.json?api_key={api_key}&q=diya")

    client = SerpClient(
        settings,
        conn,
        "t",
        live_search=boom,
        account_fetch=lambda api_key: {"plan_searches_left": 100, "this_month_usage": 0},
    )
    hit = client.search({"engine": "google", "q": "diya"})
    assert hit.source == "blocked"
    assert "super-secret-key" not in (hit.error or "")
    conn.close()


def test_report_build_failure_returns_200_without_the_exception(tmp_path, monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("secret-key-in-trace")

    monkeypatch.setattr("app.main.build_report", boom)
    app = create_app(Settings(br_mode="fixtures", db_path=tmp_path / "db.sqlite"))
    with TestClient(app) as client:
        page = client.get("/s/rangoli-colours")
        assert page.status_code == 200
        assert "secret-key-in-trace" not in page.text
        assert "page:failed" in client.get("/healthz").json()["fallbacks"]


def test_import_and_lifespan_survive_a_hostile_environment():
    env = os.environ.copy()
    env.update(
        {
            "VERCEL": "1",
            "SERPAPI_API_KEY": "super-secret-key",
            "SERPAPI_DAILY_CAP": "nope",
            "MAX_LIVE_CALLS_PER_REPORT": "lots",
            "MIN_SEARCHES_LEFT": "x",
            "BR_MODE": "live",
            "BR_DB_PATH": "/this/is/not/a/writable/directory/bazaar.sqlite",
            "BR_FIXTURES_DIR": "/no/such/fixtures",
            "PYTHONPATH": str(ROOT),
        }
    )
    script = """
from fastapi.testclient import TestClient
import app.main

with TestClient(app.main.app) as client:
    health = client.get("/healthz")
    assert health.status_code == 200, health.text
    body = health.json()
    assert body["ok"] is True
    assert body["mode"] == "fixtures"
    assert "env:daily-cap" in body["fallbacks"]
    assert "mode:fixtures" in body["fallbacks"]
    assert "super-secret-key" not in health.text
    home = client.get("/")
    assert home.status_code == 200
    assert "super-secret-key" not in home.text
    page = client.get("/s/rangoli-colours")
    assert page.status_code == 200
    assert "super-secret-key" not in page.text
print("ok")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "super-secret-key" not in result.stdout
    assert "super-secret-key" not in result.stderr


def test_missing_timezone_data_uses_a_fixed_offset(monkeypatch):
    saved = list(PROCESS_FALLBACKS)

    def boom(key):
        from zoneinfo import ZoneInfoNotFoundError

        raise ZoneInfoNotFoundError(key)

    monkeypatch.setattr("zoneinfo.ZoneInfo", boom)
    try:
        tz = load_kolkata()
        assert tz.utcoffset(None) == timedelta(hours=5, minutes=30)
        assert "timezone:fixed-offset" in PROCESS_FALLBACKS
    finally:
        PROCESS_FALLBACKS[:] = saved
