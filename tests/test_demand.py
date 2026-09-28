from datetime import date

from app.analysis.demand import (
    days_to_peak,
    is_generic,
    is_question,
    is_retailer_query,
    label_momentum,
    listing_keywords,
    momentum_from_yoy,
    momentum_ratio,
    recommend_states,
    tag_queries,
    to_weeks,
    zero_fraction,
)
from app.models import DailyPoint, RelatedQuery, StateInterest


def _days(year, start_month, start_day, values):
    points = []
    day = date(year, start_month, start_day)
    for value in values:
        points.append(DailyPoint(when=day.isoformat(), value=value, series=str(year)))
        day = date.fromordinal(day.toordinal() + 1)
    return points


def test_momentum_labels_and_ratio():
    assert label_momentum(1.79) == "Rising"
    assert label_momentum(1.0) == "Flat"
    assert label_momentum(0.79) == "Falling"
    assert label_momentum(None) == "Unknown"
    assert momentum_ratio([10, 10], [5, 5]) == 2
    assert momentum_ratio([4], [0]) is None


def test_weekly_means_before_momentum():
    # Four weeks this year at 20, four weeks last year at 10. Daily noise should average out.
    last = []
    this = []
    for week in range(4):
        for _ in range(7):
            last.append(10 if week < 3 else 10)
            this.append(20)
    points = _days(2025, 8, 4, last) + _days(2026, 8, 3, this)
    weeks = to_weeks(points)
    ratio, last_year, this_year = momentum_from_yoy(weeks)
    assert last_year == "2025"
    assert this_year == "2026"
    assert ratio == 2


def test_zero_fraction_uses_the_thinner_year():
    points = _days(2025, 8, 1, [0, 0, 0, 1]) + _days(2026, 8, 1, [5, 5, 5, 5])
    assert zero_fraction(points) == 0.75


def test_generic_queries_and_keywords():
    assert is_generic("diwali 2026")
    assert is_generic("Diwali")
    assert not is_generic("diwali gift hampers under 500")
    queries = tag_queries(
        [
            RelatedQuery(query="diwali 2026", value_label="Breakout", kind="rising"),
            RelatedQuery(query="lotus diya", value_label="+80%", kind="rising"),
            RelatedQuery(query="Borosil", value_label="100", kind="top"),
        ],
        {"borosil"},
    )
    words = listing_keywords(
        queries, ["akhand diya"], ["brass pooja items"], "brass diya", {"borosil"}
    )
    assert "diwali 2026" not in words
    assert "Borosil" not in words
    assert words[0] == "lotus diya"


def test_listing_keywords_drop_retailers_and_questions():
    assert is_retailer_query("zepto")
    assert is_retailer_query("candles on amazon")
    assert not is_retailer_query("lotus diya")
    assert is_question("are scented candles bad for you")
    assert is_question("Which diya lasts longer?")
    assert not is_question("scented candle gift set")
    queries = tag_queries(
        [
            RelatedQuery(query="zepto", value_label="100", kind="top"),
            RelatedQuery(query="are scented candles bad for you", value_label="+40%", kind="rising"),
            RelatedQuery(query="scented candle gift set", value_label="+20%", kind="rising"),
        ],
        set(),
    )
    assert [row.tag for row in queries] == ["retailer", "question", None]
    words = listing_keywords(queries, [], ["zepto candles"], "scented candles", set())
    assert words == ["scented candle gift set"]


def test_state_warning_when_served_states_miss_the_top_10():
    states = [
        StateInterest(geo=f"IN-{index:02d}", location=f"State {index}", value=100 - index)
        for index in range(12)
    ]
    picked, warning = recommend_states(states, ["IN-RJ"])
    assert warning
    assert picked[0] == "State 0"


def test_days_to_peak_uses_week_start_against_diwali():
    # Diwali 2025 is 20 Oct. A week starting 19 Oct is 1 day before.
    points = [
        DailyPoint(when="2025-10-05", value=10, series="week"),
        DailyPoint(when="2025-10-19", value=47, series="week"),
        DailyPoint(when="2025-10-26", value=8, series="week"),
    ]
    days_before, peaks, phrase, projected = days_to_peak(points)
    assert days_before == 1
    assert "1 day before" in phrase
    assert projected.startswith("7 Nov")
    assert peaks[0].year == 2025
