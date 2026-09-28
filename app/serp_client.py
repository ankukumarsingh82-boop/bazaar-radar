"""One door for SerpApi: fixtures, SQLite cache, live calls, and credit guardrails."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from app.boot import IST, note, note_process
from app.config import Settings

ACCOUNT_URL = "https://serpapi.com/account.json"

_DROP_KEYS = {"api_key", "device", "output", "no_cache"}

# SerpApi bills these and the answer is stable, so they are cached like real results.
_EMPTY_RESULT_MARKERS = ("hasn't returned any results", "has not returned any results")


def is_empty_result(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    error = str(payload.get("error") or "").lower()
    return any(marker in error for marker in _EMPTY_RESULT_MARKERS)


def _norm_params(params: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in params.items():
        if value is None or key in _DROP_KEYS:
            continue
        if isinstance(value, bool):
            text = "true" if value else "false"
        else:
            text = str(value).strip()
        if text == "":
            continue
        out[key] = text
    return out


def signature(params: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    norm = _norm_params(params)
    keys = (
        "engine",
        "q",
        "k",
        "asin",
        "text",
        "page_token",
        "data_type",
        "date",
        "gprop",
        "region",
        "geo",
        "amazon_domain",
        "gl",
        "location",
        "google_domain",
        "start_date",
        "end_date",
        "tz",
        "hl",
        "num",
        "more_stores",
    )
    return tuple((key, norm[key]) for key in keys if key in norm)


def scrub(obj: Any, secret: str = "") -> Any:
    if isinstance(obj, dict):
        return {k: scrub(v, secret) for k, v in obj.items() if k != "api_key"}
    if isinstance(obj, list):
        return [scrub(v, secret) for v in obj]
    if isinstance(obj, str):
        text = obj.replace(secret, "REDACTED") if secret else obj
        text = re.sub(r"([?&])api_key=[^&\s\"]+", r"\1", text)
        return text
    return obj


def cache_key(params: dict[str, Any]) -> str:
    blob = json.dumps(_norm_params(params), sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def _terms(query: str) -> list[str]:
    return [part.strip().lower() for part in query.split(",") if part.strip()]


def _term_compatible(fixture_q: str, wanted_q: str) -> bool:
    wanted = _terms(wanted_q)
    have = _terms(fixture_q)
    if not wanted or not have:
        return False

    def one(left: str, right: str) -> bool:
        return left == right or left.startswith(right + " ") or right.startswith(left + " ")

    return all(any(one(term, other) for other in have) for term in wanted)


@dataclass
class FixtureEntry:
    file: str
    norm: dict[str, str]
    data: dict[str, Any]


_STORES: dict[str, "FixtureStore"] = {}


def get_fixture_store(path: Path) -> "FixtureStore":
    try:
        key = str(path.resolve()) if path.exists() else str(path)
    except OSError:
        key = str(path)
    store = _STORES.get(key)
    if store is None:
        store = FixtureStore(path)
        _STORES[key] = store
    return store


class FixtureStore:
    def __init__(self, path: Path):
        self.path = path
        self.entries: list[FixtureEntry] = []
        self.by_sig: dict[tuple, FixtureEntry] = {}
        self._load()

    def _load(self) -> None:
        try:
            self._load_entries()
        except Exception as exc:
            note_process("fixtures:unreadable", exc)
            self.entries = []
            self.by_sig = {}

    def _load_entries(self) -> None:
        ledger = self.path / "_ledger.jsonl"
        by_file: dict[str, dict[str, Any]] = {}
        if ledger.exists():
            for line in ledger.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                by_file[row["file"]] = row.get("params") or {}
        for file_name, params in by_file.items():
            file_path = self.path / file_name
            if not file_path.exists():
                continue
            data = json.loads(file_path.read_text(encoding="utf-8"))
            norm = _norm_params(params)
            entry = FixtureEntry(file=file_name, norm=norm, data=data)
            self.entries.append(entry)
            self.by_sig[signature(norm)] = entry

    def find(self, params: dict[str, Any]) -> FixtureEntry | None:
        norm = _norm_params(params)
        exact = self.by_sig.get(signature(norm))
        if exact is not None:
            return exact
        return self._relaxed(norm)

    def has_ads(self, domain: str) -> bool:
        domain = domain.lower()
        return any(
            e.norm.get("engine") == "google_ads_transparency_center"
            and e.norm.get("text", "").lower() == domain
            for e in self.entries
        )

    def has_token(self, token: str) -> bool:
        return any(
            e.norm.get("engine") == "google_immersive_product" and e.norm.get("page_token") == token
            for e in self.entries
        )

    def _relaxed(self, norm: dict[str, str]) -> FixtureEntry | None:
        engine = norm.get("engine")
        cands = [e for e in self.entries if e.norm.get("engine") == engine]
        gprop = norm.get("gprop", "")
        cands = [e for e in cands if e.norm.get("gprop", "") == gprop]
        data_type = norm.get("data_type")
        if data_type:
            cands = [e for e in cands if e.norm.get("data_type") == data_type]
        if not cands:
            return None

        if (
            engine == "google_trends"
            and data_type == "TIMESERIES"
            and "5-y" in norm.get("date", "")
        ):
            matched = [
                e
                for e in cands
                if "5-y" in e.norm.get("date", "")
                and _term_compatible(e.norm.get("q", ""), norm.get("q", ""))
            ]
            return matched[0] if matched else None

        def primary_ok(entry: FixtureEntry) -> bool:
            for key in ("q", "k", "asin", "text", "page_token"):
                if key in norm or key in entry.norm:
                    if norm.get(key, "") != entry.norm.get(key, ""):
                        return False
            if norm.get("region") and entry.norm.get("region"):
                if norm["region"].lower() != entry.norm["region"].lower():
                    return False
            return True

        cands = [e for e in cands if primary_ok(e)]
        if not cands:
            return None
        if norm.get("location"):
            located = [
                e for e in cands if e.norm.get("location", "").lower() == norm["location"].lower()
            ]
            if located:
                cands = located
        if norm.get("date"):
            dated = [e for e in cands if e.norm.get("date") == norm["date"]]
            if dated:
                cands = dated
        return cands[0]


@dataclass
class SearchHit:
    data: dict[str, Any] | None
    source: str  # fixture | cache | live | missing | blocked
    params: dict[str, str]
    search_id: str | None = None
    json_endpoint: str | None = None
    error: str | None = None
    file: str | None = None


@dataclass
class CallBudget:
    report_id: str
    hits: list[SearchHit] = field(default_factory=list)

    def add(self, hit: SearchHit) -> SearchHit:
        self.hits.append(hit)
        return hit

    def counts(self) -> dict[str, int]:
        tally = {"fixture": 0, "cache": 0, "live": 0, "missing": 0, "blocked": 0}
        for hit in self.hits:
            tally[hit.source] = tally.get(hit.source, 0) + 1
        return tally


class SerpClient:
    def __init__(
        self,
        settings: Settings,
        conn: sqlite3.Connection,
        report_id: str,
        *,
        live_search=None,
        account_fetch=None,
    ):
        self.settings = settings
        self.conn = conn
        self.report_id = report_id
        self.fixtures = get_fixture_store(settings.fixtures_dir)
        self.budget = CallBudget(report_id)
        self._lock = threading.Lock()
        self._live_reserved = 0
        self._credits_checked = False
        self._credits_left: int | None = None
        self._account_error: str | None = None
        self._account_payload: dict[str, Any] | None = None
        self._live_search = live_search or default_live_search
        self._account_fetch = account_fetch or default_account_fetch

    @property
    def mode(self) -> str:
        return self.settings.mode

    def search(self, params: dict[str, Any]) -> SearchHit:
        try:
            norm = _norm_params(params)
            return self._search_locked(norm)
        except Exception as exc:
            note("search:failed", exc, self.settings.startup_fallbacks)
            return SearchHit(data=None, source="blocked", params={}, error="Search failed.")

    def _search_locked(self, norm: dict[str, str]) -> SearchHit:
        with self._lock:
            if self.mode == "fixtures":
                return self.budget.add(self._from_fixtures(norm))
            if self.mode == "cache":
                cached = self._read_cache(norm)
                if cached is not None:
                    hit = self._hit_from_payload(cached, norm, "cache")
                    self._ledger(norm, "cache")
                    return self.budget.add(hit)
            blocked = self._block_reason(norm)
            if blocked:
                return self.budget.add(
                    SearchHit(data=None, source="blocked", params=norm, error=blocked)
                )
            self._live_reserved += 1
        try:
            payload = self._live_search(norm, self.settings.serpapi_api_key)
        except Exception as exc:  # noqa: BLE001 — surface upstream failures on the report
            with self._lock:
                self._live_reserved -= 1
            return self.budget.add(
                SearchHit(
                    data=None,
                    source="blocked",
                    params=norm,
                    error=str(scrub(str(exc), self.settings.serpapi_api_key)),
                )
            )
        payload = scrub(payload, self.settings.serpapi_api_key)
        if isinstance(payload, dict) and payload.get("error"):
            with self._lock:
                self._live_reserved = max(0, self._live_reserved - 1)
                if is_empty_result(payload):
                    self._write_cache(norm, payload)
                self._ledger(norm, "live")
            return self.budget.add(
                SearchHit(
                    data=payload,
                    source="live",
                    params=norm,
                    error=str(payload.get("error")),
                    search_id=(payload.get("search_metadata") or {}).get("id"),
                )
            )
        with self._lock:
            self._live_reserved = max(0, self._live_reserved - 1)
            self._write_cache(norm, payload)
            self._ledger(norm, "live")
        return self.budget.add(self._hit_from_payload(payload, norm, "live"))

    def account(self) -> dict[str, Any]:
        """Free Account API snapshot. Offline modes do not call the network."""
        if self.mode == "fixtures" or not self.settings.has_key:
            return self._offline_meter(self._offline_message())
        try:
            return self._account_live()
        except Exception as exc:
            note("meter:offline", exc, self.settings.startup_fallbacks)
            return self._offline_meter("Credit meter is unavailable. No live call was made.")

    def _offline_message(self) -> str:
        if self.mode == "fixtures":
            return "Fixture mode. No API key is used and no credits are spent."
        return f"{self.mode.capitalize()} mode. No API key is set, so no live call was made."

    def _offline_meter(self, message: str) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "plan_searches_left": None,
            "this_month_usage": None,
            "hard_stop": False,
            "message": message,
        }

    def _account_live(self) -> dict[str, Any]:
        with self._lock:
            self._ensure_credits()
            payload = self._account_payload or {}
            left = self._credits_left
            hard = left is not None and left < self.settings.min_searches_left
            if self._account_error:
                message = self._account_error
            elif hard:
                message = (
                    f"{left} searches left. Live calls are paused below "
                    f"{self.settings.min_searches_left}."
                )
            else:
                message = f"{left} searches left on the SerpApi plan."
            return {
                "mode": self.mode,
                "plan_searches_left": left,
                "this_month_usage": payload.get("this_month_usage"),
                "total_searches_left": payload.get("total_searches_left"),
                "plan_name": payload.get("plan_name"),
                "hard_stop": hard or bool(self._account_error),
                "message": message,
                "daily_used": self._daily_live_count(),
                "daily_cap": self.settings.daily_cap,
            }

    def _from_fixtures(self, norm: dict[str, str]) -> SearchHit:
        entry = self.fixtures.find(norm)
        if entry is None:
            return SearchHit(data=None, source="missing", params=norm, error="No recorded fixture")
        note = None
        if entry.norm.get("q") and norm.get("q") and entry.norm.get("q") != norm.get("q"):
            note = f"Matched recorded search q={entry.norm.get('q')}"
        hit = self._hit_from_payload(entry.data, norm, "fixture")
        hit.file = entry.file
        hit.error = note
        return hit

    def _hit_from_payload(
        self, payload: dict[str, Any], norm: dict[str, str], source: str
    ) -> SearchHit:
        meta = payload.get("search_metadata") or {}
        endpoint = meta.get("json_endpoint")
        if isinstance(endpoint, str):
            endpoint = scrub(endpoint, self.settings.serpapi_api_key)
        error = payload.get("error") if isinstance(payload, dict) else None
        return SearchHit(
            data=payload,
            source=source,
            params=norm,
            search_id=meta.get("id"),
            json_endpoint=endpoint,
            error=str(error) if error else None,
        )

    def _read_cache(self, norm: dict[str, str]) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT response_json FROM serp_cache WHERE cache_key = ?",
            (cache_key(norm),),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["response_json"])

    def _write_cache(self, norm: dict[str, str], payload: dict[str, Any]) -> None:
        meta = payload.get("search_metadata") or {}
        self.conn.execute(
            """
            INSERT INTO serp_cache (cache_key, engine, params_json, response_json, search_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                response_json = excluded.response_json,
                search_id = excluded.search_id,
                created_at = excluded.created_at
            """,
            (
                cache_key(norm),
                norm.get("engine", ""),
                json.dumps(norm, sort_keys=True),
                json.dumps(payload),
                meta.get("id"),
                _now(),
            ),
        )
        self.conn.commit()

    def _ledger(self, norm: dict[str, str], source: str) -> None:
        self.conn.execute(
            """
            INSERT INTO serp_ledger (created_at, engine, cache_key, source, report_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (_now(), norm.get("engine", ""), cache_key(norm), source, self.report_id),
        )
        self.conn.commit()

    def _daily_live_count(self) -> int:
        start = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0)
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM serp_ledger WHERE source = 'live' AND created_at >= ?",
            (start.isoformat(),),
        ).fetchone()
        return int(row["n"]) if row else 0

    def _block_reason(self, norm: dict[str, str]) -> str | None:
        if not self.settings.has_key:
            label = "fixture" if self.mode == "fixtures" else self.mode
            return f"SERPAPI_API_KEY is not set. Stay in {label} mode or add a key to .env."
        live_so_far = (
            sum(1 for hit in self.budget.hits if hit.source == "live") + self._live_reserved
        )
        if live_so_far >= self.settings.max_live_calls_per_report:
            return (
                f"This report already used {self.settings.max_live_calls_per_report} live searches."
            )
        if self._daily_live_count() + self._live_reserved >= self.settings.daily_cap:
            return f"Daily cap of {self.settings.daily_cap} live searches is reached."
        self._ensure_credits()
        if self._account_error:
            return self._account_error
        if self._credits_left is not None and self._credits_left < self.settings.min_searches_left:
            return (
                f"Only {self._credits_left} searches left. "
                f"Refusing live calls below {self.settings.min_searches_left}."
            )
        return None

    def _ensure_credits(self) -> None:
        if self._credits_checked:
            return
        self._credits_checked = True
        try:
            payload = self._account_fetch(self.settings.serpapi_api_key)
        except Exception as exc:  # noqa: BLE001
            note("meter:offline", exc, self.settings.startup_fallbacks)
            self._account_error = "Account API check failed. Live calls are paused."
            return
        if not isinstance(payload, dict) or "plan_searches_left" not in payload:
            self._account_error = (
                "Account API did not return plan_searches_left. Live calls are paused."
            )
            return
        self._account_payload = payload
        self._credits_left = int(payload["plan_searches_left"])


def _now() -> str:
    return datetime.now(IST).isoformat(timespec="seconds")


def default_live_search(params: dict[str, str], api_key: str) -> dict[str, Any]:
    from serpapi import Client

    client = Client(api_key=api_key, timeout=90)
    result = client.search(dict(params))
    data = result.data if hasattr(result, "data") else dict(result)
    return json.loads(json.dumps(data))


def default_account_fetch(api_key: str) -> dict[str, Any]:
    response = httpx.get(ACCOUNT_URL, params={"api_key": api_key}, timeout=30)
    response.raise_for_status()
    payload = response.json()
    return scrub(payload, api_key)
