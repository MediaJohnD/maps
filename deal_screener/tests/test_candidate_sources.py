"""Tests for candidate_sources.py's parsing/filtering logic, against
representative fixture text rather than a live network call — see the
module docstring on why the real URLs/row-format are unverified. These
tests confirm the extraction and target-ZIP filtering are correct given
*some* plausible "Label: value" layout; they do not confirm that layout
matches the real fultoncountytaxes.org pages.
"""

from unittest.mock import patch

import candidate_sources

DELINQUENT_FIXTURE = """
<html><body>
Parcel: 14-0058-0002-031
Address: 187 Peeples St SW, Atlanta, GA 30315
Amount Due: $2,145.33
---
Parcel: 14-0099-0004-011
Address: 402 Lucile Ave, Atlanta, GA 30310
Amount Due: $1,876.02
---
Parcel: 14-0071-0001-018
Address: 55 Highpoint Rd, Atlanta, GA 30315
Amount Due: $3,502.10
</body></html>
"""

TAX_SALE_FIXTURE = """
<html><body>
Sale Date: 2026-08-04

Parcel: 14-0058-0002-031
Address: 187 Peeples St SW, Atlanta, GA 30315
Opening Bid: $18,500.00
---
Parcel: 14-0099-0004-011
Address: 402 Lucile Ave, Atlanta, GA 30310
Opening Bid: $22,000.00
</body></html>
"""


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


def test_delinquent_tax_filters_to_target_zip():
    with patch("candidate_sources.throttled_get") as mock_get:
        mock_get.return_value = FakeResponse(DELINQUENT_FIXTURE)
        candidates = candidate_sources.fetch_delinquent_tax_candidates()

    assert len(candidates) == 2
    zips = {c["zip"] for c in candidates}
    assert zips == {"30315"}
    assert all(c["source"] == "fulton_delinquent_tax" for c in candidates)
    amounts = sorted(c["amount"] for c in candidates)
    assert amounts == [2145.33, 3502.10]


def test_tax_sale_candidates_get_sale_date_and_zip_filter():
    with patch("candidate_sources.throttled_get") as mock_get:
        mock_get.return_value = FakeResponse(TAX_SALE_FIXTURE)
        candidates = candidate_sources.fetch_sheriff_tax_sale_candidates()

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["zip"] == "30315"
    assert candidate["sale_date"] == "2026-08-04"
    assert candidate["amount"] == 18500.00
    assert candidate["source"] == "fulton_sheriff_tax_sale"


def test_candidate_carries_raw_snippet_for_manual_verification():
    with patch("candidate_sources.throttled_get") as mock_get:
        mock_get.return_value = FakeResponse(DELINQUENT_FIXTURE)
        candidates = candidate_sources.fetch_delinquent_tax_candidates()

    assert all(c["raw_snippet"] for c in candidates)
    assert "Parcel" in candidates[0]["raw_snippet"]


def test_scan_all_tolerates_one_source_failing():
    def side_effect(url, params=None):
        if url == candidate_sources.DELINQUENT_TAX_LIST_URL:
            return FakeResponse(DELINQUENT_FIXTURE)
        raise ConnectionError("sheriff site unreachable")

    with patch("candidate_sources.throttled_get", side_effect=side_effect):
        candidates, errors = candidate_sources.scan_all()

    assert len(candidates) == 2
    assert len(errors) == 1
    assert "fetch_sheriff_tax_sale_candidates" in errors[0]
