# How Bazaar Radar uses SerpApi

SerpApi is the data layer. Every panel and every verdict rule reads normalised SerpApi fields. The client is the official `serpapi` package (`serpapi.Client(api_key=...).search({...})`). One wrapper (`app/serp_client.py`) does fixture replay, the SQLite cache, the credit ledger, and the hard stop.

Live parameters below are what the app sends. Field paths are the ones observed on 27 Sep 2026, written up in [day1-findings.md](day1-findings.md). Where the original plan and those recordings disagree, the recordings win.

## Engines

### Google Trends — demand

Docs: https://serpapi.com/google-trends-api

Four call shapes. The Shopping property (`gprop=froogle`) was recorded and then dropped: for these Indian festive terms the series is almost all zeros, so it cannot support a “shopping intent” panel. Its budget slot is the 5-year call.

1. **Year on year.** `engine=google_trends`, `data_type=TIMESERIES`, `geo=IN`, `tz=-330`, `q="<term>,<term>"`, `date="<last year window>,<this year window>"` (1 Aug through today, both years). Multi-date responses put `date`, `timestamp`, and `extracted_value` on each entry of `values[]`, not on the timeline point. The app averages days into weeks before momentum.
2. **Head term retry.** Same call with a shorter term (brass diya → diya) when more than 40% of either year is zero.
3. **States.** `data_type=GEO_MAP_0`, `region=REGION`, `geo=IN`. Read `interest_by_region[].geo`, `location`, `extracted_value`. Only non-zero states come back; a missing state is treated as 0.
4. **Related queries.** `data_type=RELATED_QUERIES`, `date=today 3-m`, with `today 12-m` if fewer than five queries come back. Read `related_queries.rising[]` and `.top[]` (`query`, `value`, `extracted_value`). Generic breakouts (“diwali 2026”) are filtered. A query that is only a competitor brand is tagged and kept off the five listing keywords.
5. **Five-year weekly.** `data_type=TIMESERIES`, `date=today 5-y`, a single head term so a loud term does not flatten a quiet one. Days-to-peak is the start of the peak week inside a window from 21 days before Diwali to 7 days after, for 2023, 2024, and 2025. Diwali dates used: 12 Nov 2023, 1 Nov 2024, 20 Oct 2025, 8 Nov 2026.

### Amazon Search — amazon.in competition

Docs: https://serpapi.com/amazon-search-api

`engine=amazon`, `k=<keyword>`, `amazon_domain=amazon.in`.

Read `organic_results[]`: `asin`, `title`, `extracted_price`, `rating`, `reviews`, `bought_last_month`, `badges`, and `sponsored` **only when the key is present**. On day 1 the key was missing entirely for brass diya and the gift hamper, and present on 12 of 60 rangoli rows. A missing key is shown as n/a, not as 0%. `sponsored_brands.brands[].name` is a second ad signal. `related_searches[].query` fills keywords when Trends is thin.

`bought_last_month` strings such as `"1K+ bought in past month"` map to 1000. Coverage is shown because it was only 35% on two of the three queries.

Price stats use non-sponsored rows. Sponsored rows still count toward the sponsored share.

### Amazon Product — buyer pain

Docs: https://serpapi.com/amazon-product-api

`engine=amazon_product`, `asin=<top non-sponsored ASIN by review count>`, `amazon_domain=amazon.in`. Up to three ASINs in live mode.

Insights are at `reviews_information.summary.insights[]`, not `reviews_information.insights`. Each insight has `title`, `sentiment` (`positive` | `mixed` | `negative`), `mentions.total`, `mentions.positive`, `mentions.negative`, `summary`, and `examples[].snippet`.

`mentions.positive + mentions.negative` does not equal `mentions.total`. The rank uses `negative`, and includes a theme when sentiment is negative or mixed, or when negative/total > 0.3.

`product_details.best_sellers_rank[]` is optional. The gift-box ASIN had none. The UI shows the more specific rank (the last entry: “#319 in Home & Décor” on the Borosil diya).

### Google Shopping — other channels

Docs: https://serpapi.com/google-shopping-api

`engine=google_shopping`, `q=<keyword>`, `gl=in`, `hl=en`, `google_domain=google.co.in`, `location=India`.

The app merges `shopping_results` and `categorized_shopping_results[].shopping_results`, dedupes by `product_id`, and normalises `source` (`Amazon.in` and `amazon.in` collapse). A missing `source` becomes “Unknown store”. `extracted_price` feeds the bands after an IQR trim (the brass-diya pull contained a ₹78,750 outlier). `rating` is ignored: it was present on a handful of rows at most.

`immersive_product_page_token` is passed to the next engine. A Mumbai location was tried on day 1 and is not a separate MVP call.

### Google Immersive Product — store list for one product

Docs: https://serpapi.com/google-immersive-product-api

`engine=google_immersive_product`, `page_token=<token>`, `more_stores=true`.

Read `product_results.price_range` and `stores[]` (`name`, `extracted_price`, `extracted_total`, `tag`, `link`). There is no ratings histogram and no `user_reviews` in the India responses we recorded. Stores whose host or seller name is foreign (`.ae`, Desertcart, Desertcart.in, and similar) are dropped. The same filter removes those sellers from the Shopping channel list. Prices far from the median are flagged as a different pack size and left out of the short list. The price range is labelled as mixed pack sizes.

### Google Ads Transparency Center — who is buying ads

Docs: https://serpapi.com/google-ads-transparency-center-api

Promoted into the MVP after both day-1 domains returned recent India creatives, because Amazon’s `sponsored` flag is often missing.

`engine=google_ads_transparency_center`, `text=<domain>`, `region=2356`, `start_date` / `end_date` as `YYYYMMDD` for the last 30 days, `num=40`.

Read `search_information.total_results` and `ad_creatives[]` (`advertiser`, `format`, `target_domain`, `first_shown`, `last_shown`). Timestamps are Unix seconds. The UI shows `target_domain`, because the advertiser string can be a parent company (Jaypore came back as “Xplanck Marketing Private Limited”).

Pressure is **high** at ≥ 500 creatives (fnp.com returned 2,000) or when Amazon sponsored share is over 50%. That forces CAUTION. Forty or more creatives, or a sponsored share of at least 15%, is **medium** and is shown but does not by itself flip the verdict.

The Immersive Product call runs before Ads Transparency. Domains come from `stores[].link` hostnames, folded to the registrable domain (`www.shoppersstop.com` and `m.shoppersstop.com` are shoppersstop.com; `dl.flipkart.com` is flipkart.com). Marketplaces, foreign shops, and large general retailers are not niche advertisers. The general-retailer list is Shoppers Stop, Tata CLiQ, IKEA, Home Centre, Nykaa Fashion, Reliance Digital, Lifestyle, Pepperfry, and Croma (Ajio and Nykaa are already marketplaces). Those hosts can still be shown, labelled context only, and their creative counts do not raise ad pressure. If filtering them leaves no niche host, the curated merchant map is the fallback. When exactly one niche store host is usable, the second slot is the next domain on that map. At most two domains are queried. Google Shopping India rows have no merchant `link`, so they are not a domain source.

Fixture mode keeps the map when none of the store hosts has a recorded Ads response. Brass diya and rangoli colours have Immersive recordings, and the only usable seller host on those lists is craftvatika.com, which has no Ads fixture. Brass diya therefore uses the map: jaypore.com is recorded, and fabindia.com is the second call, which has no Ads fixture. Rangoli colours queries flipkart.com and myntra.com, and neither Ads response is recorded. The diwali gift hamper has no Immersive recording, so it uses the curated map: fnp.com is recorded, and igp.com is the second call, which has no Ads fixture. The hamper does not use the map because of craftvatika.com.

### Account API — credit meter

Docs: https://serpapi.com/account-api

`GET https://serpapi.com/account.json`. Not counted toward the plan. The app reads `plan_searches_left` and `this_month_usage`. Live calls stop when fewer than 20 searches remain.

## What one report costs

| Call | When |
|---|---|
| Trends YoY | Always |
| Trends YoY, head term | Only if the phrase is > 40% zeros |
| Trends states | Always |
| Trends related, 3 months | Always |
| Trends related, 12 months | Only if the 3-month list has fewer than 5 queries |
| Trends 5-year | Always, on the head term |
| Amazon search | Always |
| Amazon product | Up to 3 ASINs |
| Google Shopping | Always |
| Ads Transparency | Up to 2 domains |
| Immersive Product | 1 token |
| **Cap** | **14 live searches per report** |

Repeat runs in `BR_MODE=cache` are local SQLite hits and do not call SerpApi. `BR_MODE=fixtures` never calls SerpApi.

## Evidence

Each report keeps the engine, the parameters (never the API key), the `search_metadata.id`, and whether the row was a fixture, a cache hit, a live call, missing, or blocked. The decision card’s “why” lines link to the panel that used that data.
