# Bazaar Radar: Day-1 SerpApi checks (plan §12)

*Run on 27 Sep 2026, ~01:13–01:15 IST, from the box. Product ideas: **brass diya**, **rangoli colours**, **diwali gift hamper** (swapped in for the plan's kurta/lunch-box terms, per the user's request). Broader terms (`diya`, `rangoli`, `diwali gift`) were used for two extra Trends calls.*

**Credits:** Account API before = 250 left → after = **227 left** (`this_month_usage: 23`). **23 searches used** (budget was ~25). Account API calls were free, as documented.
Raw responses are in `fixtures/<engine>__<slug>.json`, with `api_key` removed. A scan found 0 files containing the key or an `api_key` field. There is a per-call ledger in `fixtures/_ledger.jsonl` and credit snapshots in `fixtures/account__day1-{before,after}.json`.

## Summary

| # | Check | Result | Notes |
|---|---|---|---|
| 1 | Indian stores in Google Shopping | **PASS** | 40 `shopping_results` + 20–25 categorised results per query. Prices are in ₹ scale. Merchants include Amazon.in, Flipkart, Myntra, Meesho, JioMart, Zepto/Blinkit/BigBasket and many D2C sites. Shopping ratings are almost always missing |
| 2 | Amazon.in search | **PASS (bought-in-past-month is borderline; sponsored flag is unreliable)** | 48–60 organic results per query. `bought_last_month` appeared on 75% / 35% / 35% of results. `sponsored` appeared on only 1 of 3 queries |
| 3 | Amazon.in product insights | **PASS (3/3)** | Insights are at **`reviews_information.summary.insights[]`**, not `reviews_information.insights`. Best-sellers rank was present on 2 of 3 products |
| 4 | Trends by Indian state | **PASS** | 20 / 26 / 14 states, all with non-zero values. Only non-zero states are returned |
| 5 | Trends YoY (two date ranges) | **PASS (structure); niche terms give weak data** | Two aligned daily series came back (57 points each). `brass diya` was 75% / 60% zeros; `diya` had 0 zeros |
| 6 | Trends Shopping property (`gprop=froogle`) | **Technically passes; not usable** | The series is non-empty but mostly zeros (averages 14 / 2 / 1) |
| 7 | Trends related queries | **PASS** | brass diya (3 months): 5 rising + 17 top. Gift hamper (12 months): 3 rising + 18 top |
| 8 | Ads Transparency India (stretch) | **PASS** | fnp.com: 2,000 results. jaypore.com: 46. `last_shown` falls within the last day for both |
| 9 | Immersive product India (stretch) | **PASS with caveats** | 6 and 13 stores with INR prices. The list mixes in foreign stores (Desertcart.ae) and other pack sizes. No `ratings` histogram and no `user_reviews` |
| 10 | Account API | **PASS** | `plan_searches_left`, `total_searches_left`, `this_month_usage`, `this_hour_searches`, `account_rate_limit_per_hour` |

## Check details, with observed field paths

### 1. Google Shopping (`engine=google_shopping`, gl=in, hl=en, google_domain=google.co.in, location=India): 3 calls + 1 Mumbai call
Files: `google_shopping__{brass-diya,rangoli-colours,diwali-gift-hamper,brass-diya-mumbai}.json`
- Top level: `search_metadata`, `search_parameters`, `search_information{query_displayed, shopping_results_state}`, `shopping_results[]` (always 40), `categorized_shopping_results[]{title, shopping_results[]}` (e.g. "Oil Lamps", "Candle Holders", "Under ₹600"; missing for rangoli), `filters[]{type,...}`. There was **no `inline_shopping_results`**.
- Item fields: `position, title, product_id, product_link, immersive_product_page_token, serpapi_immersive_product_api, source, source_icon, multiple_sources (bool, sometimes present), price ("₹615"), extracted_price, old_price/extracted_old_price (~10%), delivery ("Free delivery", "Free 10 min delivery"), tag, extensions, thumbnail`.
- **`rating`/`reviews` are nearly absent** (brass diya 5/65, hamper 1/60, rangoli 0/40). Rating stats have to come from Amazon.
- On rangoli, `source` and `product_link` were **missing on 4/40 items**. Normalise `source` case: `Amazon.in` and `amazon.in` both appear.
- Price range (min / median / max, ₹): brass diya 29 / 549 / 78,750 (needs outlier trimming), rangoli 50 / 179 / 2,200, hamper 199 / 1,990 / 10,000.
- Merchants seen:
  - brass diya: Amazon.in 27, Myntra 8, Zepto 6, plus Exotic India Art, Jaypore, Fabindia, Anantaya, twomoustaches…
  - rangoli: Amazon 17, Flipkart 6, Myntra 2, Meesho, JioMart, BigBasket, Blinkit, Zepto
  - hamper: dominated by small D2C gifting shops (FluorescentStudios 20, Confetti Gifts 11, thedottedi.in 7), plus IGP, fnp.com, Flipkart, Amazon
- Mumbai vs India (brass diya): 31 of 40 product_ids overlap. The mix shifts a little (Decort, Vedic Vaani appear; Zepto disappears). City location isn't worth a separate call in the MVP.

### 2. Amazon Search (`engine=amazon`, amazon_domain=amazon.in): 3 calls
Files: `amazon__{brass-diya,rangoli-colours,diwali-gift-hamper}.json`
- Top level: `search_information{total_results, query_displayed, store, page}`, `organic_results[]`, `related_searches[]{query}`, `categories[]`, `filters{price, brands, customer_reviews, discount, seller, …}` (a dict, not a list), `serpapi_pagination{current,next}`. Rangoli also returned `featured_products[]`, `video_results[]` and **`sponsored_brands{title, brands[]}`**.
- Item fields: `position, asin, title, link, link_clean, serpapi_link, thumbnail, rating, reviews, bought_last_month, price, extracted_price, old_price, extracted_old_price, offers[], delivery[], purchase_options[], badges[] ("Limited time deal", "Amazon's Choice for \"brass diya\""), save_with_coupon, sponsored, options, more_buying_choices`. There is no `prime` field.
- Counts: 48 / 60 / 48 organic results. INR prices on 98–100% of items. Rating/reviews on 100% / 93% / 83%.
- **`bought_last_month`** is a string such as `"600+ bought in past month"` or `"1K+ bought in past month"`. Coverage was brass diya 75%, rangoli 35%, hamper 35%, so the ≥30% bar passes, but barely for two terms.
- **`sponsored: true` is only present when true; the key is otherwise absent.** It appeared on 12/60 rangoli results and **0/48 for both brass diya and hamper**. Either Amazon served no sponsored results to SerpApi for those queries, or they aren't parsed. A 0% ad-pressure reading can't be trusted.

### 3. Amazon Product (`engine=amazon_product`, amazon_domain=amazon.in): 3 calls
ASINs (top non-sponsored result by reviews): B00EZMNH9A (Borosil Akhand Diya), B08KF3QKZ6 (Open Secret cookie gift box), B08M3PBSHG (CraftVatika rangoli kit).
- `product_results{asin, title, brand, rating, reviews, bought_last_month, extracted_price, extracted_old_price, discount, badges, variants, categories, stock, …}`
- **Insights path:** `reviews_information.summary.text` and **`reviews_information.summary.insights[]{title, sentiment ∈ positive|mixed|negative, mentions{total, positive, negative}, summary, examples[]{snippet, link}}`**. There were 8 insights on each of the 3 products.
- **`mentions` counts don't add up** (e.g. Quality: total 1400, positive 1393, negative 102). Use `negative` and `negative/total` directly; don't assume positive + negative = total.
- Example complaints we could show:
  - rangoli kit: Functionality (nozzles), 19 negative; Bottle size 23; Flow 15; Texture 13; Quality (mixed) 109
  - gift box: Value for money 59; Size 17
  - diya: Size 59; Heat resistance 43; Durability 36
- `reviews_information.authors_reviews[]{title, text, rating, date, verified_purchase, helpful_votes}` has 8 items. The diya also has `other_countries_reviews`.
- **BSR:** `product_details.best_sellers_rank[]{text, extracted_rank, link, link_text}`. Present for the diya (#319 Home & Décor) and rangoli (#29 Home Decorative Accessories). **Missing for the grocery-type gift box**, where `product_details` only had rating/reviews.

### 4. Trends GEO_MAP_0 (region=REGION, geo=IN, default date today 12-m): 3 calls
- `interest_by_region[]{geo ("IN-KA"), location, max_value_index, value, extracted_value}`. Only non-zero states are returned, so a missing state means 0.
- States returned: brass diya 20 (KA 100, TG 82, MH 69, DL 60), rangoli 26 (PY 100, AP 83, TG 67, TN 65), gift hamper 14 (DL 100, MH/UT/HR 66). `include_low_search_volume` wasn't needed.

### 5. Trends YoY multi-date TIMESERIES: 2 calls
- `interest_over_time.timeline_data[]` has **a different shape in multi-date mode**. Each point has only `values[]`, and **`date` / `timestamp` / `partial_data` sit on each value**: `values[i]{query, query_index, date, timestamp, value, extracted_value}`. `interest_over_time.averages[]{query, value}`.
- Granularity is daily, with 57 points for the 1 Aug–26 Sep windows. The two series share one scale, so they can be compared directly.
- `brass diya,brass diya`: 43/57 zeros last year and 34/57 this year. Momentum from the last 28 days = 1.49, but that's noise-driven.
- `diya,diya`: 0 zeros. Last-28-day means were 44.3 (2025) vs 79.4 (2026), a ratio of 1.79. **Caveat:** "diya" is also a common given name. The 5-year weekly series also shows a step-up (7–8 → 11–13), which could be non-commercial.

### 6. Trends `gprop=froogle` TIMESERIES (3 terms, today 12-m): 1 call
- Standard shape: `timeline_data[]{date ("Sep 21 – 27, 2025" with thin-space U+2009), timestamp, partial_data?, values[]{query, query_index, value, extracted_value}}`.
- Averages were brass diya 14, rangoli colours 2, hamper 1. Most weeks are 0. It's too sparse to support a "shopping intent" panel.

### 7. Trends RELATED_QUERIES: 2 calls
- `related_queries.rising[] / .top[]` with fields `{query, value ("Breakout", "+250%", "100"), extracted_value, link, serpapi_link}`.
- brass diya (today 3-m): rising = borosil akhand diya (Breakout), agarbatti stand, candle, metal diya, lotus diya. Top = akhand diya, brass diya lamp, brass diya set, brass diya for pooja, hanging diya…
- gift hamper (today 12-m): rising = "diwali 2026" (Breakout, which should be filtered out), "…for corporate" +200%, "…under 500" +90%. Top has 18 items.

### Extra: 5-year weekly TIMESERIES (`diya,rangoli,diwali gift`): 1 call (fallback for days-to-peak)
- 261 weekly points (Sep 2021 → Sep 2026).
- `rangoli` peaks in Diwali week every year: 12–18 Nov 2023, 27 Oct–2 Nov 2024, 19–25 Oct 2025 (value 47). That's a clean days-to-peak signal of about 0–7 days before Diwali.
- `diwali gift` was 0 on 247/261 weeks. Dominant terms flatten weaker terms in multi-term comparisons, so don't batch terms with very different volumes.

### 8. Ads Transparency (`region=2356`, start/end 20260827–20260926, num=40): 2 calls
- `search_information.total_results`, `ad_creatives[]{advertiser_id, advertiser, ad_creative_id, format (text|image|video), target_domain, image, width, height, total_days_shown, first_shown, last_shown, details_link, serpapi_details_link, link}`, `serpapi_pagination`.
- **`first_shown`/`last_shown` are Unix epoch seconds.**
- fnp.com: FNP E Retail Pvt Ltd, 2,000 results. jaypore.com: advertiser shows as "Xplanck Marketing Private Limited", which is the parent/agency name and not the brand. The UI should display `target_domain`.

### 9. Immersive Product (`more_stores=true`): 2 calls
- `product_results{title, brand, price_range ("₹584-₹615"), stores[]{name, title, link, tag ("Best price"), details_and_offers, price, extracted_price, shipping, total, extracted_total, rating?, reviews?}, stores_next_page_token, about_the_product, more_options, thumbnails}`.
- **No `ratings` histogram and no `user_reviews`** for either product.
- The rangoli product returned 13 stores whose prices ran ₹293–₹5,270, because different pack sizes are merged. Desertcart.ae (not an Indian store) appeared for the diya. Filter store names and treat `price_range` with care.

## Surprises
1. Amazon `sponsored` shows up on only 1 of 3 queries, so ad-pressure can read 0% even on crowded festive terms.
2. Amazon insights are nested under `summary`, and the mention counts don't sum to the total.
3. Google Shopping India carries almost no ratings. It does surface quick-commerce stores (Zepto 10-minute delivery, Blinkit, BigBasket), which make a nice "channel spread" story.
4. Multi-date Trends moves `date`/`timestamp` into `values[]` and returns daily points.
5. Two-word niche terms ("brass diya") are sparse in daily Trends data. Broad terms are dense but can be ambiguous ("diya" is also a name).
6. Trends Shopping property (`froogle`) is nearly empty for Indian festive terms.
7. Gift hampers are a grocery-type category: no BSR, and lower `bought_last_month` coverage.

## Plan adjustments (recommended)
1. **Momentum / YoY:** keep multi-date TIMESERIES, but aggregate the daily points to **weekly means** before computing momentum. If more than 40% of points are zero, retry with a broader "head term" automatically, or drop confidence. Add a "head term" input in the UI (e.g. "brass diya" → "diya"). The normaliser has to read `values[i].timestamp` in multi-date mode.
2. **Days-to-peak:** the Aug–Sep YoY window can't show last year's peak. Add one `today 5-y` weekly call per report (use a single term, or terms of similar volume) and slice the Diwali 2023/24/25 windows. This replaces the froogle call, so the per-report call count stays the same.
3. **Drop the `gprop=froogle` "shopping intent" sub-panel** (the plan's fallback for check 6). Its call slot goes to the 5-year call.
4. **Ad pressure:** show the Amazon sponsored share only when at least one `sponsored` key exists, and add `sponsored_brands` as a signal. Otherwise show "n/a". Treat Ads Transparency (S1) as the stronger ad signal and consider promoting it to MVP, since both test domains returned many recent creatives.
5. **Demand proxy:** keep `bought_last_month` but combine it with `reviews` and badges ("Amazon's Choice"). Map strings: `"1K+"` → 1000, `"50+"` → 50, missing → 0. Show coverage % in the UI.
6. **Complaints:** use `reviews_information.summary.insights`. Rank by `mentions.negative` for `sentiment ∈ {negative, mixed}`, or where negative/total > 0.3. BSR is optional (missing for grocery categories).
7. **Shopping normaliser:** merge `shopping_results` + `categorized_shopping_results` and dedupe by `product_id`. Lower-case and strip `source`, and tolerate a missing `source`. Trim prices with IQR (the diya run had a ₹78,750 outlier). Don't use Shopping ratings. Drop the Mumbai/location variant from MVP.
8. **Related queries:** filter out generic breakouts ("diwali 2026", "diwali") and competitor brand names, or tag them. Use `today 3-m` for rising and `today 12-m` as the fallback when there are fewer than 5 results.
9. **Immersive (S2):** keep it as a stretch goal, but only for store lists. Filter out non-`.in`/foreign stores. Drop the star-histogram idea.
10. **Budget:** 23 calls came in under the planned ~25. The per-report count stays at 9 (MVP) with the froogle→5-year swap. Before recording demo scenarios, spend 1 call per candidate on a YoY TIMESERIES to check density. So far only `diya` (dense) and `rangoli` (5-year weekly, dense with a clear Diwali peak) are confirmed. `brass diya` needs the head-term fallback, and `diwali gift` is sparse.
