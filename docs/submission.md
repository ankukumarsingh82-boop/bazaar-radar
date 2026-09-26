# Draft text for the hackathon form

For the lead participant to review and paste. Do not submit from this file.

**Project name:** Bazaar Radar

**Track:** Commerce & Market Intelligence

**Existed before the hackathon?** No. Built 28 Sep–4 Oct 2026.

**Project description**

Bazaar Radar is a festive-season decision tool for India’s small online sellers: the 20 lakh+ sellers on Amazon.in, and many who also sell on Meesho, Flipkart, or Instagram. Before a seller puts savings into Diwali stock, they type a product idea (for example “brass diya”), a target price, and the states they ship to. Bazaar Radar combines live demand and competition data into one decision card:

- this year’s Google Trends interest vs last year, aligned to Diwali, plus a days-to-peak read from a 5-year weekly curve
- the Indian states with the most interest, and rising search phrases to use as listing keywords
- a price-band map of Amazon.in and Google Shopping India that shows where demand exists but strong listings do not
- the top buyer complaints about current listings, from Amazon review insights
- ad pressure from Amazon’s sponsored flag (when the field exists) and from the Google Ads Transparency Center for India

The output is a verdict (GO / GO with positioning / CAUTION / SKIP), a price band, target states, keywords, and complaints to fix, with every claim linked to its SerpApi evidence. Unlike price trackers, which help buyers find the cheapest offer, Bazaar Radar helps sellers find the gap. It runs locally (FastAPI), caches every search, and ships a fixture mode so anyone can run the three recorded ideas without an API key.

**How the project uses SerpApi**

SerpApi is the entire data layer. Every panel and every verdict rule is computed from SerpApi results:

- **Google Trends API** (`geo=IN`): a multi-date TIMESERIES for a Diwali-aligned year-on-year curve and a weekly momentum score; a `today 5-y` TIMESERIES for days-to-peak; `GEO_MAP_0` with `region=REGION` for state demand; `RELATED_QUERIES` for listing keywords. A Shopping-property (`gprop=froogle`) check was too sparse for these terms and is not in the product.
- **Amazon Search API** (`amazon_domain=amazon.in`): prices, ratings, review counts, “bought in past month”, and the sponsored flag when Amazon returns it.
- **Amazon Product API** (amazon.in): review insights at `reviews_information.summary.insights` (theme, sentiment, mention counts) for the complaints list.
- **Google Shopping API** (`gl=in`, google.co.in): cross-merchant offers (Flipkart, Meesho, JioMart, quick commerce, D2C) that Amazon’s own tools do not show.
- **Google Immersive Product API** (`more_stores=true`): store-level prices for one competing product, with foreign shops filtered out.
- **Google Ads Transparency Center API** (region 2356, India): how many creatives a competitor domain has had live.
- **Account API**: the in-app credit meter. Live calls stop below 20 searches left.

A typical fresh report is 9–14 searches. Responses are cached in SQLite. Fixture mode replays 23 recorded responses and costs nothing. Each report lists the searches it used and their SerpApi ids.

**AI tools used**

The project was built with Cursor’s coding agent (Grok 4.7), which drafted the implementation, tests, and documentation from an approved plan and from recorded SerpApi responses. I reviewed, ran, and tested the code and I am responsible for it. At runtime no LLM is used. The verdict is deterministic, unit-tested Python.

**Community source:** (fill in: SerpApi blog / BangPypers / HydPy / TriPy / AI Geeks Chennai)

**Lead participant:** name, email, mobile, occupation, years of experience (do not store these in the repo).
