"""FastAPI routes for the form, the report, the credit meter, and Markdown export."""

from __future__ import annotations

import json
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.boot import note, public_fallbacks
from app.config import Settings, get_settings
from app.db import connect, init_db, memory_connection
from app.format import inr, pct, verdict_blurb, verdict_title
from app.markdown_export import to_markdown
from app.models import Report
from app.orchestrator import build_report
from app.scenarios import SCENARIOS, scenario_id_for
from app.serp_client import SerpClient
from app.states import CATEGORIES, STATE_NAMES, STATES

TEMPLATES = Path(__file__).resolve().parent / "templates"
STATIC = Path(__file__).resolve().parent / "static"


def _force_fixtures(settings: Settings) -> None:
    settings.force_fixtures = True
    if "mode:fixtures" not in settings.startup_fallbacks:
        settings.startup_fallbacks.append("mode:fixtures")


def _open_app_db(settings: Settings) -> sqlite3.Connection:
    before = len(settings.startup_fallbacks)
    conn = connect(settings.db_path, settings.startup_fallbacks)
    try:
        init_db(conn)
    except Exception as exc:
        note("db:memory", exc, settings.startup_fallbacks)
        conn = memory_connection()
        try:
            init_db(conn)
        except Exception as exc2:
            note("db:init", exc2, settings.startup_fallbacks)
    if len(settings.startup_fallbacks) != before:
        _force_fixtures(settings)
    return conn


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.fallbacks = settings.startup_fallbacks
        try:
            app.state.conn = _open_app_db(settings)
        except Exception as exc:  # connect() already swallows; this is a last resort
            note("db:memory", exc, settings.startup_fallbacks)
            _force_fixtures(settings)
            try:
                app.state.conn = memory_connection()
            except Exception as exc2:
                note("db:memory", exc2, settings.startup_fallbacks)
                app.state.conn = None
        try:
            yield
        finally:
            conn = getattr(app.state, "conn", None)
            if conn is not None:
                try:
                    conn.close()
                except Exception as exc:
                    note("db:close", exc, settings.startup_fallbacks)

    app = FastAPI(title="Bazaar Radar", lifespan=lifespan)
    app.state.settings = settings
    app.state.fallbacks = settings.startup_fallbacks
    if STATIC.is_dir():
        app.mount("/static", StaticFiles(directory=STATIC), name="static")
    else:
        note("static:missing", bucket=settings.startup_fallbacks)
    templates = Jinja2Templates(directory=TEMPLATES)
    templates.env.filters["inr"] = inr
    templates.env.filters["pct"] = pct
    templates.env.globals["verdict_title"] = verdict_title
    templates.env.globals["verdict_blurb"] = verdict_blurb
    templates.env.globals["state_name"] = lambda code: STATE_NAMES.get(code, code)

    def meter() -> dict:
        try:
            client = SerpClient(settings, app.state.conn, "meter")
            return client.account()
        except Exception as exc:
            note("meter:offline", exc, settings.startup_fallbacks)
            return {
                "mode": settings.mode,
                "plan_searches_left": None,
                "this_month_usage": None,
                "hard_stop": False,
                "message": "Credit meter is unavailable. No live call was made.",
            }

    def render(request: Request, template: str, **extra):
        try:
            return page(request, template, **extra)
        except HTTPException:
            raise
        except Exception as exc:
            note("page:failed", exc, settings.startup_fallbacks)
            return HTMLResponse(
                "<p>Bazaar Radar could not render this page.</p>"
                '<p><a href="/healthz">Health</a></p>',
                status_code=200,
            )

    def build_saved(**kwargs) -> Report | None:
        if getattr(app.state, "conn", None) is None:
            note("db:memory", bucket=settings.startup_fallbacks)
            _force_fixtures(settings)
            return None
        try:
            report = build_report(**kwargs, settings=settings, conn=app.state.conn)
        except Exception as exc:
            note("page:failed", exc, settings.startup_fallbacks)
            return None
        try:
            save(report)
        except Exception as exc:
            note("db:save", exc, settings.startup_fallbacks)
        return report

    def save(report: Report) -> None:
        conn: sqlite3.Connection = app.state.conn
        conn.execute(
            """
            INSERT INTO reports (id, created_at, keyword, payload_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET payload_json = excluded.payload_json
            """,
            (report.id, report.created_at, report.keyword, report.model_dump_json()),
        )
        conn.commit()

    def load(report_id: str) -> Report:
        row = app.state.conn.execute(
            "SELECT payload_json FROM reports WHERE id = ?",
            (report_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Report not found")
        return Report.model_validate_json(row["payload_json"])

    def page(request: Request, template: str, **extra):
        # The raw Scenario used to be spread after the computed prefill and
        # overwrite it, so the form showed a list repr and a float price.
        raw_prefill = extra.pop("prefill", None)
        report = extra.get("report")
        charts = json.dumps(_charts(report)).replace("<", "\\u003c") if report else "{}"
        prefill = _prefill(raw_prefill, report)
        return templates.TemplateResponse(
            request,
            template,
            {
                "settings_mode": settings.mode,
                "meter": meter(),
                "scenarios": SCENARIOS,
                "states": STATES,
                "categories": CATEGORIES,
                "charts": charts,
                "prefill": prefill,
                **extra,
            },
        )

    @app.get("/healthz")
    def healthz():
        return {
            "ok": True,
            "mode": settings.mode,
            "fallbacks": public_fallbacks(settings.startup_fallbacks),
        }

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        return render(request, "index.html", report=None, prefill=None)

    @app.get("/s/{slug}", response_class=HTMLResponse)
    def scenario_page(slug: str, request: Request):
        scenario = SCENARIOS.get(slug)
        if scenario is None:
            raise HTTPException(status_code=404, detail="Unknown scenario")
        report = None
        # Auto-run only offline. A GET in live mode must not spend credits.
        if settings.mode == "fixtures":
            report = build_saved(
                keyword=scenario.keyword,
                head_term=scenario.head_term,
                variants=scenario.variants,
                target_price=scenario.target_price,
                states=scenario.states,
                category=scenario.category,
                report_id=scenario.slug,
            )
        return render(request, "index.html", report=report, prefill=scenario)

    @app.post("/analyze", response_class=HTMLResponse)
    async def analyze(request: Request):
        form = await request.form()
        keyword = " ".join(str(form.get("keyword") or "").split())
        try:
            target_price = float(str(form.get("target_price") or "0"))
        except ValueError:
            target_price = 0
        if not keyword or target_price <= 0:
            return render(
                request,
                "index.html",
                report=None,
                prefill=None,
                error="Enter a product idea and a target price in rupees.",
            )
        states = [str(value) for value in form.getlist("states")]
        variants = [
            part.strip()
            for part in str(form.get("variants") or "").replace("\n", ",").split(",")
            if part.strip()
        ][:4]
        head_term = str(form.get("head_term") or "")
        category = str(form.get("category") or "Home & Décor")
        report_id = None
        if settings.mode == "fixtures":
            report_id = scenario_id_for(
                keyword, head_term, variants, target_price, states, category
            )
        report = build_saved(
            keyword=keyword,
            head_term=head_term,
            variants=variants,
            target_price=target_price,
            states=states,
            category=category,
            report_id=report_id,
        )
        if report is None:
            return render(
                request,
                "index.html",
                report=None,
                prefill=None,
                error="Could not build a report.",
            )
        if request.headers.get("HX-Request") == "true":
            try:
                return templates.TemplateResponse(
                    request,
                    "report_body.html",
                    {
                        "report": report,
                        "charts": json.dumps(_charts(report)).replace("<", "\\u003c"),
                    },
                )
            except Exception as exc:
                note("page:failed", exc, settings.startup_fallbacks)
                return HTMLResponse(
                    "<p>Bazaar Radar could not render this page.</p>",
                    status_code=200,
                )
        return render(request, "index.html", report=report, prefill=None)

    def _rebuild_scenario(report_id: str) -> Report | None:
        scenario = SCENARIOS.get(report_id)
        if scenario is None or settings.mode != "fixtures":
            return None
        return build_saved(
            keyword=scenario.keyword,
            head_term=scenario.head_term,
            variants=scenario.variants,
            target_price=scenario.target_price,
            states=scenario.states,
            category=scenario.category,
            report_id=scenario.slug,
        )

    def _loaded(report_id: str) -> Report:
        try:
            return load(report_id)
        except HTTPException:
            rebuilt = _rebuild_scenario(report_id)
            if rebuilt is not None:
                return rebuilt
            raise
        except Exception as exc:
            note("page:failed", exc, settings.startup_fallbacks)
            rebuilt = _rebuild_scenario(report_id)
            if rebuilt is not None:
                return rebuilt
            raise HTTPException(status_code=404, detail="Report not found") from None

    def _missing_report(request: Request, report_id: str):
        try:
            payload = meter()
        except Exception:
            payload = {"mode": settings.mode, "plan_searches_left": None, "hard_stop": False}
        return templates.TemplateResponse(
            request,
            "expired.html",
            {"meter": payload, "report_id": report_id},
            status_code=404,
        )

    @app.get("/report/{report_id}.md")
    def show_markdown(report_id: str):
        try:
            report = _loaded(report_id)
        except HTTPException:
            return PlainTextResponse(
                "This report expired. Please re-run the idea.\n",
                status_code=404,
            )
        filename = f"bazaar-radar-{report.keyword.replace(' ', '-')}.md"
        return PlainTextResponse(
            to_markdown(report),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/report/{report_id}", response_class=HTMLResponse)
    def show_report(report_id: str, request: Request):
        try:
            report = _loaded(report_id)
        except HTTPException:
            return _missing_report(request, report_id)
        return render(request, "index.html", report=report, prefill=None)

    @app.get("/credits")
    def credits(request: Request):
        payload = meter()
        if "application/json" in request.headers.get("accept", ""):
            return payload
        try:
            return templates.TemplateResponse(request, "_credits.html", {"meter": payload})
        except Exception as exc:
            note("page:failed", exc, settings.startup_fallbacks)
            return JSONResponse(payload)

    return app


def _prefill(raw, report: Report | None) -> dict:
    if raw is None and report is not None:
        raw = report
    if raw is None:
        return {
            "keyword": "",
            "head_term": "",
            "variants": "",
            "target_price": "",
            "states": [],
            "category": "Home & Décor",
        }
    variants = getattr(raw, "variants", [])
    states = getattr(raw, "states", None)
    if states is None:
        states = getattr(raw, "states_served", [])
    price = getattr(raw, "target_price", "")
    return {
        "keyword": raw.keyword,
        "head_term": raw.head_term,
        "variants": ", ".join(variants),
        "target_price": _whole_price(price),
        "states": list(states),
        "category": raw.category,
    }


def _whole_price(price) -> str | int | float:
    if price == "" or price is None:
        return ""
    number = float(price)
    if number == int(number):
        return int(number)
    return number


def _charts(report: Report) -> dict:
    demand = report.demand
    bands = report.competition.bands
    return {
        "yoy": {
            "labels": demand.yoy_labels,
            "last": demand.yoy_last,
            "this": demand.yoy_this,
            "lastYear": demand.yoy_last_year,
            "thisYear": demand.yoy_this_year,
        },
        "five": {
            "labels": demand.five_labels,
            "values": demand.five_values,
            "markers": demand.markers,
            "term": demand.five_term,
        },
        "states": {
            "labels": [row.location for row in demand.states[:12]],
            "values": [row.value for row in demand.states[:12]],
            "served": [row.served for row in demand.states[:12]],
        },
        "bands": {
            "labels": [band.label for band in bands],
            "counts": [band.count for band in bands],
            "whitespace": [band.whitespace for band in bands],
            "target": [band.contains_target for band in bands],
        },
    }


def _emergency_app() -> FastAPI:
    emergency = FastAPI(title="Bazaar Radar")

    @emergency.get("/healthz")
    def healthz():
        return {"ok": True, "mode": "fixtures", "fallbacks": public_fallbacks(["app:emergency"])}

    @emergency.api_route("/{path:path}", methods=["GET", "POST", "HEAD"])
    def anything(path: str):
        return JSONResponse(
            {"ok": True, "mode": "fixtures", "fallbacks": public_fallbacks(["app:emergency"])}
        )

    return emergency


try:
    app = create_app()
except Exception as exc:
    note("app:emergency", exc)
    app = _emergency_app()


def run() -> None:
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
