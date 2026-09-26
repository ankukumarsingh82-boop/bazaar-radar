"""Guard the disqualification case: fixtures and env files carry no API key."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_fixtures_have_no_api_key():
    fixture_dir = ROOT / "fixtures"
    assert fixture_dir.exists()
    for path in fixture_dir.iterdir():
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert "api_key" not in text.lower(), path.name
        assert "SERPAPI_API_KEY" not in text, path.name


def test_env_example_has_an_empty_key():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert re.search(r"^SERPAPI_API_KEY=\s*$", text, re.M)
    assert not re.search(r"^SERPAPI_API_KEY=.+", text, re.M)
