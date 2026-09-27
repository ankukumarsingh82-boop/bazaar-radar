"""Typed models. The analysis layer never sees raw SerpApi JSON."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DailyPoint(BaseModel):
    when: str  # ISO date
    value: float
    series: str  # calendar year as text, e.g. "2026"


class WeeklyPoint(BaseModel):
    week_start: str
    label: str
    value: float
    partial: bool = False


class StateInterest(BaseModel):
    geo: str
    location: str
    value: int
    served: bool = False


class RelatedQuery(BaseModel):
    query: str
    value_label: str
    extracted_value: int = 0
    kind: str  # rising | top
    tag: str | None = None  # generic | brand | None


class Offer(BaseModel):
    origin: str  # amazon | shopping
    title: str
    price: float | None = None
    rating: float | None = None
    reviews: int = 0
    bought: int = 0
    sponsored: bool | None = None
    asin: str | None = None
    merchant: str | None = None
    badges: list[str] = Field(default_factory=list)
    product_id: str | None = None
    immersive_token: str | None = None
    choice: bool = False


class AmazonSearch(BaseModel):
    offers: list[Offer]
    related_searches: list[str] = Field(default_factory=list)
    sponsored_share: float | None = None
    sponsored_observed: bool = False
    sponsored_brand_names: list[str] = Field(default_factory=list)
    total_results: int | None = None
    bought_coverage: float = 0.0
    choice_count: int = 0


class Insight(BaseModel):
    title: str
    sentiment: str
    negative: int
    positive: int
    total: int
    summary: str = ""
    snippet: str = ""


class ProductPage(BaseModel):
    asin: str
    title: str
    brand: str | None = None
    price: float | None = None
    rating: float | None = None
    reviews: int | None = None
    bsr: str | None = None
    bsr_rank: int | None = None
    summary_text: str = ""
    insights: list[Insight] = Field(default_factory=list)


class ShoppingResult(BaseModel):
    offers: list[Offer]
    merchants: list[MerchantStat] = Field(default_factory=list)


class MerchantStat(BaseModel):
    name: str
    count: int
    median_price: float | None = None
    domain: str | None = None
    quick: bool = False


class StoreOffer(BaseModel):
    name: str
    price: float | None = None
    total: float | None = None
    tag: str | None = None
    link: str | None = None
    pack_outlier: bool = False
    foreign: bool = False


class ImmersiveProduct(BaseModel):
    title: str = ""
    brand: str | None = None
    price_range: str | None = None
    stores: list[StoreOffer] = Field(default_factory=list)


class AdSignal(BaseModel):
    domain: str
    advertiser: str
    total_results: int
    formats: dict[str, int] = Field(default_factory=dict)
    last_shown: int | None = None
    last_shown_label: str | None = None
    recent: bool = False
    marketplace: bool = False


class Band(BaseModel):
    label: str
    low: float
    high: float
    count: int
    amazon_count: int
    shopping_count: int
    listing_share: float
    median_rating: float | None = None
    total_reviews: int = 0
    bought_sum: int = 0
    demand_share: float = 0.0
    high_rating_count: int = 0
    whitespace: bool = False
    quality_gap: bool = False
    contains_target: bool = False


class YearPeak(BaseModel):
    year: int
    week_label: str
    value: float
    days_before: int


class Evidence(BaseModel):
    engine: str
    purpose: str
    params: dict[str, str]
    search_id: str | None = None
    source: str
    json_endpoint: str | None = None
    note: str | None = None


class Usage(BaseModel):
    fixture: int = 0
    cache: int = 0
    live: int = 0
    missing: int = 0
    blocked: int = 0

    @property
    def served(self) -> int:
        return self.fixture + self.cache + self.live


class DemandView(BaseModel):
    momentum: float | None = None
    momentum_label: str = "Unknown"
    momentum_source: str = ""
    zero_fraction: float = 1.0
    sparse: bool = True
    used_head_term: bool = False
    series_term: str = ""
    ambiguous_head: bool = False
    yoy_labels: list[str] = Field(default_factory=list)
    yoy_last: list[float] = Field(default_factory=list)
    yoy_this: list[float] = Field(default_factory=list)
    yoy_last_year: str = ""
    yoy_this_year: str = ""
    five_labels: list[str] = Field(default_factory=list)
    five_values: list[float] = Field(default_factory=list)
    five_term: str = ""
    markers: list[dict[str, str]] = Field(default_factory=list)
    days_before: int | None = None
    peak_phrase: str = ""
    projected_label: str = ""
    yearly_peaks: list[YearPeak] = Field(default_factory=list)
    states: list[StateInterest] = Field(default_factory=list)
    state_warning: str | None = None
    target_states: list[str] = Field(default_factory=list)
    keywords: list[RelatedQuery] = Field(default_factory=list)
    listing_keywords: list[str] = Field(default_factory=list)


class CompetitionView(BaseModel):
    bands: list[Band] = Field(default_factory=list)
    outliers_removed: int = 0
    priced_offers: int = 0
    bought_coverage: float = 0.0
    sponsored_share: float | None = None
    sponsored_note: str = ""
    sponsored_brands: list[str] = Field(default_factory=list)
    choice_count: int = 0
    amazon_total: int | None = None
    merchants: list[MerchantStat] = Field(default_factory=list)
    stores: list[StoreOffer] = Field(default_factory=list)
    store_title: str = ""
    store_price_range: str | None = None
    store_note: str = ""
    recommended: Band | None = None


class ComplaintView(BaseModel):
    theme: str
    sentiment: str
    negative: int
    total: int
    ratio: float
    summary: str = ""
    snippet: str = ""
    products: list[str] = Field(default_factory=list)


class WhyItem(BaseModel):
    text: str
    anchor: str


class DecisionView(BaseModel):
    verdict: str
    confidence: str
    price_low: float | None = None
    price_high: float | None = None
    price_label: str | None = None
    states: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    complaints: list[str] = Field(default_factory=list)
    why: list[WhyItem] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class Report(BaseModel):
    id: str
    created_at: str
    keyword: str
    head_term: str
    variants: list[str] = Field(default_factory=list)
    target_price: float
    states_served: list[str] = Field(default_factory=list)
    category: str
    mode: str
    demand: DemandView
    competition: CompetitionView
    complaints: list[ComplaintView] = Field(default_factory=list)
    products: list[ProductPage] = Field(default_factory=list)
    ads: list[AdSignal] = Field(default_factory=list)
    ads_pressure: str = "n/a"
    decision: DecisionView
    evidence: list[Evidence] = Field(default_factory=list)
    usage: Usage
    notes: list[str] = Field(default_factory=list)


# Resolve forward refs for ShoppingResult.merchants typed before MerchantStat assignment.
ShoppingResult.model_rebuild()
