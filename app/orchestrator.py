"""Run the SerpApi calls for one idea and assemble a decision report."""

from __future__ import annotations

import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.analysis.complaints import complaint_themes
from app.analysis.demand import (
    AMBIGUOUS_HEADS,
    align_yoy,
    days_to_peak,
    five_year_chart,
    label_momentum,
    listing_keywords,
    momentum_from_history,
    momentum_from_yoy,
    recommend_states,
    tag_queries,
    to_weeks,
    zero_fraction,
)
from app.analysis.pricebands import build_bands, near_target, recommend_band, trim_offers
from app.analysis.verdict import (
    VerdictFacts,
    ads_pressure,
    confidence,
    confidence_note,
    decide,
    limitations,
    why_items,
)
from app.config import Settings
from app.db import connect, init_db
from app.models import (
    AdSignal,
    CompetitionView,
    DecisionView,
    DemandView,
    Evidence,
    Offer,
    ProductPage,
    Report,
    Usage,
    WhyItem,
)
from app.scenarios import suggest_head
from app.serp_client import SearchHit, SerpClient
from app.sources.ads import normalize_ads
from app.sources.ads import search_params as ads_params
from app.sources.amazon import normalize_product, normalize_search, product_params
from app.sources.amazon import search_params as amazon_params
from app.sources.immersive import normalize_immersive
from app.sources.immersive import search_params as immersive_params
from app.sources.shopping import MARKETPLACE_DOMAINS, merchant_stats, normalize_shopping
from app.sources.shopping import search_params as shopping_params
from app.sources.trends import (
    five_year_params,
    geo_params,
    normalize_five_year,
    normalize_geo,
    normalize_related,
    normalize_yoy,
    related_params,
    yoy_params,
)

IST = ZoneInfo("Asia/Kolkata")


def build_report(
    *,
    keyword: str,
    target_price: float,
    states: list[str],
    category: str,
    head_term: str = "",
    variants: list[str] | None = None,
    settings: Settings,
    conn=None,
    today: date | None = None,
    report_id: str | None = None,
) -> Report:
    today = today or datetime.now(IST).date()
    keyword = " ".join(keyword.split())
    head = " ".join((head_term or suggest_head(keyword)).split())
    variants = [v.strip() for v in (variants or []) if v.strip()][:4]
    owns_conn = conn is None
    if conn is None:
        conn = connect(settings.db_path)
        init_db(conn)
    report_id = report_id or secrets.token_hex(4)
    client = SerpClient(settings, conn, report_id)
    try:
        return _assemble(
            client,
            keyword=keyword,
            head=head,
            variants=variants,
            target_price=target_price,
            states=states,
            category=category,
            today=today,
            report_id=report_id,
        )
    finally:
        if owns_conn:
            conn.close()


def _assemble(
    client: SerpClient,
    *,
    keyword: str,
    head: str,
    variants: list[str],
    target_price: float,
    states: list[str],
    category: str,
    today: date,
    report_id: str,
) -> Report:
    evidence: list[Evidence] = []
    notes: list[str] = []
    five_term = head or keyword

    def fetch(params: dict, purpose: str) -> SearchHit:
        hit = client.search(params)
        evidence.append(_evidence(hit, purpose))
        return hit

    wave = [
        (yoy_params(keyword, today), "Festive year-on-year Trends"),
        (geo_params(keyword), "Interest by Indian state"),
        (related_params(keyword, "today 3-m"), "Rising and top queries"),
        (amazon_params(keyword), "Amazon.in search"),
        (shopping_params(keyword), "Google Shopping India"),
        (five_year_params(five_term), "Five-year weekly Trends"),
    ]
    with ThreadPoolExecutor(max_workers=6) as pool:
        hits = list(pool.map(lambda item: client.search(item[0]), wave))
    for hit, (_, purpose) in zip(hits, wave):
        evidence.append(_evidence(hit, purpose))
    yoy_hit, geo_hit, rel_hit, amz_hit, shop_hit, five_hit = hits

    yoy_points = normalize_yoy(yoy_hit.data) if yoy_hit.data else []
    used_head = False
    series_term = keyword
    keyword_sparse = (not yoy_points) or zero_fraction(yoy_points) > 0.40
    if keyword_sparse and head.lower() != keyword.lower():
        head_hit = fetch(yoy_params(head, today), f"Head-term Trends for “{head}”")
        head_points = normalize_yoy(head_hit.data) if head_hit.data else []
        if head_points and (
            not yoy_points or zero_fraction(head_points) < zero_fraction(yoy_points)
        ):
            yoy_points = head_points
            used_head = True
            series_term = head
            notes.append(
                f"“{keyword}” is sparse on daily Trends "
                f"({zero_fraction(normalize_yoy(yoy_hit.data)) if yoy_hit.data else 1:.0%} zeros). "
                f"Momentum uses the head term “{head}”."
            )

    related = normalize_related(rel_hit.data) if rel_hit.data else []
    useful = [row for row in related if row.kind in {"rising", "top"}]
    if len(useful) < 5:
        wider = fetch(related_params(keyword, "today 12-m"), "Related queries, 12-month fallback")
        if wider.data:
            related = normalize_related(wider.data)
        elif not related:
            notes.append(
                "No Trends related queries in the recorded set. Keywords fall back to Amazon."
            )

    five_points: list = []
    five_name = five_term
    if five_hit.data:
        five_name, five_points = normalize_five_year(five_hit.data, five_term)
        if five_name.lower() != five_term.lower():
            notes.append(f"The 5-year curve uses “{five_name}”, the closest recorded head term.")
    elif keyword.lower() != five_term.lower():
        alt = fetch(five_year_params(keyword), "Five-year Trends fallback")
        if alt.data:
            five_name, five_points = normalize_five_year(alt.data, keyword)

    weeks = to_weeks(yoy_points)
    ratio, last_year, this_year = momentum_from_yoy(weeks)
    momentum_source = "weekly year-on-year Trends"
    yoy_zero = zero_fraction(yoy_points) if yoy_points else 1.0
    history_weeks = to_weeks(five_points).get("week", [])
    history_ratio = momentum_from_history(history_weeks)
    if yoy_points and yoy_zero <= 0.40 and ratio is not None:
        momentum = ratio
    elif history_ratio is not None and zero_fraction(five_points) <= 0.40:
        momentum = history_ratio
        momentum_source = f"5-year weekly Trends for “{five_name}”"
        series_term = five_name
        notes.append(
            "Year-on-year daily Trends was missing or sparse, so momentum comes from the 5-year weekly curve."
        )
    else:
        momentum = ratio if ratio is not None else history_ratio
        if history_ratio is not None and (ratio is None or yoy_zero > 0.40):
            momentum_source = f"5-year weekly Trends for “{five_name}”"
            series_term = five_name
    if momentum is None:
        momentum_source = "not enough dense Trends data"
    sparse = (
        zero_fraction(five_points if momentum_source.startswith("5-year") else yoy_points) > 0.40
    )
    if not yoy_points and not five_points:
        sparse = True

    labels, yoy_last, yoy_this, last_year, this_year = align_yoy(weeks)
    five_labels, five_values, markers = five_year_chart(five_points)
    days_before, yearly, peak_phrase, projected = days_to_peak(five_points)
    state_rows = normalize_geo(geo_hit.data, set(states)) if geo_hit.data else []
    target_states, state_warning = recommend_states(state_rows, states)

    amazon = normalize_search(amz_hit.data) if amz_hit.data else None
    shopping = normalize_shopping(shop_hit.data) if shop_hit.data else None
    offers: list[Offer] = []
    if amazon:
        offers.extend(offer for offer in amazon.offers if offer.sponsored is not True)
    if shopping:
        offers.extend(shopping.offers)
    trimmed, removed = trim_offers(offers)
    bands = build_bands(trimmed, target_price)

    products = _products(client, amazon, evidence, notes, fetch)
    complaints = complaint_themes(products)
    brands = {product.brand.lower() for product in products if product.brand}
    if amazon:
        brands.update(name.lower() for name in amazon.sponsored_brand_names)
    tagged = tag_queries(related, brands)
    keywords = listing_keywords(
        tagged,
        variants,
        amazon.related_searches if amazon else [],
        keyword,
        brands,
    )

    ads, ads_notes = _ads(client, shopping, today, evidence, fetch)
    notes.extend(ads_notes)
    stores, store_title, price_range, store_note = _stores(client, shopping, evidence, fetch)
    if store_note:
        notes.append(store_note)

    sponsored_share = amazon.sponsored_share if amazon else None
    pressure = ads_pressure([ad.total_results for ad in ads if not ad.marketplace], sponsored_share)
    whitespace_near = any(band.whitespace and near_target(band, target_price) for band in bands)
    quality_near = any(band.quality_gap and near_target(band, target_price) for band in bands)
    target_band = next((band for band in bands if band.contains_target), None)
    crowded = bool(target_band and target_band.count >= 4 and not whitespace_near)
    failed = []
    if not amazon:
        failed.append("amazon")
    if not shopping:
        failed.append("shopping")
    if not state_rows and not yoy_points and not five_points:
        failed.append("trends")
    counts = client.budget.counts()
    served_searches = counts["fixture"] + counts["cache"] + counts["live"]
    facts = VerdictFacts(
        momentum=momentum,
        momentum_label=label_momentum(momentum),
        whitespace_near=whitespace_near,
        quality_gap_near=quality_near,
        crowded=crowded,
        sponsored_share=sponsored_share,
        ads_pressure=pressure,
        sparse=sparse,
        used_head_term=used_head or series_term.lower() != keyword.lower(),
        ambiguous_head=series_term.lower() in AMBIGUOUS_HEADS,
        failed=failed,
        series_term=series_term,
        peak_phrase=peak_phrase,
        price_label=(target_band.label if target_band else None),
        target_states=target_states,
        state_warning=state_warning,
        searches_served=served_searches,
        searches_missing=counts["missing"],
        searches_blocked=counts["blocked"],
    )
    if served_searches == 0:
        chosen = None
        decision = DecisionView(
            verdict="insufficient",
            confidence="n/a",
            why=[
                WhyItem(
                    text="None of the planned searches returned data, so there is no verdict.",
                    anchor="evidence",
                )
            ],
            limitations=[
                "Fixture mode only replays the three recorded ideas.",
                "Without a search result, inventing a verdict would be a guess.",
            ],
        )
    else:
        verdict = decide(facts)
        chosen = recommend_band(bands, target_price, verdict)
        if chosen is not None:
            facts.price_label = chosen.label
        decision = DecisionView(
            verdict=verdict,
            confidence=confidence(facts),
            confidence_note=confidence_note(facts),
            price_low=chosen.low if chosen else None,
            price_high=chosen.high if chosen else None,
            price_label=chosen.label if chosen else None,
            states=target_states[:3],
            keywords=keywords[:5],
            complaints=[
                f"{row.theme} ({row.negative} negative mentions)" for row in complaints[:3]
            ],
            why=why_items(facts, verdict),
            limitations=limitations(facts),
        )
    if amazon and not amazon.sponsored_observed:
        sponsored_note = (
            "n/a — Amazon did not return a sponsored field on this search, so 0% would be a guess."
        )
    elif amazon and amazon.sponsored_share is not None:
        sponsored_note = f"{amazon.sponsored_share:.0%} of Amazon results are sponsored."
    else:
        sponsored_note = "Amazon search was not available."
    merchants = (
        shopping.merchants if shopping else merchant_stats(shopping.offers if shopping else [])
    )
    competition = CompetitionView(
        bands=bands,
        outliers_removed=removed,
        priced_offers=sum(1 for offer in trimmed if offer.price is not None),
        bought_coverage=amazon.bought_coverage if amazon else 0.0,
        sponsored_share=sponsored_share,
        sponsored_note=sponsored_note,
        sponsored_brands=amazon.sponsored_brand_names if amazon else [],
        choice_count=amazon.choice_count if amazon else 0,
        amazon_total=amazon.total_results if amazon else None,
        merchants=merchants[:8],
        stores=[store for store in stores if not store.pack_outlier][:8] or stores[:8],
        store_title=store_title,
        store_price_range=price_range,
        store_note=store_note,
        recommended=chosen,
    )
    demand = DemandView(
        momentum=None if momentum is None else round(momentum, 2),
        momentum_label=label_momentum(momentum),
        momentum_source=momentum_source,
        zero_fraction=round(yoy_zero if yoy_points else zero_fraction(five_points), 2),
        sparse=sparse,
        used_head_term=used_head or (bool(five_points) and five_name.lower() != keyword.lower()),
        series_term=series_term,
        ambiguous_head=series_term.lower() in AMBIGUOUS_HEADS,
        yoy_labels=labels,
        yoy_last=yoy_last,
        yoy_this=yoy_this,
        yoy_last_year=last_year,
        yoy_this_year=this_year,
        five_labels=five_labels,
        five_values=five_values,
        five_term=five_name if five_points else "",
        markers=markers,
        days_before=days_before,
        peak_phrase=peak_phrase,
        projected_label=projected,
        yearly_peaks=yearly,
        states=state_rows,
        state_warning=state_warning,
        target_states=target_states,
        keywords=[
            row
            for row in tagged
            if row.tag not in {"generic", "question", "retailer"}
        ][:12],
        listing_keywords=keywords,
    )
    return Report(
        id=report_id,
        created_at=datetime.now(IST).isoformat(timespec="seconds"),
        keyword=keyword,
        head_term=head,
        variants=variants,
        target_price=target_price,
        states_served=states,
        category=category,
        mode=client.mode,
        demand=demand,
        competition=competition,
        complaints=complaints,
        products=products,
        ads=ads,
        ads_pressure=pressure,
        decision=decision,
        evidence=evidence,
        usage=Usage(**counts),
        notes=notes,
    )


def _products(client, amazon, evidence, notes, fetch) -> list[ProductPage]:
    if amazon is None:
        return []
    ranked = [offer for offer in amazon.offers if offer.asin and offer.sponsored is not True]
    ranked.sort(key=lambda offer: offer.reviews, reverse=True)
    pages: list[ProductPage] = []
    missed = 0
    for offer in ranked[:3]:
        hit = fetch(product_params(offer.asin or ""), f"Amazon reviews for {offer.asin}")
        if hit.data:
            pages.append(normalize_product(hit.data))
        else:
            missed += 1
    if missed and client.mode == "fixtures":
        notes.append(
            f"Offline fixtures include {len(pages)} Amazon product page"
            f"{'' if len(pages) == 1 else 's'} (the review leader). Live mode fetches up to three."
        )
    return pages


def _ads(client, shopping, today, evidence, fetch) -> tuple[list[AdSignal], list[str]]:
    if shopping is None:
        return [], []
    merchants = [row for row in shopping.merchants if row.domain and row.name != "Amazon.in"]
    # Niche and D2C sellers first; a marketplace's ad volume is catalogue-wide.
    merchants.sort(key=lambda row: (row.domain or "") in MARKETPLACE_DOMAINS)
    if client.mode == "fixtures":
        recorded = [row for row in merchants if client.fixtures.has_ads(row.domain or "")]
        rest = [row for row in merchants if row not in recorded]
        merchants = recorded + rest
    chosen = []
    seen = set()
    for row in merchants:
        if row.domain in seen:
            continue
        seen.add(row.domain)
        chosen.append(row)
        if len(chosen) == 2:
            break
    ads: list[AdSignal] = []
    missing_domains = []
    for row in chosen:
        hit = fetch(ads_params(row.domain or "", today), f"Ads Transparency for {row.domain}")
        if hit.data and not hit.error:
            ads.append(_ad_signal(hit.data, row.domain or "", today))
        elif hit.source == "missing":
            missing_domains.append(row.domain)
        elif hit.data and hit.error:
            # Live error payloads still count; skip empty creative sets only when error is set
            # and there is no search_information.
            if hit.data.get("ad_creatives") or hit.data.get("search_information"):
                ads.append(_ad_signal(hit.data, row.domain or "", today))
            else:
                missing_domains.append(row.domain)
    notes = []
    if any(ad.marketplace for ad in ads):
        notes.append(
            "Marketplace ad volume (e.g. "
            + ", ".join(ad.domain for ad in ads if ad.marketplace)
            + ") is catalogue-wide, so it is shown for context and does not raise ad pressure."
        )
    if missing_domains and client.mode == "fixtures":
        notes.append(
            "Ads Transparency fixtures are not recorded for "
            + ", ".join(missing_domains)
            + ". Live mode would query those domains."
        )
    return ads, notes


def _ad_signal(payload: dict, domain: str, today) -> AdSignal:
    signal = normalize_ads(payload, domain, today)
    signal.marketplace = domain.lower() in MARKETPLACE_DOMAINS
    return signal


def _stores(client, shopping, evidence, fetch):
    if shopping is None:
        return [], "", None, ""
    with_token = [offer for offer in shopping.offers if offer.immersive_token]
    if not with_token:
        return [], "", None, ""
    picked = with_token[0]
    if client.mode == "fixtures":
        for offer in with_token:
            if client.fixtures.has_token(offer.immersive_token or ""):
                picked = offer
                break
        else:
            return [], "", None, ""
    hit = fetch(immersive_params(picked.immersive_token or ""), "Immersive Product store list")
    if not hit.data:
        return [], "", None, ""
    product = normalize_immersive(hit.data)
    note = ""
    if product.price_range:
        note = (
            f"Store list for “{product.title}”. The Google price range ({product.price_range}) "
            "can mix pack sizes, so outlier packs are set aside."
        )
    visible = [store for store in product.stores if not store.pack_outlier]
    return visible or product.stores, product.title, product.price_range, note


def _evidence(hit: SearchHit, purpose: str) -> Evidence:
    params = {key: value for key, value in hit.params.items() if key != "page_token"}
    if "page_token" in hit.params:
        params["page_token"] = hit.params["page_token"][:18] + "…"
    note = None
    if hit.source == "missing":
        note = "Not in the offline fixture set."
    elif hit.source == "blocked":
        note = hit.error
    elif hit.error and hit.source == "fixture":
        note = hit.error
    elif hit.error:
        note = hit.error
    return Evidence(
        engine=hit.params.get("engine", ""),
        purpose=purpose,
        params=params,
        search_id=hit.search_id,
        source=hit.source,
        json_endpoint=hit.json_endpoint,
        note=note,
    )
