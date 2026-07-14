"""Bulk discovery of candidate properties from Fulton County public records.

Unlike fulton_county.py's single-address lookup (which enriches a deal you
already have), this module answers "what distressed properties exist in my
target area right now" — the sourcing half of the tool. It's built on
exactly the same public-records exception to the no-scraping rule already
used there: these are government records under Georgia's Open Records Act,
not listing-site data, and requests share fulton_county's rate-limited
gov_records_http.throttled_get.

Two sources:

- **Delinquent property tax list** (fultoncountytaxes.org) — properties
  behind on tax payments; the earliest-stage distress signal.
- **Upcoming Sheriff's tax sale list** — foreclosure-auction candidates,
  published ahead of the first-Tuesday-of-the-month sale.

Both are filtered down to `config.DEFAULT_INVESTOR_PROFILE.target_markets`
(30315 today) before being returned — the point is a short, relevant
candidate list, not a county-wide harvest.

IMPORTANT — same build-environment caveat as fulton_county.py, more acutely
here: this was written with NO live access to fultoncountytaxes.org or a
Fulton County Sheriff's-sale site, so `DELINQUENT_TAX_LIST_URL` and
`SHERIFF_TAX_SALE_URL` below are best-effort guesses, and the row-parsing
regexes assume a plain "Label: value" layout (Parcel: / Address: /
Amount Due: or Opening Bid:) that real HTML will very likely NOT match
verbatim — actual pages are more likely to render this as an HTML table or
a downloadable PDF/CSV. Parsing logic is unit-tested against representative
fixtures in tests/test_candidate_sources.py so the extraction/filtering
logic itself is verified, but the URLs and the exact row format need
confirmation (and likely a rewrite of `_CANDIDATE_ROW_RE`) against the real
pages before this reliably finds anything. Every returned candidate carries
`raw_snippet` for manual sanity-checking in the meantime.
"""

import re

from config import DEFAULT_INVESTOR_PROFILE
from gov_records_http import throttled_get

DELINQUENT_TAX_LIST_URL = (
    "https://www.fultoncountytaxes.org/property-taxes/delinquent-tax-list"
)
SHERIFF_TAX_SALE_URL = (
    "https://www.fultoncountytaxes.org/property-taxes/sheriff-tax-sales"
)

TARGET_ZIPS = tuple(
    market for market in DEFAULT_INVESTOR_PROFILE.target_markets
    if market.isdigit() and len(market) == 5
)


def _row_pattern(amount_label: str) -> re.Pattern:
    return re.compile(
        r"Parcel:?\s*([\w-]{6,20})\s*"
        r"Address:?\s*([^\n]+?,\s*GA\s+(\d{5}))\s*"
        rf"{amount_label}:?\s*\$?\s*([\d,]+(?:\.\d{{2}})?)",
        re.IGNORECASE,
    )


_DELINQUENT_ROW_RE = _row_pattern("Amount Due")
_TAX_SALE_ROW_RE = _row_pattern("Opening Bid")
_SALE_DATE_RE = re.compile(
    r"Sale Date:?\s*([\d/\-]{6,10})", re.IGNORECASE
)


def _matches_target_zip(zip_code: str) -> bool:
    return not TARGET_ZIPS or zip_code in TARGET_ZIPS


def _extract_candidates(body: str, pattern: re.Pattern, source: str) -> list:
    candidates = []
    for match in pattern.finditer(body):
        parcel_id, address, zip_code, amount = match.groups()
        if not _matches_target_zip(zip_code):
            continue
        candidates.append({
            "source": source,
            "external_id": parcel_id.strip(),
            "address": address.strip(),
            "zip": zip_code,
            "amount": float(amount.replace(",", "")),
            "sale_date": None,
            "raw_snippet": match.group(0)[:500],
        })
    return candidates


def fetch_delinquent_tax_candidates() -> list:
    response = throttled_get(DELINQUENT_TAX_LIST_URL)
    response.raise_for_status()
    return _extract_candidates(
        response.text, _DELINQUENT_ROW_RE, "fulton_delinquent_tax"
    )


def fetch_sheriff_tax_sale_candidates() -> list:
    response = throttled_get(SHERIFF_TAX_SALE_URL)
    response.raise_for_status()
    body = response.text
    candidates = _extract_candidates(body, _TAX_SALE_ROW_RE, "fulton_sheriff_tax_sale")
    sale_date_match = _SALE_DATE_RE.search(body)
    sale_date = sale_date_match.group(1) if sale_date_match else None
    for candidate in candidates:
        candidate["sale_date"] = sale_date
    return candidates


def scan_all() -> tuple:
    """Runs both scans, tolerating either failing independently — these are
    two separately-maintained government pages with no uptime guarantee.
    Returns (candidates, errors); errors is a list of "source: message"
    strings for any scan that failed, so a broken sheriff-sale page doesn't
    also hide a working delinquent-tax result."""
    candidates = []
    errors = []
    for fetch_fn in (
        fetch_delinquent_tax_candidates,
        fetch_sheriff_tax_sale_candidates,
    ):
        try:
            candidates.extend(fetch_fn())
        except Exception as exc:
            errors.append(f"{fetch_fn.__name__}: {exc}")
    return candidates, errors
