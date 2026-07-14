"""Data model for deals, financing scenarios, and computed results.

These are plain dataclasses, not an ORM — db.py maps them to/from SQLite rows
by hand. For a single-user local app that's less machinery than an ORM and
keeps the schema visible in one place (db.py's `CREATE TABLE` statements).
"""

from dataclasses import dataclass, field
from typing import Optional

PROPERTY_TYPES = ("SFH", "duplex", "tri", "quad")
DEAL_SOURCES = (
    "manual_paste",
    "screenshot",
    "manual_entry",
    "fulton_county_lookup",
)
PIPELINE_STAGES = (
    "screening",
    "offer",
    "under_contract",
    "closed",
    "passed",
)


@dataclass
class Deal:
    id: Optional[int] = None
    address: str = ""
    zip: str = ""
    price: float = 0.0
    beds: Optional[float] = None
    baths: Optional[float] = None
    sqft: Optional[float] = None
    unit_count: int = 1
    property_type: str = "SFH"
    listing_url: str = ""  # stored as reference text only, never fetched
    rent_monthly_total: float = 0.0
    tax_annual: float = 0.0
    insurance_annual: float = 0.0
    hoa_monthly: float = 0.0
    condition_notes: str = ""
    source: str = "manual_entry"
    pipeline_stage: str = "screening"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    raw_pasted_text: str = ""
    fulton_county_lookup: Optional[dict] = None
    hubspot_deal_id: Optional[str] = None


@dataclass
class FinancingScenario:
    down_pct: float
    rate_pct: float
    loan_years: int = 30
    closing_cost_pct: float = 3.0
    reserve_months: float = 6
    vacancy_pct: float = 5.0
    maintenance_pct: float = 8.0
    capex_pct: float = 5.0
    mgmt_pct: float = 0.0


@dataclass
class DealResult:
    scenario: FinancingScenario
    loan_amount: float
    principal_interest: float
    piti: float
    dscr: float
    operating_expenses: float
    monthly_cash_flow: float
    annual_cash_flow: float
    down_payment: float
    closing_costs: float
    cash_to_close: float
    cash_on_cash_pct: float
    reserves_required: float
    verdict: str  # "green" | "amber" | "red"
    reasons: list = field(default_factory=list)
