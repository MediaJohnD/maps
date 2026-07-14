"""Editable configuration for the deal screener.

Everything here is a *default* the investor can override per-deal or
per-scenario through the app — nothing in the screening engine reads these
values directly except `seed.py`, which writes them into the database as the
starting config row. Treat this file as the single place to update the
investor's numbers when they change (new cash position, new financing lane,
etc.) without touching any application code.
"""

from dataclasses import dataclass, field


@dataclass
class FinancingLane:
    name: str
    note: str = ""
    typical_rate_range: str = ""


@dataclass
class InvestorProfile:
    credit_score: int = 800
    gross_annual_income: float = 205_000
    existing_monthly_debt: float = 4_200  # $3,600 mortgage + $600 car
    current_mortgage_rate_pct: float = 5.5
    current_mortgage_product: str = "7/7 ARM"
    current_mortgage_monthly_payment: float = 3_600

    # Acorns (~$48.8K) + cash (~$15.2K), minus buffer. This is the ONLY figure
    # the verdict logic treats as spendable capital for a deal's cash-to-close.
    cash_available_for_deals: float = 54_000

    # Stash (~$81.5K) is intentionally NOT part of cash_available_for_deals.
    # It exists purely to be cited to a lender as post-closing reserves.
    reserves_source_note: str = (
        "Stash brokerage (~$81.5K) documented for lender reserves only — "
        "never counted as spendable capital."
    )

    target_markets: tuple = ("30315", "Fulton County, GA")
    strategy: str = (
        "15% down conventional, self-managed, value-add or small 2-4 unit, "
        "must clear positive monthly cash flow — reject breakeven "
        "single-family deals."
    )

    financing_lanes: tuple = field(
        default_factory=lambda: (
            FinancingLane(
                name="Credit union (CUFS)",
                note=(
                    "Confirmed owner-occupied only as of 2026-07-13. "
                    "Investment-property availability unconfirmed — flag as "
                    "open question, don't assume."
                ),
            ),
            FinancingLane(
                name="Conventional bank (investment)",
                typical_rate_range="7.1%-7.6%",
            ),
            FinancingLane(
                name="DSCR",
                typical_rate_range="6.5%-8.0%",
                note=(
                    "Qualifies on rental income, not personal DTI. Best "
                    "pricing tier at 800+ credit."
                ),
            ),
            FinancingLane(
                name="Private lender",
                note=(
                    "Terms not yet obtained — rate, points, term, LTV/LTC, "
                    "entity-lending, prepay penalty all TBD."
                ),
            ),
        )
    )


DEFAULT_INVESTOR_PROFILE = InvestorProfile()

# Default financing-scenario assumptions, applied unless a deal overrides
# them. Percentages are expressed as plain numbers (5 == 5%), matching the
# formulas in screening.py.
DEFAULT_LOAN_YEARS = 30
DEFAULT_RATE_PCT = 7.3  # fallback if no Freddie Mac PMMS cache is available
DEFAULT_VACANCY_PCT = 5.0
DEFAULT_MAINTENANCE_PCT = 8.0
DEFAULT_CAPEX_PCT = 5.0
DEFAULT_MGMT_PCT = 0.0  # self-managed
DEFAULT_CLOSING_COST_PCT = 3.0
DEFAULT_RESERVE_MONTHS = 6

# The three down-payment tiers shown side-by-side for every saved deal.
DEFAULT_DOWN_PAYMENT_TIERS_PCT = (15.0, 20.0, 25.0)

# Verdict thresholds — see screening.py:classify_verdict for the logic these
# feed into.
MIN_GREEN_MONTHLY_CASH_FLOW = 200.0
MIN_GREEN_DSCR = 1.0

# HubSpot pipeline stage mapping. These are placeholder internal IDs —
# HubSpot pipeline/stage IDs are account-specific and must be replaced with
# the real ones from the target HubSpot portal (Settings -> Deals ->
# Pipelines) before hubspot_sync.py will push to the correct stage.
HUBSPOT_PIPELINE_ID = "default"
HUBSPOT_STAGE_MAP = {
    "screening": "appointmentscheduled",
    "offer": "qualifiedtobuy",
    "under_contract": "contractsent",
    "closed": "closedwon",
    "passed": "closedlost",
}
