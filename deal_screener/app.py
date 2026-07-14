"""FastAPI backend for the 30315 deal screener.

Single-page local web app: this serves both the JSON API and the static
frontend (static/index.html). Run with:

    uvicorn app:app --reload

See README.md for full setup instructions.
"""

from dataclasses import asdict
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()  # before other local imports: several read env vars at import time

import candidate_sources
import db
import fulton_county
import freddie_mac
import parsing
import screening
from config import DEFAULT_INVESTOR_PROFILE, DEFAULT_RATE_PCT
from models import Deal, FinancingScenario

app = FastAPI(title="30315 Deal Screener")
db.init_db()


# ---------------------------------------------------------------------------
# Request/response schemas
# ---------------------------------------------------------------------------

class ParseTextRequest(BaseModel):
    raw_text: str


class DealCreateRequest(BaseModel):
    address: str = ""
    zip: str = ""
    price: float = 0
    beds: Optional[float] = None
    baths: Optional[float] = None
    sqft: Optional[float] = None
    unit_count: int = 1
    property_type: str = "SFH"
    listing_url: str = ""
    rent_monthly_total: float = 0
    tax_annual: float = 0
    insurance_annual: float = 0
    hoa_monthly: float = 0
    condition_notes: str = ""
    source: str = "manual_entry"
    raw_pasted_text: str = ""


class DealUpdateRequest(BaseModel):
    address: Optional[str] = None
    zip: Optional[str] = None
    price: Optional[float] = None
    beds: Optional[float] = None
    baths: Optional[float] = None
    sqft: Optional[float] = None
    unit_count: Optional[int] = None
    property_type: Optional[str] = None
    listing_url: Optional[str] = None
    rent_monthly_total: Optional[float] = None
    tax_annual: Optional[float] = None
    insurance_annual: Optional[float] = None
    hoa_monthly: Optional[float] = None
    condition_notes: Optional[str] = None
    pipeline_stage: Optional[str] = None


class RecomputeRequest(BaseModel):
    down_pct: float
    rate_pct: float
    loan_years: int = 30
    closing_cost_pct: float = 3.0
    reserve_months: float = 6
    vacancy_pct: float = 5.0
    maintenance_pct: float = 8.0
    capex_pct: float = 5.0
    mgmt_pct: float = 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _deal_with_tiers(deal: Deal, rate_pct: float) -> dict:
    results = screening.evaluate_all_tiers(
        deal, rate_pct, DEFAULT_INVESTOR_PROFILE.cash_available_for_deals
    )
    return {"deal": asdict(deal), "tiers": [asdict(r) for r in results]}


def _current_default_rate() -> float:
    rate_info = freddie_mac.get_current_rate()
    return rate_info["rate_pct"]


def _get_deal_or_404(deal_id: int) -> Deal:
    deal = db.get_deal(deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    return deal


# ---------------------------------------------------------------------------
# Config / rates
# ---------------------------------------------------------------------------

@app.get("/api/config")
def get_config():
    return {
        "investor_profile": asdict(DEFAULT_INVESTOR_PROFILE),
        "default_rate_pct": DEFAULT_RATE_PCT,
    }


@app.get("/api/rates/freddie-mac")
def get_freddie_mac_rate():
    return freddie_mac.get_current_rate()


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

@app.post("/api/parse/text")
def parse_text(request: ParseTextRequest):
    return parsing.parse_text(request.raw_text)


@app.post("/api/parse/screenshot")
async def parse_screenshot(image: UploadFile = File(...)):
    image_bytes = await image.read()
    media_type = image.content_type or "image/png"
    try:
        return parsing.parse_image(image_bytes, media_type)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# ---------------------------------------------------------------------------
# Deals
# ---------------------------------------------------------------------------

@app.post("/api/deals")
def create_deal(request: DealCreateRequest):
    deal = Deal(**request.model_dump())
    saved = db.create_deal(deal)
    return _deal_with_tiers(saved, _current_default_rate())


@app.get("/api/deals")
def list_deals():
    rate_pct = _current_default_rate()
    return [_deal_with_tiers(deal, rate_pct) for deal in db.list_deals()]


@app.get("/api/deals/{deal_id}")
def get_deal(deal_id: int):
    deal = _get_deal_or_404(deal_id)
    return _deal_with_tiers(deal, _current_default_rate())


@app.patch("/api/deals/{deal_id}")
def update_deal(deal_id: int, request: DealUpdateRequest):
    _get_deal_or_404(deal_id)
    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    updated = db.update_deal(deal_id, updates)
    return _deal_with_tiers(updated, _current_default_rate())


@app.post("/api/deals/{deal_id}/recompute")
def recompute(deal_id: int, request: RecomputeRequest):
    deal = _get_deal_or_404(deal_id)
    scenario = FinancingScenario(**request.model_dump())
    result = screening.evaluate(
        deal, scenario, DEFAULT_INVESTOR_PROFILE.cash_available_for_deals
    )
    return asdict(result)


@app.post("/api/deals/{deal_id}/fulton-lookup")
def fulton_lookup(deal_id: int):
    deal = _get_deal_or_404(deal_id)
    if not deal.address:
        raise HTTPException(
            status_code=400, detail="Deal has no address to look up"
        )
    lookup_result = fulton_county.lookup(deal.address)
    updated = db.save_fulton_lookup(deal_id, lookup_result)
    return _deal_with_tiers(updated, _current_default_rate())


# ---------------------------------------------------------------------------
# Candidate sourcing (Fulton County public-records bulk scans)
# ---------------------------------------------------------------------------

@app.post("/api/candidates/scan")
def scan_candidates():
    """Runs both bulk scans, persists results (dedup + status-preserving),
    and returns the current 'new' candidates plus any per-source errors."""
    found, errors = candidate_sources.scan_all()
    summary = db.upsert_candidates(found)
    return {
        "summary": summary,
        "errors": errors,
        "candidates": [asdict(c) for c in db.list_candidates(status="new")],
    }


@app.get("/api/candidates")
def list_candidates(status: Optional[str] = None):
    return [asdict(c) for c in db.list_candidates(status)]


@app.post("/api/candidates/{candidate_id}/dismiss")
def dismiss_candidate(candidate_id: int):
    candidate = db.update_candidate_status(candidate_id, "dismissed")
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return asdict(candidate)


@app.post("/api/candidates/{candidate_id}/import")
def import_candidate(candidate_id: int):
    candidate = db.get_candidate(candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if candidate.source == "fulton_delinquent_tax":
        note = (
            f"Sourced from Fulton County delinquent tax list. "
            f"Amount owed: ${candidate.amount:,.2f}."
        )
    else:
        note = f"Sourced from Fulton County Sheriff's tax sale list. "
        if candidate.amount is not None:
            note += f"Opening bid: ${candidate.amount:,.2f}. "
        if candidate.sale_date:
            note += f"Sale date: {candidate.sale_date}."

    deal = Deal(
        address=candidate.address,
        zip=candidate.zip,
        source="fulton_county_lookup",
        condition_notes=note,
        raw_pasted_text=candidate.raw_snippet,
    )
    saved = db.create_deal(deal)
    db.mark_candidate_imported(candidate_id, saved.id)
    return _deal_with_tiers(saved, _current_default_rate())


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")
