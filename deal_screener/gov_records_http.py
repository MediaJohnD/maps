"""Shared rate-limited HTTP helper for Georgia/Fulton County public-records
fetches (fulton_county.py's single-address lookups, candidate_sources.py's
bulk scans).

One shared throttle clock across every caller, not one per module — the
point of rate-limiting is to keep total traffic to these sites "occasional,
human-paced," and that guarantee only holds if a lookup and a bulk scan
running back-to-back share the same clock instead of each getting their own
independent budget.
"""

import time

import requests

RATE_LIMIT_SECONDS = 3.0
REQUEST_TIMEOUT_SECONDS = 15
USER_AGENT = (
    "deal-screener/0.1 (personal underwriting tool; single-user, "
    "human-paced lookups; contact via listed county assessor account)"
)

_last_request_at = 0.0


def _throttle() -> None:
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    if elapsed < RATE_LIMIT_SECONDS:
        time.sleep(RATE_LIMIT_SECONDS - elapsed)
    _last_request_at = time.monotonic()


def throttled_get(url: str, params: dict = None) -> requests.Response:
    _throttle()
    return requests.get(
        url,
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
