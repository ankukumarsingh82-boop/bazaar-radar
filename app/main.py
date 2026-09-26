"""FastAPI routes for the form, the report, the credit meter, and Markdown export."""

from __future__ import annotations

import json
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import Settings, get_settings
from app.db import connect, init_db
from app.format import inr, pct, verdict_blurb, verdict_title
from app.markdown_export import to_markdown
from app.models import Report
from app.orchestrator import build_report
from app.scenarios import SCENARIOS
from app.serp_client import SerpClient
from app.states import CATEGORIES, STATE_NAMES, STATES

TEMPLATES = Path(__file__).resolve().parent / "templates"
STATIC = Path(__file__).resolve().parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.conn = connect(settings.db_path)
        init_db(app.state.conn)
        yield
        app.state.conn.close()

    app = FastAPI(title="Bazaar Radar", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    templates = Jinja2Templates(directory=TEMPLATES)
    templates.env.filters["inr"] = inr
    templates.env.filters["pct"] = pct
    templates.env.globals["verdict_title"] = verdict_title
    templates.env.globals["verdict_blurb"] = verdict_blurb
    templates.env.globals["state_name"] = lambda code: STATE_NAMES.get(code, code)

    def meter() -> dict:
        client = SerpClient(settings, app.state.conn, "meter")
        return client.account()

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
        report = extra.get("report")
        charts = json.dumps(_charts(report)).replace("<", "\\u003c") if report else "{}"
        prefill = _prefill(extra.get("prefill"), report)
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

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        return page(request, "index.html", report=None, prefill=None)

    @app.get("/s/{slug}", response_class=HTMLResponse)
    def scenario_page(slug: str, request: Request):
        scenario = SCENARIOS.get(slug)
        if scenario is None:
            raise HTTPException(status_code=404, detail="Unknown scenario")
        report = None
        # Auto-run only offline. A GET in live mode must not spend credits.
        if settings.mode == "fixtures":
            report = build_report(
                keyword=scenario.keyword,
                head_term=scenario.head_term,
                variants=scenario.variants,
                target_price=scenario.target_price,
                states=scenario.states,
                category=scenario.category,
                settings=settings,
                conn=app.state.conn,
            )
            save(report)
        return page(request, "index.html", report=report, prefill=scenario)

    @app.post("/analyze", response_class=HTMLResponse)
    async def analyze(request: Request):
        form = await request.form()
        keyword = " ".join(str(form.get("keyword") or "").split())
        try:
            target_price = float(str(form.get("target_price") or "0"))
        except ValueError:
            target_price = 0
        if not keyword or target_price <= 0:
            return page(
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
        report = build_report(
            keyword=keyword,
            head_term=str(form.get("head_term") or ""),
            variants=variants,
            target_price=target_price,
            states=states,
            category=str(form.get("category") or "Home & Décor"),
            settings=settings,
            conn=app.state.conn,
        )
        save(report)
        if request.headers.get("HX-Request") == "true":
            return templates.TemplateResponse(
                request,
                "report_body.html",
                {
                    "report": report,
                    "charts": json.dumps(_charts(report)).replace("<", "\\u003c"),
                },
            )
        return page(request, "index.html", report=report, prefill=None)

    @app.get("/report/{report_id}.md")
    def show_markdown(report_id: str):
        report = load(report_id)
        filename = f"bazaar-radar-{report.keyword.replace(' ', '-')}.md"
        return PlainTextResponse(
            to_markdown(report),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/report/{report_id}", response_class=HTMLResponse)
    def show_report(report_id: str, request: Request):
        report = load(report_id)
        return page(request, "index.html", report=report, prefill=None)

    @app.get("/credits")
    def credits(request: Request):
        payload = meter()
        if "application/json" in request.headers.get("accept", ""):
            return payload
        return templates.TemplateResponse(request, "_credits.html", {"meter": payload})

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
        "target_price": "" if price == "" else price,
        "states": list(states),
        "category": raw.category,
    }


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


app = create_app()


def run() -> None:
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
