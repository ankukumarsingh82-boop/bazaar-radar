"""Serverless filesystem and the fixture-mode default on Vercel."""

from pathlib import Path

from app.config import ROOT, get_settings
from app.db import connect, init_db


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
