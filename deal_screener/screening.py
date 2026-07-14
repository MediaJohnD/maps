"""The financial screening engine.

Pure functions only — no I/O, no database access — so the regression test in
tests/test_screening.py exercises exactly the same code path the app uses.
Formulas match the build spec verbatim; see the module docstring on each
function for the exact expression it implements.
"""

from config import (
    DEFAULT_DOWN_PAYMENT_TIERS_PCT,
    MIN_GREEN_DSCR,
    MIN_GREEN_MONTHLY_CASH_FLOW,
)
from models import Deal, DealResult, FinancingScenario


def amortized_payment(
    loan_amount: float, rate_pct: float, loan_years: int
) -> float:
    """Standard monthly principal & interest payment.

    monthly_rate = rate_pct / 100 / 12
    n_payments = loan_years * 12
    payment = loan_amount * monthly_rate * (1 + monthly_rate) ** n_payments
              / ((1 + monthly_rate) ** n_payments - 1)
    """
    monthly_rate = rate_pct / 100 / 12
    n_payments = loan_years * 12
    if monthly_rate == 0:
        return loan_amount / n_payments
    growth = (1 + monthly_rate) ** n_payments
    return loan_amount * monthly_rate * growth / (growth - 1)


def classify_verdict(
    monthly_cash_flow: float,
    dscr: float,
    cash_to_close: float,
    cash_available_for_deals: float,
) -> tuple:
    """Returns (verdict, reasons) per the build spec's verdict logic.

    - Over budget (red): cash_to_close > cash_available_for_deals
    - Bleeds cash (red): monthly_cash_flow < 0
    - Clears the bar (green): monthly_cash_flow >= 200 AND dscr >= 1.0
      AND cash_to_close <= cash_available_for_deals
    - Thin/breakeven (amber): everything else
    """
    reasons = []

    if cash_to_close > cash_available_for_deals:
        reasons.append(
            f"Cash to close (${cash_to_close:,.0f}) exceeds available "
            f"capital (${cash_available_for_deals:,.0f})"
        )
        return "red", reasons

    if monthly_cash_flow < 0:
        reasons.append(
            f"Negative monthly cash flow (${monthly_cash_flow:,.0f})"
        )
        return "red", reasons

    if monthly_cash_flow >= MIN_GREEN_MONTHLY_CASH_FLOW and dscr >= MIN_GREEN_DSCR:
        reasons.append(
            f"Cash flow (${monthly_cash_flow:,.0f}/mo) and DSCR "
            f"({dscr:.2f}) both clear the bar"
        )
        return "green", reasons

    if monthly_cash_flow < MIN_GREEN_MONTHLY_CASH_FLOW:
        reasons.append(
            f"Cash flow (${monthly_cash_flow:,.0f}/mo) is below the "
            f"${MIN_GREEN_MONTHLY_CASH_FLOW:,.0f}/mo bar"
        )
    if dscr < MIN_GREEN_DSCR:
        reasons.append(f"DSCR ({dscr:.2f}) is below {MIN_GREEN_DSCR:.2f}")
    return "amber", reasons


def evaluate(
    deal: Deal, scenario: FinancingScenario, cash_available_for_deals: float
) -> DealResult:
    """Runs one deal through one financing scenario and returns DealResult."""
    loan_amount = deal.price * (1 - scenario.down_pct / 100)
    principal_interest = amortized_payment(
        loan_amount, scenario.rate_pct, scenario.loan_years
    )
    piti = (
        principal_interest
        + deal.tax_annual / 12
        + deal.insurance_annual / 12
        + deal.hoa_monthly
    )
    dscr = deal.rent_monthly_total / piti if piti else 0.0

    expense_pct = (
        scenario.vacancy_pct
        + scenario.maintenance_pct
        + scenario.capex_pct
        + scenario.mgmt_pct
    )
    operating_expenses = deal.rent_monthly_total * expense_pct / 100

    monthly_cash_flow = deal.rent_monthly_total - piti - operating_expenses
    annual_cash_flow = monthly_cash_flow * 12

    down_payment = deal.price * (scenario.down_pct / 100)
    closing_costs = deal.price * (scenario.closing_cost_pct / 100)
    cash_to_close = down_payment + closing_costs
    cash_on_cash_pct = (
        (annual_cash_flow / cash_to_close) * 100 if cash_to_close else 0.0
    )

    reserves_required = piti * scenario.reserve_months

    verdict, reasons = classify_verdict(
        monthly_cash_flow, dscr, cash_to_close, cash_available_for_deals
    )

    return DealResult(
        scenario=scenario,
        loan_amount=loan_amount,
        principal_interest=principal_interest,
        piti=piti,
        dscr=dscr,
        operating_expenses=operating_expenses,
        monthly_cash_flow=monthly_cash_flow,
        annual_cash_flow=annual_cash_flow,
        down_payment=down_payment,
        closing_costs=closing_costs,
        cash_to_close=cash_to_close,
        cash_on_cash_pct=cash_on_cash_pct,
        reserves_required=reserves_required,
        verdict=verdict,
        reasons=reasons,
    )


def default_scenarios(
    rate_pct: float,
    loan_years: int = 30,
    closing_cost_pct: float = 3.0,
    reserve_months: float = 6,
    vacancy_pct: float = 5.0,
    maintenance_pct: float = 8.0,
    capex_pct: float = 5.0,
    mgmt_pct: float = 0.0,
) -> list:
    """The 15% / 20% / 25% down comparison shown for every saved deal.

    Rate and every expense assumption are held constant across the three
    tiers so the only variable is down payment — an apples-to-apples
    comparison. This doesn't model PMI (which could lower the effective rate
    at >=20% down); that's a simplification, not an oversight, documented in
    the README.
    """
    return [
        FinancingScenario(
            down_pct=down_pct,
            rate_pct=rate_pct,
            loan_years=loan_years,
            closing_cost_pct=closing_cost_pct,
            reserve_months=reserve_months,
            vacancy_pct=vacancy_pct,
            maintenance_pct=maintenance_pct,
            capex_pct=capex_pct,
            mgmt_pct=mgmt_pct,
        )
        for down_pct in DEFAULT_DOWN_PAYMENT_TIERS_PCT
    ]


def evaluate_all_tiers(
    deal: Deal, rate_pct: float, cash_available_for_deals: float
) -> list:
    """Evaluates a deal against the default 15/20/25% down tiers."""
    return [
        evaluate(deal, scenario, cash_available_for_deals)
        for scenario in default_scenarios(rate_pct)
    ]
