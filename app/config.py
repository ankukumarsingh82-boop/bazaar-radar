"""Runtime settings. The API key is read from the environment only, never from source."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE lines into the environment without overriding existing vars."""
    env_path = path or ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class Settings(BaseModel):
    serpapi_api_key: str = ""
    br_mode: str = ""
    daily_cap: int = 40
    max_live_calls_per_report: int = 14
    min_searches_left: int = 20
    fixtures_dir: Path = Field(default_factory=lambda: ROOT / "fixtures")
    db_path: Path = Field(default_factory=lambda: ROOT / "data" / "bazaar.sqlite")

    @property
    def mode(self) -> str:
        if self.br_mode in {"fixtures", "cache", "live"}:
            return self.br_mode
        return "cache" if self.serpapi_api_key else "fixtures"

    @property
    def has_key(self) -> bool:
        return bool(self.serpapi_api_key.strip())


def get_settings() -> Settings:
    load_dotenv()
    mode = os.environ.get("BR_MODE", "").strip().lower()
    return Settings(
        serpapi_api_key=os.environ.get("SERPAPI_API_KEY", "").strip(),
        br_mode=mode,
        daily_cap=int(os.environ.get("SERPAPI_DAILY_CAP", "40")),
        max_live_calls_per_report=int(os.environ.get("MAX_LIVE_CALLS_PER_REPORT", "14")),
        min_searches_left=int(os.environ.get("MIN_SEARCHES_LEFT", "20")),
        fixtures_dir=Path(os.environ.get("BR_FIXTURES_DIR", ROOT / "fixtures")),
        db_path=Path(os.environ.get("BR_DB_PATH", ROOT / "data" / "bazaar.sqlite")),
    )
