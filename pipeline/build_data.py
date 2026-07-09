"""City Buy List - baseline builder (entry point).

Usage:
    python build_data.py [--server europe] [--cache-dir PATH] [--subset id1,id2] [--out PATH]

Produces app/data/baseline.json:
{
  "generated_at": "...Z", "server": "europe",
  "notes": {...data honesty notes...},
  "items": { "<market_id>": {name, cat, sub, tier, ench, artefact,
                             q: {"1": {a7, a30, vol7, bm_buy, bm_buy_ts}, ...}}, ... }
}
Items with zero Black Market history AND zero BM buy order are still listed
(meta only, no "q" key) so the app can say "no baseline" instead of guessing.
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fetch import fetch_dump, fetch_aodp_batch, batched  # noqa: E402
from compute import extract_gear_meta, compute_baseline  # noqa: E402

HISTORY_BATCH = 50
PRICES_BATCH = 100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="europe", choices=["europe", "west", "east"])
    ap.add_argument("--cache-dir", default=str(Path(__file__).parent / ".cache"))
    ap.add_argument("--subset", default="", help="comma-separated market ids (testing)")
    ap.add_argument("--out", default=str(Path(__file__).parent.parent / "app" / "data" / "baseline.json"))
    args = ap.parse_args()

    cache = Path(args.cache_dir)
    t0 = time.monotonic()

    print("[1/4] dumps (ao-bin-dumps, cache 24h)...")
    meta = extract_gear_meta(
        fetch_dump(cache, "items.json"),
        fetch_dump(cache, "formatted/items.txt"),
    )
    print(f"      {len(meta)} market ids (T4+ gear, enchants included)")

    ids = sorted(meta)
    if args.subset:
        wanted = {s.strip() for s in args.subset.split(",") if s.strip()}
        ids = [i for i in ids if i in wanted]
        print(f"      subset: {len(ids)} ids")

    print(f"[2/4] AODP history, Black Market, 30d daily ({len(ids)} ids, batches of {HISTORY_BATCH})...")
    history = []
    for n, chunk in enumerate(batched(ids, HISTORY_BATCH), 1):
        history.extend(fetch_aodp_batch(
            cache, args.server, "history", chunk,
            {"locations": "Black Market", "time-scale": 24},
        ))
        if n % 20 == 0:
            print(f"      batch {n}, {len(history)} rows")

    print(f"[3/4] AODP prices, Black Market ({len(ids)} ids, batches of {PRICES_BATCH})...")
    prices = []
    for chunk in batched(ids, PRICES_BATCH):
        prices.extend(fetch_aodp_batch(
            cache, args.server, "prices", chunk,
            {"locations": "Black Market"},
        ))

    print("[4/4] compute + write...")
    baseline = compute_baseline(history, prices)

    items = {}
    for item_id in ids:
        entry = dict(meta[item_id])
        if item_id in baseline:
            entry["q"] = baseline[item_id]
        items[item_id] = entry

    with_data = sum(1 for v in items.values() if "q" in v)
    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "server": args.server,
        "notes": {
            "scope": "T4-T8 gear (weapons, armors, head, shoes, offhands, bags, capes)",
            "a7_a30": "volume-weighted mean of AODP Black Market daily history",
            "vol7": "mean items/day at Black Market over last 7 days (item_count)",
            "bm_buy": "AODP buy_price_max at Black Market at build time; check bm_buy_ts for staleness",
            "missing": "items without 'q' have no reliable Black Market baseline; the app must show 'no baseline', never a guess",
        },
        "items": items,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8", newline="\n")
    kb = out_path.stat().st_size / 1024
    print(f"done in {time.monotonic()-t0:.0f}s -> {out_path} ({kb:.0f} KB, {with_data}/{len(items)} items with baseline)")


if __name__ == "__main__":
    main()
