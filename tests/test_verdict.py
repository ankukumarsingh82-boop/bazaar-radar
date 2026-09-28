import pytest

from app.analysis.verdict import VerdictFacts, ads_pressure, confidence, decide


def facts(**kwargs):
    base = dict(
        momentum=1.4,
        momentum_label="Rising",
        whitespace_near=True,
        quality_gap_near=True,
        crowded=False,
        sponsored_share=None,
        ads_pressure="low",
        sparse=False,
    )
    base.update(kwargs)
    return VerdictFacts(**base)


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, "GO"),
        ({"momentum": 1.0, "momentum_label": "Flat"}, "GO"),
        ({"momentum": 0.9, "momentum_label": "Flat"}, "GO-with-positioning"),
        (
            {"whitespace_near": False, "quality_gap_near": True, "crowded": True},
            "GO-with-positioning",
        ),
        ({"whitespace_near": False, "quality_gap_near": False, "crowded": True}, "CAUTION"),
        (
            {
                "momentum": 0.5,
                "momentum_label": "Falling",
                "whitespace_near": False,
                "quality_gap_near": False,
                "crowded": True,
            },
            "SKIP",
        ),
        (
            {
                "momentum": 0.5,
                "momentum_label": "Falling",
                "whitespace_near": True,
            },
            "CAUTION",
        ),
        ({"sponsored_share": 0.62, "ads_pressure": "high"}, "CAUTION"),
        ({"ads_pressure": "high", "sponsored_share": None}, "CAUTION"),
        ({"sponsored_share": None, "ads_pressure": "n/a"}, "GO"),
        ({"sparse": True}, "GO-with-positioning"),
        ({"momentum": None, "momentum_label": "Unknown", "sparse": True}, "GO-with-positioning"),
    ],
)
def test_verdict_matrix(overrides, expected):
    assert decide(facts(**overrides)) == expected


def test_sponsored_share_above_half_is_high_pressure():
    assert ads_pressure([], 0.51) == "high"
    assert ads_pressure([2000], None) == "high"
    assert ads_pressure([46], None) == "medium"
    assert ads_pressure([], 0.2) == "medium"
    assert ads_pressure([], None) == "n/a"


def test_confidence_drops_for_sparse_ambiguous_or_failed_sources():
    assert confidence(facts()) == "high"
    assert confidence(facts(sparse=True)) == "medium"
    assert confidence(facts(sparse=True, ambiguous_head=True, used_head_term=True)) == "low"
    assert confidence(facts(failed=["amazon"])) == "medium"


def test_confidence_drops_when_searches_are_missing_or_blocked():
    # A complete plan stays high. A third missing drops one step; two thirds drops two.
    assert confidence(facts(searches_served=14, searches_missing=0)) == "high"
    assert confidence(facts(searches_served=6, searches_missing=8)) == "medium"
    assert confidence(facts(searches_served=6, searches_blocked=8)) == "medium"
    assert confidence(facts(searches_served=2, searches_missing=12)) == "low"
    # Coverage stacks with an existing weakness.
    assert confidence(facts(sparse=True, searches_served=6, searches_missing=8)) == "low"
    # A handful of optional misses (brass diya is 3 of 13) does not move the score.
    assert confidence(facts(searches_served=10, searches_missing=3)) == "high"
