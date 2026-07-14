"""Manual "push to HubSpot" integration.

Assumption worth flagging explicitly: the build spec calls this "HubSpot MCP
sync," but MCP servers are tools consumed inside a Claude session — they
aren't something a standalone script the user runs on their own machine can
call at runtime. This module instead uses HubSpot's standard CRM REST API
(v3) with a private-app access token, which gets the same deliberate,
one-button "push this deal" behavior the spec describes without requiring
an MCP client. If you're running this from inside a Claude session that
already has the HubSpot MCP connected, you can just ask Claude to push the
deal there instead — this module is for the app running unattended.

Never called automatically. app.py only invokes this from an explicit
"push to HubSpot" button/endpoint per deal.
"""

import os

import requests

from config import HUBSPOT_PIPELINE_ID, HUBSPOT_STAGE_MAP

HUBSPOT_API_BASE = "https://api.hubapi.com"
REQUEST_TIMEOUT_SECONDS = 15


class HubSpotNotConfigured(RuntimeError):
    pass


def _token() -> str:
    token = os.environ.get("HUBSPOT_ACCESS_TOKEN")
    if not token:
        raise HubSpotNotConfigured(
            "HUBSPOT_ACCESS_TOKEN is not set — add it to .env to enable "
            "the HubSpot push."
        )
    return token


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/json",
    }


def _deal_properties(deal, best_result) -> dict:
    stage = HUBSPOT_STAGE_MAP.get(deal.pipeline_stage, deal.pipeline_stage)
    return {
        "dealname": deal.address or f"Deal #{deal.id}",
        "pipeline": HUBSPOT_PIPELINE_ID,
        "dealstage": stage,
        "amount": str(deal.price),
        "description": (
            f"{deal.property_type}, {deal.unit_count} unit(s), "
            f"{deal.zip}. Rent ${deal.rent_monthly_total:,.0f}/mo. "
            f"Best-tier verdict: {best_result.verdict} "
            f"(${best_result.monthly_cash_flow:,.0f}/mo cash flow, "
            f"DSCR {best_result.dscr:.2f})."
        ),
    }


def push_deal(deal, best_result) -> dict:
    """Creates the HubSpot deal if `deal.hubspot_deal_id` is unset, else
    updates the existing one. Returns {"hubspot_deal_id": str}."""
    properties = _deal_properties(deal, best_result)

    if deal.hubspot_deal_id:
        response = requests.patch(
            f"{HUBSPOT_API_BASE}/crm/v3/objects/deals/{deal.hubspot_deal_id}",
            headers=_headers(),
            json={"properties": properties},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    else:
        response = requests.post(
            f"{HUBSPOT_API_BASE}/crm/v3/objects/deals",
            headers=_headers(),
            json={"properties": properties},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    response.raise_for_status()
    body = response.json()
    return {"hubspot_deal_id": body["id"]}
