"""City Buy List - compute layer.

- extract_gear_meta: raw items.json + items.txt -> gear catalogue
  (T4+ weapons/armors/head/shoes/offhands/bags/capes, artefact flag from
  crafting recipe: a craftresource whose id contains 'ARTEFACT_' is game
  data, not a heuristic).
- compute_baseline: AODP history + prices rows -> per item, per quality:
  avg 7d, avg 30d, BM daily amount (7d mean), current BM buy_price_max.

Missing data stays missing (None / absent key). Nothing is interpolated.
"""

import json
from datetime import datetime, timedelta, timezone

GEAR_CATS = {"weapons", "magic", "armors", "head", "shoes", "offhands", "bags", "capes"}
MIN_TIER = 4  # V1 scope choice: T4-T8 (documented, not a data claim)


def extract_gear_meta(items_json_bytes: bytes, items_txt_bytes: bytes) -> dict:
    """Returns {market_id: {name, cat, sub, tier, ench, artefact}} for every
    market id (base + @1..@n enchant variants) whose base item is T4+ gear."""
    d = json.loads(items_json_bytes)["items"]
    base_gear = {}
    for grp in ("equipmentitem", "weapon"):
        for e in d.get(grp, []):
            uid = e.get("@uniquename", "")
            cat = e.get("@shopcategory", "")
            tier = int(e.get("@tier", "0") or 0)
            if cat not in GEAR_CATS or tier < MIN_TIER:
                continue
            crafting = e.get("craftingrequirements")
            artefact = "ARTEFACT_" in json.dumps(crafting) if crafting else False
            base_gear[uid] = {
                "cat": cat,
                "sub": e.get("@shopsubcategory1", ""),
                "tier": tier,
                "artefact": artefact,
            }

    meta = {}
    for line in items_txt_bytes.decode("utf-8").splitlines():
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        uid = parts[1].strip()
        name = parts[2].strip()
        root, _, ench = uid.partition("@")
        if root not in base_gear:
            continue
        m = dict(base_gear[root])
        m["name"] = name
        m["ench"] = int(ench) if ench else 0
        meta[uid] = m
    return meta


def compute_baseline(history_rows: list, price_rows: list, now=None) -> dict:
    """history_rows: AODP history entries (location=Black Market, time-scale=24).
    price_rows: AODP prices entries (location=Black Market).
    Returns {item_id: {quality(str): {a7, a30, vol7, bm_buy, bm_buy_ts}}}."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    cut7 = now - timedelta(days=7)
    cut30 = now - timedelta(days=30)

    out = {}

    def slot(item_id, quality):
        return out.setdefault(item_id, {}).setdefault(str(quality), {})

    for row in history_rows:
        days = row.get("data") or []
        pts7, pts30 = [], []
        for p in days:
            try:
                ts = datetime.fromisoformat(p["timestamp"])
            except (KeyError, ValueError):
                continue
            count = p.get("item_count") or 0
            price = p.get("avg_price") or 0
            if count <= 0 or price <= 0:
                continue
            if ts >= cut30:
                pts30.append((count, price))
                if ts >= cut7:
                    pts7.append((count, price))
        s = slot(row["item_id"], row.get("quality", 1))
        if pts7:
            n7 = sum(c for c, _ in pts7)
            s["a7"] = round(sum(c * p for c, p in pts7) / n7)  # volume-weighted
            s["vol7"] = round(n7 / 7)
        if pts30:
            n30 = sum(c for c, _ in pts30)
            s["a30"] = round(sum(c * p for c, p in pts30) / n30)

    for row in price_rows:
        buy = row.get("buy_price_max") or 0
        if buy <= 0:
            continue
        s = slot(row["item_id"], row.get("quality", 1))
        s["bm_buy"] = buy
        s["bm_buy_ts"] = row.get("buy_price_max_date")

    # prune empty slots
    for item_id in list(out):
        qs = {q: v for q, v in out[item_id].items() if v}
        if qs:
            out[item_id] = qs
        else:
            del out[item_id]
    return out
