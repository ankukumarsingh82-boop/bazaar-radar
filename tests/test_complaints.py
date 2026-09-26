from app.analysis.complaints import complaint_themes
from app.models import Insight, ProductPage


def _page(asin, insights):
    return ProductPage(asin=asin, title=f"Product {asin}", insights=insights)


def test_positive_theme_with_unbalanced_counts_is_not_a_complaint():
    # positive + negative != total, and the theme is still positive.
    page = _page(
        "B00",
        [
            Insight(title="Quality", sentiment="positive", negative=102, positive=1393, total=1400),
            Insight(
                title="Size",
                sentiment="mixed",
                negative=59,
                positive=40,
                total=121,
                summary="Runs small",
            ),
            Insight(title="Bottle size", sentiment="negative", negative=23, positive=2, total=27),
        ],
    )
    themes = complaint_themes([page])
    names = [row.theme for row in themes]
    assert "Quality" not in names
    assert names[0] == "Size"
    assert names[1] == "Bottle size"


def test_positive_theme_is_kept_when_negative_share_exceeds_30_percent():
    page = _page(
        "B01",
        [Insight(title="Value", sentiment="positive", negative=40, positive=50, total=100)],
    )
    themes = complaint_themes([page])
    assert themes[0].theme == "Value"
    assert themes[0].ratio == 0.4


def test_themes_merge_across_asins_by_negative_mentions():
    pages = [
        _page(
            "A", [Insight(title="Durability", sentiment="mixed", negative=10, positive=1, total=12)]
        ),
        _page(
            "B",
            [Insight(title="Durability", sentiment="negative", negative=30, positive=2, total=40)],
        ),
    ]
    themes = complaint_themes(pages)
    assert themes[0].negative == 40
    assert themes[0].sentiment == "negative"
    assert len(themes[0].products) == 2
