"""Re-record fixtures. This spends SerpApi credits. It does not run unless you pass --live.

Usage:
    uv run python scripts/record_fixtures.py --live --keyword "brass diya"

The day-1 recordings already live in fixtures/. Responses are written with api_key removed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.serp_client import scrub  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Record a sanitized SerpApi response")
    parser.add_argument("--live", action="store_true", help="Actually spend a search")
    parser.add_argument("--keyword", default="brass diya")
    args = parser.parse_args()
    if not args.live:
        print("Refusing to call SerpApi. Re-run with --live after reading docs/day1-findings.md.")
        print(f"Existing fixtures: {len(list((ROOT / 'fixtures').glob('*.json')))} json files")
        return
    settings = get_settings()
    if not settings.has_key:
        sys.exit("Set SERPAPI_API_KEY in .env first. Never pass the key on the command line.")
    from app.serp_client import default_account_fetch, default_live_search

    left = default_account_fetch(settings.serpapi_api_key).get("plan_searches_left")
    if left is None or int(left) < settings.min_searches_left:
        sys.exit(f"Only {left} searches left. Not recording.")
    params = {
        "engine": "google_shopping",
        "q": args.keyword,
        "gl": "in",
        "hl": "en",
        "google_domain": "google.co.in",
        "location": "India",
    }
    payload = scrub(default_live_search(params, settings.serpapi_api_key), settings.serpapi_api_key)
    slug = args.keyword.strip().lower().replace(" ", "-")
    dest = ROOT / "fixtures" / f"google_shopping__{slug}-rerecord.json"
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    assert settings.serpapi_api_key not in dest.read_text(encoding="utf-8")
    print(f"wrote {dest.name}")


if __name__ == "__main__":
    main()
