"""City Buy List - fetch layer.

Downloads (with file cache):
- ao-bin-dumps items.json + items.txt (metadata, cache 24h)
- AODP history + prices for the Black Market (baseline, cache 1h)

Stdlib only. Never invents data: a failed batch is retried, then recorded
as missing; missing items simply have no baseline entry.

AODP is a free community service (albion-online-data.com). Documented rate
limits: 180 req/min. We pace well under that. The player's own client
uploads keep feeding it; this script only READS the public API.
"""

import json
import os
import time
import urllib.error
import urllib.request
import urllib.parse
from pathlib import Path

DUMPS_BASE = "https://raw.githubusercontent.com/ao-data/ao-bin-dumps/master/"
AODP_SERVERS = {
    "europe": "https://europe.albion-online-data.com",
    "west": "https://west.albion-online-data.com",
    "east": "https://east.albion-online-data.com",
}

DUMP_TTL = 24 * 3600   # dumps move slowly
AODP_TTL = 3600        # per spec: 1h local cache
# Observed 09/07: bursts of history batches at 0.45s pacing still drew HTTP 429,
# so the effective limit is stricter than the documented 180/min. Default slower,
# overridable for tuning (e.g. CBL_PACE=2 in GitHub Actions).
PACE_SECONDS = float(os.environ.get("CBL_PACE", "1.2"))
UA = "CityBuyList-pipeline/0.1 (read-only baseline builder)"

_last_request_at = 0.0


def _http_get(url: str, timeout: int = 60) -> bytes:
    global _last_request_at
    wait = PACE_SECONDS - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
    finally:
        _last_request_at = time.monotonic()
    return data


def _cached(cache_dir: Path, key: str, ttl: int, fetch) -> bytes:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / key
    if path.exists() and (time.time() - path.stat().st_mtime) < ttl:
        return path.read_bytes()
    data = fetch()
    if data is None:            # fetch failed: do NOT cache, so a re-run retries
        return b"[]"
    path.write_bytes(data)
    return data


def fetch_dump(cache_dir: Path, name: str) -> bytes:
    """name: e.g. 'items.json' or 'formatted/items.txt'"""
    key = "dump_" + name.replace("/", "_")
    return _cached(cache_dir, key, DUMP_TTL, lambda: _http_get(DUMPS_BASE + name, timeout=300))


def fetch_aodp_batch(cache_dir: Path, server: str, endpoint: str, item_ids: list,
                     params: dict, retries: int = 3) -> list:
    """endpoint: 'history' or 'prices'. Returns parsed JSON list, [] if all retries fail."""
    base = AODP_SERVERS[server]
    ids = ",".join(item_ids)
    qs = urllib.parse.urlencode(params)
    url = f"{base}/api/v2/stats/{endpoint}/{urllib.parse.quote(ids)}?{qs}"
    key = "aodp_%s_%s_%08x" % (server, endpoint, hash((ids, qs)) & 0xFFFFFFFF)

    def _fetch():
        last_err = None
        for attempt in range(retries):
            try:
                return _http_get(url)
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code == 429:
                    # rate limited: honor Retry-After if present, else back off hard
                    retry_after = e.headers.get("Retry-After")
                    wait = int(retry_after) if retry_after and retry_after.isdigit() else 15 * (attempt + 1)
                    time.sleep(wait)
                else:
                    time.sleep(2 * (attempt + 1))
            except Exception as e:  # noqa: BLE001 - transient network error, retry
                last_err = e
                time.sleep(2 * (attempt + 1))
        print(f"  MISS after {retries} tries ({last_err}): {item_ids[0]}..{item_ids[-1]}")
        return None

    try:
        return json.loads(_cached(cache_dir, key, AODP_TTL, _fetch))
    except json.JSONDecodeError:
        return []


def batched(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]
