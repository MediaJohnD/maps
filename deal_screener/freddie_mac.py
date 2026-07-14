"""Weekly-cached fetch of Freddie Mac's Primary Mortgage Market Survey
(PMMS) 30-year fixed rate, used to pre-fill a sensible default rate for new
financing scenarios.

This is explicitly NOT the listing-site scraping this app avoids — PMMS is
a public weekly data release Freddie Mac itself publishes for exactly this
kind of downstream use. Cached to a local JSON file and only re-fetched if
the cache is more than 7 days old (PMMS is a weekly series; there is no
reason to hit it more often).

Build-environment limitation: like fulton_county.py, this was written
without network access to freddiemac.com from the build sandbox, so the CSV
URL/format below is based on Freddie Mac's documented historical-data
export pattern and hasn't been live-verified. If the fetch fails or the
format changed, `get_current_rate` falls back to `config.DEFAULT_RATE_PCT`
and flags the result as a fallback rather than raising — a stale/wrong
default rate is a bad UX surprise; a visibly-flagged fallback is not.
"""

import csv
import io
import json
import os
import time

import requests

from config import DEFAULT_RATE_PCT

PMMS_HISTORY_CSV_URL = "https://www.freddiemac.com/pmms/docs/PMMS_history.csv"
CACHE_PATH = os.environ.get(
    "DEAL_SCREENER_PMMS_CACHE", "pmms_rate_cache.json"
)
CACHE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
REQUEST_TIMEOUT_SECONDS = 15


def _read_cache() -> dict:
    if not os.path.exists(CACHE_PATH):
        return {}
    try:
        with open(CACHE_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _write_cache(data: dict) -> None:
    with open(CACHE_PATH, "w") as f:
        json.dump(data, f)


def _fetch_latest_pmms30_rate() -> float:
    response = requests.get(PMMS_HISTORY_CSV_URL, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    reader = csv.DictReader(io.StringIO(response.text))
    rows = list(reader)
    if not rows:
        raise ValueError("PMMS history CSV returned no rows")
    last_row = rows[-1]
    # Freddie Mac's historical export names the 30-year fixed column
    # "PMMS30" in most releases; fall back to the first numeric-looking
    # column if that header isn't present.
    if "PMMS30" in last_row:
        return float(last_row["PMMS30"])
    for value in last_row.values():
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    raise ValueError(f"Could not find a rate value in row: {last_row}")


def get_current_rate() -> dict:
    """Returns {"rate_pct": float, "as_of": str|None, "source": str}.

    source is "freddie_mac_pmms" on a fresh or cached live fetch, or
    "fallback_default" if both the cache and a live fetch are unavailable.
    """
    cache = _read_cache()
    cached_at = cache.get("cached_at", 0)
    if cache.get("rate_pct") is not None and (
        time.time() - cached_at < CACHE_MAX_AGE_SECONDS
    ):
        return {
            "rate_pct": cache["rate_pct"],
            "as_of": cache.get("as_of"),
            "source": "freddie_mac_pmms",
        }

    try:
        rate = _fetch_latest_pmms30_rate()
        now = time.time()
        _write_cache({"rate_pct": rate, "cached_at": now, "as_of": now})
        return {"rate_pct": rate, "as_of": now, "source": "freddie_mac_pmms"}
    except (requests.RequestException, ValueError):
        if cache.get("rate_pct") is not None:
            return {
                "rate_pct": cache["rate_pct"],
                "as_of": cache.get("as_of"),
                "source": "freddie_mac_pmms_stale_cache",
            }
        return {
            "rate_pct": DEFAULT_RATE_PCT,
            "as_of": None,
            "source": "fallback_default",
        }
