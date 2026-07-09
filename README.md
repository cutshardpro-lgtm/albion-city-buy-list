# Albion City Buy List

Sniping tool for Albion Online: spot undervalued gear on city markets and flip it to the Black Market NPC in Caerleon (guaranteed buy, no auction risk).

**Live demo:** [cutshardpro-lgtm.github.io/albion-city-buy-list](https://cutshardpro-lgtm.github.io/albion-city-buy-list)

> Top Traded works directly online. Sniper (live feed) requires local setup — browser security blocks `ws://` from an `https://` page. See the Setup tab in the app.

---

## What it does

- **Sniper view** — real-time feed of market orders as you browse in-game. Highlights deals where the city price is below the 7-day average AND the Black Market margin is positive.
- **Top Traded** — ranked list of the 100 most-traded gear items by daily Black Market silver volume. Sortable, filterable by tier/enchant/category.
- **Setup page** — step-by-step guide to connect the live feed.

All data comes from the official [Albion Online Data Project](https://albion-online-data.com/) (AODP) public API. No accounts, no servers, no fees.

---

## Quick start (local)

**Requirements:** Python 3.8+ (stdlib only), [albiondata-client](https://github.com/ao-data/albiondata-client)

```bash
# 1. Serve the app
python -m http.server 8010 --directory app

# 2. Open in browser
http://localhost:8010/

# 3. Launch albiondata-client with WebSocket enabled (see Setup page in the app)

# 4. Browse city markets in-game — deals appear in real time
```

The baseline (7-day / 30-day averages, volumes, BM buy prices) is pre-built and included. Refresh it manually anytime:

```bash
python pipeline/build_data.py --server europe
```

---

## How the margin is calculated

```
margin = BM_buy_price * (1 - tax%) - city_price - city_price * fee%
```

- `tax` default: 4% (Black Market NPC tax — edit in the app Settings)
- `fee`: 0% by default (adjust if you use a Premium market fee)
- Both are labeled **HYPOTHESIS** in the UI — set them to your actual rates

---

## Baseline pipeline

```
pipeline/
  fetch.py       — downloads ao-bin-dumps metadata + AODP history/prices (cached)
  compute.py     — extracts T4+ gear, computes volume-weighted averages
  build_data.py  — entry point; outputs docs/data/baseline.json
```

Baseline is refreshed automatically twice daily via GitHub Actions (`.github/workflows/baseline.yml`).

---

## Contributing

Bug reports and PRs welcome. This is a personal tool shared with the Albion community — keep it simple and data-honest (no invented values, no degrading AODP uploads).

---

## License

MIT
