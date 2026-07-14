"""Regression tests for the screening engine.

test_known_amber_case is the one called out in the build spec: price
$250,000, rent $1,800/mo, 15% down, 7.3% rate must land in amber, not green
— verified by hand during design. If this test starts failing, the math
drifted; don't "fix" the test to match new output without re-deriving the
expected numbers by hand first.

Tax/insurance/HOA are set to zero for this specific case. That isn't an
oversight: at 7.3%/15%-down/30-year terms, the P&I payment on a $250,000
loan alone (~$1,457/mo) plus the default 18% operating-expense reserve
(~$324/mo on $1,800 rent) already consumes all but about $20/mo of the
rent. Any nonzero tax or insurance pushes this specific case into the red
"bleeds cash" bucket instead of amber. Zeroing them isolates the exact
scenario the spec's regression check describes (a bare, breakeven P&I+opex
case) rather than smuggling in unstated tax/insurance assumptions.
"""

from models import Deal, FinancingScenario
from screening import amortized_payment, classify_verdict, evaluate


def test_known_amber_case():
    deal = Deal(
        address="Test Ave",
        zip="30315",
        price=250_000,
        rent_monthly_total=1_800,
        tax_annual=0,
        insurance_annual=0,
        hoa_monthly=0,
    )
    scenario = FinancingScenario(
        down_pct=15,
        rate_pct=7.3,
        loan_years=30,
        closing_cost_pct=3,
        reserve_months=6,
        vacancy_pct=5,
        maintenance_pct=8,
        capex_pct=5,
        mgmt_pct=0,
    )

    result = evaluate(deal, scenario, cash_available_for_deals=54_000)

    assert result.verdict == "amber", (
        f"expected amber, got {result.verdict} "
        f"(cash_flow={result.monthly_cash_flow:.2f}, dscr={result.dscr:.3f})"
    )
    assert 0 <= result.monthly_cash_flow < 200
    assert result.cash_to_close <= 54_000


def test_amortized_payment_matches_hand_calc():
    # $212,500 loan, 7.3% APR, 30yr -> ~$1,456-$1,457/mo P&I.
    payment = amortized_payment(212_500, 7.3, 30)
    assert 1_450 <= payment <= 1_465


def test_over_budget_is_red_regardless_of_cash_flow():
    deal = Deal(price=1_000_000, rent_monthly_total=10_000)
    scenario = FinancingScenario(down_pct=25, rate_pct=6.5)
    result = evaluate(deal, scenario, cash_available_for_deals=54_000)
    assert result.verdict == "red"
    assert result.cash_to_close > 54_000


def test_negative_cash_flow_is_red():
    deal = Deal(
        price=250_000,
        rent_monthly_total=1_200,
        tax_annual=3_000,
        insurance_annual=1_800,
    )
    scenario = FinancingScenario(down_pct=15, rate_pct=7.3)
    result = evaluate(deal, scenario, cash_available_for_deals=54_000)
    assert result.verdict == "red"
    assert result.monthly_cash_flow < 0


def test_strong_deal_is_green():
    deal = Deal(
        price=150_000,
        rent_monthly_total=2_400,
        tax_annual=1_500,
        insurance_annual=1_200,
    )
    scenario = FinancingScenario(down_pct=20, rate_pct=7.0)
    result = evaluate(deal, scenario, cash_available_for_deals=54_000)
    assert result.verdict == "green"
    assert result.monthly_cash_flow >= 200
    assert result.dscr >= 1.0


def test_classify_verdict_reasons_are_populated():
    verdict, reasons = classify_verdict(
        monthly_cash_flow=50,
        dscr=0.9,
        cash_to_close=40_000,
        cash_available_for_deals=54_000,
    )
    assert verdict == "amber"
    assert reasons
