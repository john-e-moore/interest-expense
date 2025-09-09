
# Interest Expense — Forward Projection Engine
## Step-by-Step Work Plan (for Agent Execution)

**Variant:** Aggregated tenor-bucket (SHORT, NB, TIPS) per the approved Mini‑Spec.  
**Operating Mode:** Small steps with artifacts, tests, and a pause gate after each step.

---

## Milestones (High Level)
1. **Scaffold & Contracts** (steps 0–2) — repo layout, FY tagging, config schema.
2. **Macro Functions** (steps 3–5) — GDP callables, rates providers, issuance policy.
3. **Historical Adapters & Calibration** (steps 6–8) — build matrix, fit shares, parameters.
4. **Projection Engine** (steps 9–10) — golden run → full budget identity loop.
5. **Annualization & QA** (steps 11–12) — CY/FY & %GDP with splice visuals + bridge.
6. **Integration & CI** (steps 13–15) — end‑to‑end smoke, CI, formatting, coverage.
7. **Performance & Options** (steps 16–18) — perf pass, cohort-ready hooks, UAT.

---

## Step 0 — Repo Scaffold & Tooling
**Goal:** Create the exact folder structure and dev tooling.
- **Code:** Create folders/files:
  - `src/core/{dates.py,types.py}`, `src/macro/{config.py,gdp.py,rates.py,issuance.py}`
  - `src/calibration/{matrix.py,fit.py}`, `src/engine/{state.py,accrual.py,transitions.py,project.py}`
  - `src/annualize.py`, `src/diagnostics/qa.py`, `scripts/run_forward.py`
  - `tests/` with empty `__init__.py`
- **Tooling:** Add `pyproject.toml` (black, ruff, mypy), `Makefile` with `make test`, `make lint`.
- **Artifacts:** N/A (print created tree).
- **Tests:** N/A (sanity only).
- **Step Report:** repo tree summary.
- **Gate:** repo layout matches spec exactly.

---

## Step 1 — Data Contracts & Config Schema
**Goal:** Lock units and schema before touching math.
- **Code:** `src/macro/config.py`
  - `load_macro_yaml(path) -> MacroConfig` with validation (pydantic or jsonschema).
  - Enforce units (USD millions) & ranges (shares in [0,1], rates finite).
- **Artifacts:** `output/diagnostics/config_echo.json` (normalized config).
- **Tests:** `tests/test_config.py` (required keys, type checks, failure cases).
- **Step Report:** show parsed fields (anchor_date, horizon, GDP anchor, deficit frame).
- **Gate:** schema validation passes; echo file present.

---

## Step 2 — Fiscal Year Tagging Helpers
**Goal:** One canonical FY function used everywhere.
- **Code:** `src/core/dates.py` → `fiscal_year(ts)`; vectorized helpers.
- **Artifacts:** `output/diagnostics/sample_fy_check.csv` (10 example rows).
- **Tests:** `tests/test_dates.py` (Sep 30 vs Oct 1, vectorized map).
- **Step Report:** head/tail of sample mapping.
- **Gate:** tests pass; artifact present.

---

## Step 3 — GDP as Callables (No Monthly Joins)
**Goal:** Annual GDP functions anchored at macro.yaml.
- **Code:** `src/macro/gdp.py` → `build_gdp_function(anchor_date, anchor_gdp, growth_fy) -> GDPModel` with `gdp_cy`, `gdp_fy`.
- **Artifacts:** `output/diagnostics/gdp_check.csv` (year, gdp_fy, gdp_cy).
- **Tests:** `tests/test_gdp.py` (anchor equality, compounding, CY mapping).
- **Step Report:** show anchor FY value, next FY, preview table.
- **Gate:** tests pass; anchor equality holds.

---

## Step 4 — Rate Providers
**Goal:** Deterministic rates for tests and a table-driven provider for runs.
- **Code:** `src/macro/rates.py`
  - `ConstantRatesProvider({...})`
  - `MonthlyCSVRateProvider(path)` that validates full coverage for projection index.
- **Artifacts:** `output/diagnostics/rates_preview.csv` (first/last 24 months).
- **Tests:** `tests/test_rates.py` (coverage, finiteness, columns).
- **Step Report:** range, columns, head/tail.
- **Gate:** tests pass; preview present.

---

## Step 5 — Issuance Policy
**Goal:** Fixed or piecewise shares; sum to 1.
- **Code:** `src/macro/issuance.py`
  - `FixedSharesPolicy(short, nb, tips)`
  - `PiecewiseSharesPolicy([{start, short, nb, tips}, ...])`
  - Note: `OTHER` is an exogenous expense category (from Step 6) and is not part of issuance.
- **Artifacts:** `output/diagnostics/issuance_preview.csv` (first 24 months of horizon).
- **Tests:** `tests/test_issuance.py` (sum≈1, bounds, piecewise behavior).
- **Step Report:** sample shares and validations.
- **Gate:** tests pass; preview present.

---

## Step 6 — Historical Adapters (Build Interest Aggregates from Raw Input)
**Goal:** Build the monthly historical interest expense aggregates directly from the latest `input/IntExp_*` file instead of relying on pre‑aggregated CSVs.
- **Code:** `src/calibration/matrix.py` (adapters):
  - `find_latest_interest_file(pattern="input/IntExp_*") -> Path` (prefer CSV; allow XLSX).
  - `load_interest_raw(path) -> DataFrame` that reads the file and then:
    - Drop rows where `Expense Category Description` ≠ `INTEREST EXPENSE ON PUBLIC ISSUES` (e.g., exclude intra‑government/GAS transfers).
    - Add derived columns from `Record Date`:
      - `Calendar Year` (CY)
      - `Fiscal Year` (FY, using `core.dates.fiscal_year` with FY starting in October)
      - `Month` (1–12)
    - Add `Debt Category` with values in {`SHORT`, `NB`, `TIPS`, `OTHER`} via deterministic mapping from available fields (e.g., security type/class). Anything not clearly mapped to `SHORT`/`NB`/`TIPS` goes to `OTHER`.
    - Normalize units to USD millions and rename `Current Month Expense Amount` → `Interest Expense`.
  - Build aggregates:
    - `monthly_by_category`: group by month (`Record Date` truncated to month start), `Calendar Year`, `Fiscal Year`, `Month`, and `Debt Category`, summing `Interest Expense` → one row per category per month.
    - `fy_totals`: group by `Fiscal Year` only (across all categories), summing `Interest Expense`.
    - `cy_totals`: group by `Calendar Year` only (across all categories), summing `Interest Expense`.
  - Write diagnostics:
    - `output/diagnostics/interest_monthly_by_category.csv`
    - `output/diagnostics/interest_fy_totals.csv`
    - `output/diagnostics/interest_cy_totals.csv`
- **Artifacts:**
  - `output/diagnostics/interest_monthly_by_category.csv` with columns:
    - `Record Date`, `Calendar Year`, `Fiscal Year`, `Month`, `Debt Category` (SHORT, NB, TIPS, OTHER), `Interest Expense`
  - `output/diagnostics/interest_fy_totals.csv` (FY, Interest Expense)
  - `output/diagnostics/interest_cy_totals.csv` (CY, Interest Expense)
- **Tests:** `tests/test_hist_adapters.py`
  - Filtering: no rows remain with `Expense Category Description` ≠ `INTEREST EXPENSE ON PUBLIC ISSUES`.
  - Columns present and types sane; dates monthly and monotonic.
  - `Debt Category` values ⊆ {SHORT, NB, TIPS, OTHER} and monthly sums ≥ 0.
  - FY/CY totals equal the corresponding sums of monthly rows (within tolerance).
- **Step Report:** latest input file path; shapes of three outputs; column lists; head/tail samples; FY/CY example totals.
- **Gate:** tests pass; three artifacts present and non‑empty.

### Decision: `OTHER` Included
- We permanently include `OTHER` for expense items not clearly mapped to `SHORT`/`NB`/`TIPS`.
- Impacts (applied in later steps):
  - Calibration (Step 7): use `y = Interest Expense` excluding `OTHER`; keep `X = (SHORT, NB, TIPS)` unchanged.
  - Engine (Steps 9–10): carry `OTHER` as an exogenous series that contributes to total interest but does not participate in issuance/rates dynamics.
  - Annualization & QA (Steps 11–12): include `OTHER` in totals and visuals; bridge table shows an `OTHER` component.
  - CLI/Docs: note the optional `OTHER` flow.

---

## Step 6b — MSPD Outstanding Adapter (Marketable Stocks by Bucket)
**Goal:** Aggregate marketable outstanding amounts from MSPD into monthly stocks by bucket: `stock_short`, `stock_nb`, `stock_tips` (USD millions). This prepares inputs that some calibration/engine steps may use later.
- **Code:** `src/calibration/stocks.py`
  - `find_latest_mspd_file(pattern="input/MSPD_*.csv") -> Path` (pick newest by mtime)
  - `_bucket_from_mspd_class(s: str) -> {SHORT|NB|TIPS|OTHER}` mapping from MSPD `Security Class 1 Description`:
    - `SHORT`: contains "Bill"
    - `NB`: contains "Note", "Bond", "Floating Rate", or "FRN"
    - `TIPS`: contains "Inflation" or "TIPS"
    - otherwise `OTHER` (ignored downstream here)
  - `build_outstanding_by_bucket_from_mspd(path) -> DataFrame`:
    - Read MSPD "Detail of Marketable Treasury Securities Outstanding" CSV
    - Filter `Security Type Description == "Marketable"`
    - Parse `Record Date` (month‑end), map bucket, sum `Outstanding Amount (in Millions)` by month and bucket
    - Return columns: `Record Date`, `stock_short`, `stock_nb`, `stock_tips` (fill missing buckets with 0)
  - `write_stocks_diagnostic(df, out_path="output/diagnostics/outstanding_by_bucket.csv") -> Path`
- **Artifacts:**
  - `output/diagnostics/outstanding_by_bucket.csv` (month‑end date, stock_short, stock_nb, stock_tips)
- **Tests:** `tests/test_stocks_adapter.py`
  - Excludes non‑marketable rows; columns present; dates monotonic
  - Aggregates match a small synthetic sample; values non‑negative
- **Step Report:** MSPD file path used; shape and date range; head/tail of output
- **Gate:** tests pass; artifact can be produced from the real MSPD file; no NaNs; non‑empty

---

## Step 7 — Calibration Matrix Build
**Goal:** Construct `X (SHORT, NB, TIPS)` and `y` (interest) for last 36–60 months.
- **Code:** `src/calibration/matrix.py` → `build_X(hist_interest_df, hist_stock_df, window_months=48)`.
  - `y` excludes `OTHER` interest (i.e., `y = total_interest − other_interest`).
  - Validate: no NaNs; variance(NB) > 0; aligned dates.
- **Artifacts:** `output/diagnostics/calibration_matrix.csv` (date, y, SHORT, NB, TIPS).
- **Tests:** `tests/test_calibration_matrix.py` (shapes, NaNs, variance thresholds).
- **Step Report:** shapes, variances, head/tail, window used.
- **Gate:** tests pass; matrix written; variance OK.

---

## Step 8 — Constrained Calibration Fit
**Goal:** Fit issuance shares with bounds; write parameters.
- **Code:** `src/calibration/fit.py` → `calibrate_shares(X, y, tip_cap=0.2)` (SLSQP; s≥0; sum=1).
  - Sanity bounds: SHORT∈[0.05,0.60], NB∈[0.05,0.85], TIPS∈[0.00,0.20].
  - Write `output/parameters.json` **only if** bounds pass.
- **Artifacts:** `output/parameters.json` (shares, window, objective); also echo fit diagnostics to `output/diagnostics/calibration_fit.json`.
- **Tests:** `tests/test_calibration_fit.py` (synthetic recovery ±5pp; sum≈1).
- **Step Report:** shares, objective, bounds check, paths.
- **Gate:** tests pass; parameters present; bounds satisfied.

---

## Step 9 — Projection Engine (Golden Skeleton)
**Goal:** Wire a minimal loop with constant rates/shares for 3 months.
- **Code:** `src/engine/{state.py,accrual.py,transitions.py,project.py}`
  - `ProjectionEngine(rates, issuance).run(idx, start_state, deficits_monthly)`
  - `compute_interest` and `update_state` kept **pure**.
  - Carry `OTHER` as an exogenous monthly series added to total interest; it does not affect issuance or stocks.
- **Artifacts:** `output/diagnostics/monthly_trace.parquet` (for 3‑month golden run).
- **Tests:** `tests/test_engine_golden.py` (finite numbers, contiguous dates, shares validity).
- **Step Report:** first/last 3 rows (all columns), totals, artifact path.
- **Gate:** tests pass; trace written.

---

## Step 10 — Projection Engine (Budget Identity & Rollover)
**Goal:** Full monthly budget identity with rollover/decay rules.
- **Code:** Implement:
  - Bills: full monthly rollover.
  - NB/TIPS: constant monthly **decay rate** calibrated to match WAM at anchor (read from historical outstanding by bucket). Persist the chosen decay in `parameters.json`.
  - Interest: existing NB accrues at **anchor average coupon**; new NB uses an **effective current yield** (e.g., r_10y). TIPS add CPI accretion if provided; otherwise keep zero to start.
  - `OTHER`: passed through as an exogenous add-on to interest; does not roll or accrue within the engine.
- **Artifacts:** `output/diagnostics/monthly_trace.parquet` (full horizon).
- **Tests:** extend `tests/test_engine_golden.py` with a 12‑month scenario; add `tests/test_engine_identity.py` that checks:
  - `GFN_t = deficit_t + interest_t + redemptions_t` (within tolerance).
  - Stocks update: `B_{t+1} = B_t - redemptions + new` by bucket.
- **Step Report:** coverage stats, monthly means, example months.
- **Gate:** tests pass; identity holds within tolerance.

---

## Step 11 — Annualization & % of GDP
**Goal:** Produce CY/FY levels and %GDP using GDP callables.
- **Code:** `src/annualize.py` → `annualize(monthly_df, gdp_model)`
  - Return CY/FY levels and %GDP; write annual CSVs.
- **Artifacts:** 
  - `output/calendar_year/spreadsheets/annual.csv`
  - `output/fiscal_year/spreadsheets/annual.csv`
- **Tests:** `tests/test_annualize.py` (CY uses gdp_cy, FY uses gdp_fy; values finite; year monotonic).
- **Step Report:** two sample years (levels + %GDP) with denominators shown.
- **Gate:** tests pass; CSVs present.
  - Include `OTHER` in totals; optionally break out by category if diagnostics enabled.

---

## Step 12 — Diagnostics & QA Visuals + Bridge
**Goal:** Human‑checkable continuity around the splice.
- **Code:** `src/diagnostics/qa.py`
  - Plots: (1) monthly interest 2018–2026, (2) effective rate `interest/avg_outstanding`, (3) annual CY/FY w/ %GDP.
  - `bridge_table.csv`: FY(anchorFY)→FY(anchorFY+1) decomposition into **stock**, **rate**, **mix/term**, **TIPS accretion**, **OTHER**.
- **Artifacts:** 
  - `output/calendar_year/visualizations/*.png`
  - `output/fiscal_year/visualizations/*.png`
  - `output/diagnostics/bridge_table.csv`
- **Tests:** `tests/test_qa_presence.py` (files exist; simple numeric sanity on bridge components).
- **Step Report:** file paths + quick stats; bridge snippet.
- **Gate:** artifacts present; tests pass.

---

## Step 13 — End‑to‑End Smoke (Golden Slice)
**Goal:** CI‑friendly fast run.
- **Code:** `scripts/run_forward.py` orchestrates: load config → build providers → run engine → annualize → QA.
- **Artifacts:** All standard outputs for **12 months only** when `--golden` flag is used.
- **Tests:** `tests/test_integration_smoke.py` (runs golden; asserts presence & key numbers finite).
- **Step Report:** run summary, paths.
- **Gate:** passes locally in <10s.

---

## Step 14 — CLI & Docs
**Goal:** One‑command driver and README.
- **Code:** `scripts/run_forward.py` CLI flags:
  - `--config input/macro.yaml`
  - `--golden` (12‑month slice)
  - `--full` (horizon from config)
  - `--diagnostics` (force artifact writes)
- **Artifacts:** `README.md` with usage, expected inputs, outputs.
- **Tests:** `tests/test_cli.py` (argparse layer, dry‑run).
- **Step Report:** CLI help text.
- **Gate:** docs complete; CLI usable.

---

## Step 15 — CI & Quality Gates
**Goal:** Keep it tidy and reproducible.
- **Code:** GitHub Actions (or preferred CI): run `ruff`, `black --check`, `mypy`, and `pytest -q` on push/PR.
- **Artifacts:** CI badge in README (optional).
- **Tests:** CI green.
- **Step Report:** CI summary.
- **Gate:** CI passes on main.

---

## Step 16 — Performance Pass
**Goal:** Ensure full 30‑year run is snappy.
- **Code:** Vectorize inner loops where safe; avoid per‑row Python in hotspots.
- **Artifacts:** `output/diagnostics/perf_profile.json` (timings).
- **Tests:** time‑boxed test for full horizon under a threshold (mark as slow).
- **Step Report:** timing table.
- **Gate:** meets target (< a few seconds on dev box, adjust as needed).

---

## Step 17 — Cohort‑Ready Hooks (Optional)
**Goal:** Prepare for tenor cohorts without refactor churn.
- **Code:** Add abstractions so NB bucket logic can be swapped for cohorts while preserving ports/tests.
- **Artifacts:** N/A (design notes in code).
- **Tests:** back‑compat; golden run unchanged.
- **Step Report:** notes on extension points.
- **Gate:** N/A (optional).

---

## Step 18 — User Acceptance Tests (UAT) Checklist
**Goal:** Final human checks with your data.
- **Checklist:**
  - [ ] GDP anchor equals macro.yaml FY anchor.
  - [ ] CY/FY denominators printed alongside numerators for 2 sample years.
  - [ ] Splice continuity: monthly interest near anchor looks smooth (explainable by macros).
  - [ ] Bridge table attribution sums to ΔInterest within rounding.
  - [ ] Calibration matrix has no NaNs; NB column variance > 0.
  - [ ] Parameters within bounds and documented.
  - [ ] `monthly_trace.parquet` row has all expected fields.
  - [ ] CLI full run finishes and writes all outputs.
- **Artifacts:** mark decisions in `output/diagnostics/uat_checklist.json`.
- **Gate:** all checked.

---

## Step Report — Required Template (Print after every step)
```
STEP: <name>
Artifacts:
- <path 1>
- <path 2>
Shapes / ranges:
- df_name: shape=(r,c), date_min=..., date_max=...
Head/Tail (key tables):
<df.head(3)>
...
<df.tail(3)>
Key scalars:
- anchor_month=..., gdp_fy_anchor=..., shares=(..., ..., ...)
Tests: PASSED=<n>, FAILED=<m>
NEXT: (waiting for user approval)
```

---

## Risk Log & Mitigations
- **GDP anchoring errors** → Add explicit assert: `gdp_fy(FY(anchor)) == anchor_gdp`.
- **CY/FY mismatches** → Single `fiscal_year()`; unit tests + annualize tests enforce frames.
- **Degenerate calibration** → Matrix artifact + variance assert; constrained fit; bounds enforcement.
- **Projection identity drift** → Budget-identity unit test and per‑month GFN check.
- **Overfitting shares** → Use 36–60 months; keep model simple; log fit residuals.
- **Units drift** → Normalize at load; echo units in Step Reports.

---

## Commands (suggested)
```
make lint
make test
python scripts/run_forward.py --config input/macro.yaml --golden
python scripts/run_forward.py --config input/macro.yaml --full --diagnostics
```

---

**Definition of Done (Project):** All gates passed through Step 15, UAT checklist green, and a full‑horizon run writes annual CSVs and QA visuals with sensible splice behavior.
