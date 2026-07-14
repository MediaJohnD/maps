"""Public-record lookups against Fulton County government sites.

This is deliberately separate from parsing.py. parsing.py never fetches
anything — it only processes text/images the user already copied. This
module *does* make outbound HTTP requests, but only to two Georgia county
government sites publishing records under the state's Open Records Act:

- fultonassessor.org (Board of Assessors — assessed value, parcel data)
- fultoncountytaxes.org (Tax Commissioner — delinquent-tax status)

Neither is a listing aggregator and neither publishes a scraping-restrictive
ToS the way Zillow/Redfin/realtor.com do; requests go through
gov_records_http's shared throttle to stay well within "occasional,
human-paced lookup by parcel/address" rather than bulk harvesting.

IMPORTANT — build-environment limitation: this code was written without
network access to fultonassessor.org / fultoncountytaxes.org (the sandbox
this app was built in has no egress to Georgia county sites), so the exact
search-results HTML structure below has NOT been verified against the live
site. The request plumbing, rate limiting, and error handling are solid;
the actual field-extraction regexes are a best-effort based on how these
county GIS/assessor portals (typically Schneider Corp's qPublic platform)
tend to render search results, and will likely need a pass of adjustment
against the real page before this is fully reliable. Treat lookup results
as "best effort, verify against the raw_snippet" until confirmed.
"""

import re
from urllib.parse import quote

import requests

from gov_records_http import throttled_get

ASSESSOR_SEARCH_URL = "https://qpublic.schneidercorp.com/Application.aspx"
ASSESSOR_APP_ID = "1132"  # Fulton County's qPublic AppID as of this writing
TAX_COMMISSIONER_SEARCH_URL = (
    "https://www.fultoncountytaxes.org/property-taxes/property-search"
)

_DOLLAR_NEAR_LABEL_RE = re.compile(
    r"(assessed\s+value|total\s+appraised\s+value)\D{0,20}\$?([\d,]+)",
    re.IGNORECASE,
)
_PARCEL_RE = re.compile(
    r"(parcel\s*(?:id|number)?)\D{0,10}([\d\-]{6,})", re.IGNORECASE
)
_YEAR_BUILT_RE = re.compile(r"year\s+built\D{0,10}(\d{4})", re.IGNORECASE)


def lookup_assessor(address: str) -> dict:
    """Best-effort assessed-value/parcel lookup. Returns a dict always
    containing `raw_snippet` (first 2000 chars of the response body) so a
    human can sanity-check the parse regardless of whether the regexes
    above matched anything on the live page structure."""
    result = {
        "source": "fultonassessor.org",
        "source_url": None,
        "assessed_value": None,
        "parcel_id": None,
        "year_built": None,
        "raw_snippet": None,
        "error": None,
    }
    try:
        response = throttled_get(
            ASSESSOR_SEARCH_URL,
            params={"AppID": ASSESSOR_APP_ID, "PageType": "Search", "q": address},
        )
        response.raise_for_status()
        result["source_url"] = response.url
        body = response.text
        result["raw_snippet"] = body[:2000]

        value_match = _DOLLAR_NEAR_LABEL_RE.search(body)
        if value_match:
            result["assessed_value"] = float(
                value_match.group(2).replace(",", "")
            )

        parcel_match = _PARCEL_RE.search(body)
        if parcel_match:
            result["parcel_id"] = parcel_match.group(2)

        year_match = _YEAR_BUILT_RE.search(body)
        if year_match:
            result["year_built"] = int(year_match.group(1))
    except requests.RequestException as exc:
        result["error"] = str(exc)
    return result


_DELINQUENT_RE = re.compile(r"delinquent", re.IGNORECASE)
_AMOUNT_DUE_RE = re.compile(
    r"(amount\s+due|balance\s+due)\D{0,20}\$?([\d,]+(?:\.\d{2})?)",
    re.IGNORECASE,
)


def lookup_delinquent_tax(address_or_parcel: str) -> dict:
    """Best-effort delinquent-tax status lookup. Same raw_snippet
    fallback as lookup_assessor for manual verification."""
    result = {
        "source": "fultoncountytaxes.org",
        "source_url": None,
        "delinquent": None,
        "amount_owed": None,
        "raw_snippet": None,
        "error": None,
    }
    try:
        response = throttled_get(
            TAX_COMMISSIONER_SEARCH_URL,
            params={"q": quote(address_or_parcel)},
        )
        response.raise_for_status()
        result["source_url"] = response.url
        body = response.text
        result["raw_snippet"] = body[:2000]

        result["delinquent"] = bool(_DELINQUENT_RE.search(body))

        amount_match = _AMOUNT_DUE_RE.search(body)
        if amount_match:
            result["amount_owed"] = float(
                amount_match.group(2).replace(",", "")
            )
    except requests.RequestException as exc:
        result["error"] = str(exc)
    return result


def lookup(address: str) -> dict:
    """Combined lookup used by the app's 'check Fulton County records'
    button — one throttled call to each source."""
    return {
        "assessor": lookup_assessor(address),
        "delinquent_tax": lookup_delinquent_tax(address),
    }
