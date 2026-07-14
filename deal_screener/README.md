# 30315 Deal Screener

A local-first real estate deal screener and pipeline tracker for evaluating
small multifamily (2-4 unit) and value-add properties in and around Atlanta
ZIP 30315 / Fulton County, GA. Single-operator tool — not a product.

Lives in this monorepo at `deal_screener/` for now (built here rather than
its own repo because the session's GitHub integration can't create new
repositories; splitting it out later is a straightforward `git subtree` /
history-filter job if still wanted).

## Hard constraint honored

**No automated scraping of Zillow, Redfin, realtor.com, or any MLS/listing
aggregator.** Listing data only enters the system via:

1. Pasting raw listing text into a text box,
2. Uploading a screenshot of a listing, or
3. Manual form entry.

Both (1) and (2) run through regex + an Anthropic API call to extract
structured fields, but **always** show the parsed result for correction
before saving — nothing is trusted silently. Fulton County government
records (`fultonassessor.org`, `fultoncountytaxes.org`) are the one
exception to "no automated fetching," since they're public records with no
scraping-restrictive ToS in the way this app uses them (occasional,
rate-limited, human-paced lookups) — see `fulton_county.py`.

## Setup

```bash
cd deal_screener
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in ANTHROPIC_API_KEY (required for LLM parsing)
python3 seed.py        # creates deal_screener.db and seeds the investor profile
uvicorn app:app --reload
```

Open http://127.0.0.1:8000/.

Run the test suite (in particular the regression check described below):

```bash
pytest tests/ -v
```

## How it works

- **Find Candidates** — bulk-scans Fulton County's public delinquent-tax
  list and upcoming Sheriff's tax-sale list (same public-records exception
  as the single-address lookup below), filtered to your target ZIP(s).
  Results persist locally with a status (new / imported / dismissed) so
  re-scanning never resurfaces something you've already handled. Import a
  candidate to create a draft deal (address/zip pre-filled, price/rent
  still $0 — you fill those in before it means anything) or dismiss it.
  This is the actual sourcing half of the tool — see "Assumptions" below
  for how unverified the live site format is.
- **Add Deal** — paste text, upload a screenshot, or fill the form
  directly. Paste/screenshot both converge on the same editable
  parsed-fields form; nothing saves until you click Save.
- **Pipeline** — every saved deal, verdict-coded (green/amber/red) at its
  15%-down scenario, sortable by cash flow / DSCR / cash-to-close,
  filterable by pipeline stage.
- **Deal detail** — full breakdown at 15%, 20%, and 25% down side by side,
  with editable assumptions (rate, vacancy/maintenance/capex/mgmt %,
  closing cost %, reserve months) that recalculate live via the backend
  (single source of truth for the math — the frontend never reimplements
  the formulas). Also: a Fulton County lookup button, notes, and
  pipeline-stage control.

## Screening engine

Exact formulas (see `screening.py`):

```
monthly_rate = rate_pct / 100 / 12
n_payments = loan_years * 12
loan_amount = price * (1 - down_pct/100)
principal_interest = amortized payment on loan_amount, monthly_rate, n_payments
piti = principal_interest + (tax_annual/12) + (insurance_annual/12) + hoa_monthly
dscr = rent_monthly_total / piti

operating_expenses = rent_monthly_total * (vacancy_pct + maintenance_pct + capex_pct + mgmt_pct) / 100
monthly_cash_flow = rent_monthly_total - piti - operating_expenses

cash_to_close = price*(down_pct/100) + price*(closing_cost_pct/100)
cash_on_cash_pct = (monthly_cash_flow * 12 / cash_to_close) * 100
reserves_required = piti * reserve_months
```

Verdict:

- **Green**: `monthly_cash_flow >= 200` AND `dscr >= 1.0` AND
  `cash_to_close <= cash_available_for_deals`
- **Red**: `cash_to_close > cash_available_for_deals` (over budget), OR
  `monthly_cash_flow < 0` (bleeds cash)
- **Amber**: everything else (thin/breakeven)

Defaults: vacancy 5%, maintenance 8%, capex 5%, mgmt 0% (self-managed),
closing cost 3%, reserve months 6. Every saved deal is run against 15%,
20%, and 25% down by default.

### Regression check

`tests/test_screening.py::test_known_amber_case` reproduces the spec's
calibration case: price $250,000, rent $1,800/mo, 15% down, 7.3% rate must
land in **amber**, not green. Tax/insurance/HOA are set to $0 in this
specific test — not an oversight. At these loan terms the P&I payment alone
(~$1,457/mo) plus the default 18% operating-expense reserve (~$324/mo on
$1,800 rent) already consumes all but ~$20/mo of the rent; any realistic
nonzero tax/insurance pushes this exact price/rent pair into **red**
instead. Zeroing them isolates the bare P&I+opex case the spec's check
describes. If this test starts failing, the math drifted — re-derive the
expected numbers by hand before changing the test.

## Investor profile

Seeded from `config.py` (not hardcoded into the engine — the engine takes
`cash_available_for_deals` and financing-scenario fields as parameters).
Edit `config.py` and re-run `seed.py` to update. Current profile: 800
credit, $205K W-2 income, $54K deployable capital (Acorns + cash, buffer
already netted out), Stash ($81.5K) explicitly excluded from spendable
capital and noted as lender-reserves-only. Financing lanes (CUFS credit
union, conventional investment, DSCR, private lender) are recorded as
reference/config, not wired into the rate — the app doesn't yet know which
lane a given deal will use; you pick the assumption rate per scenario.

## Assumptions made (things the spec left ambiguous)

- **No HubSpot integration.** The build spec proposed a manual "push to
  HubSpot" action, but this tool's pipeline is intentionally kept separate
  from any HubSpot account — those are business accounts, not appropriate
  for this personal underwriting tool. `pipeline_stage` (screening / offer
  / under_contract / closed / passed) lives entirely in this app's own
  SQLite database; there's no external CRM sync at all.
- **Regex-vs-LLM field split**: price, sqft, beds, baths, and zip are
  regex-extracted and treated as authoritative over the LLM's guess for
  those same fields (regex wins in the merge). Everything else (address,
  rent estimate, tax/insurance/HOA, condition notes, property type, unit
  count) comes from the LLM pass only.
- **Regex price extraction takes the first dollar amount in the pasted
  text**, on the assumption that listing dumps show list price first/most
  prominently. This can misfire on pages that lead with a fee or tax
  figure — which is exactly why the parsed form is always shown for
  correction before saving.
- **Fulton County lookups (`fulton_county.py`), the bulk candidate scans
  (`candidate_sources.py`), and the Freddie Mac PMMS fetch
  (`freddie_mac.py`) were all built without live network access to
  fultonassessor.org / fultoncountytaxes.org / freddiemac.com** — the
  sandbox this was built in has no egress to those hosts. The request
  plumbing, rate-limiting (one shared 3s-minimum-interval throttle across
  every Fulton County fetch, in `gov_records_http.py`), and error handling
  are solid and tested; the actual HTML-parsing regexes are best-effort
  based on how these sites typically render (qPublic/Schneider Corp
  assessor portals; a plain "Label: value" layout guessed for the
  delinquent-tax and tax-sale lists; Freddie Mac's documented PMMS history
  CSV export) and have **not been verified against the live pages**.
  `candidate_sources.py`'s row-parsing is unit-tested against
  representative fixtures (`tests/test_candidate_sources.py`), which
  confirms the extraction/filtering logic is correct *given* that
  guessed layout — not that the guess matches reality. All of them
  degrade gracefully: single lookups return a `raw_snippet` and an
  `error` field instead of raising; a bulk scan returns whatever
  candidates it found plus a list of per-source error strings rather than
  failing the whole scan; Freddie Mac fetch falls back to
  `config.DEFAULT_RATE_PCT` (7.3%) flagged as `fallback_default`. Expect
  to spend a pass adjusting `DELINQUENT_TAX_LIST_URL`,
  `SHERIFF_TAX_SALE_URL`, and their row regexes once you can hit the real
  pages.
- **No PMI modeling.** The 15/20/25% down comparison holds rate constant
  across all three tiers for an apples-to-apples read on down-payment
  size alone; in reality a <20%-down conventional loan may carry PMI or a
  different rate. Not modeled — a known simplification.
- **No URL routing/deep-linking.** Reloading the page always returns to
  the Add Deal view; there's no `/deals/:id` URL. Fine for a local
  single-operator tool; the SQLite data itself is unaffected by a reload.
- **Model ID**: uses `claude-sonnet-4-6` per the build spec, overridable
  via `DEAL_SCREENER_MODEL` if that ID isn't available on your API account
  by the time you run this.
- **SQLite via stdlib `sqlite3`**, no ORM — a thin hand-rolled data layer
  in `db.py`. Less machinery than SQLAlchemy for a single-table,
  single-user tool; the schema is fully visible in one `CREATE TABLE`.

## Repo layout

```
deal_screener/
  app.py              FastAPI app + all API routes
  config.py           investor profile, defaults, verdict thresholds (edit this)
  models.py           Deal / FinancingScenario / DealResult dataclasses
  db.py               SQLite schema + CRUD
  screening.py         the financial engine (pure functions)
  parsing.py           regex + Anthropic text/vision extraction
  fulton_county.py      Fulton County single-address assessor/tax lookups
  candidate_sources.py   bulk delinquent-tax + tax-sale candidate scans
  gov_records_http.py     shared rate-limited HTTP helper for the above two
  freddie_mac.py            weekly-cached PMMS rate fetch
  seed.py                    init DB + seed investor profile config
  static/index.html           the whole frontend (vanilla JS, no build step)
  tests/test_screening.py      regression + unit tests for the engine
  tests/test_candidate_sources.py  fixture-based tests for the bulk scans
```
