## Work plan — Revenue & Primary Outlays split (budget block)

### Milestones
1) YAML schema + loader: replace `deficits` with `budget` (frame, revenue/outlays shares, additional_revenue)
2) Builders: monthly component series and primary deficit derivation
3) Wiring: integrate into forward run and engine input
4) Diagnostics: expand monthly preview; add annual preview
5) Sanity checks & logging
6) Tests: unit + integration
7) Migration docs and example config update
8) FY & CY overview spreadsheets (budget + interest summary)

### M1 — Schema + loader (src/macro/config.py)
- Replace `deficits` section with `budget`:
  - `budget.frame: FY|CY`
  - `budget.annual_revenue_pct_gdp: {year: percent}` (percent, not decimal)
  - `budget.annual_outlays_pct_gdp: {year: percent}` (percent, not decimal)
  - `budget.additional_revenue: { enabled, mode, anchor/index or maps }` (unchanged semantics)
- Parse into `MacroConfig` with new fields:
  - `budget_frame: FiscalFrame`
  - `budget_annual_revenue_pct_gdp: Dict[int, float]`
  - `budget_annual_outlays_pct_gdp: Dict[int, float]`
  - `additional_revenue_*` fields (same as existing design; source = `budget.additional_revenue`)
- Remove acceptance of legacy `deficits.annual_pct_gdp` (error if present).
- Provide a read-only alias property `deficits_frame` returning `budget_frame` to minimize refactors in existing call sites, then update call sites in this feature.
- Update `write_config_echo` to include the new fields.

Acceptance criteria:
- Loader raises on missing `budget` or missing either of the two share maps.
- Example `macro.yaml` with new `budget` parses successfully; config echo contains `budget_frame` and both share maps.

### M2 — Builders (src/macro/budget.py)
- New helper:
  - `build_budget_component_series(cfg: MacroConfig, gdp_model: GDPModel, index: pd.DatetimeIndex) -> tuple[pd.Series, pd.Series, pd.DataFrame]`
    - Build monthly USD mn for revenue and primary_outlays from `%GDP × GDP_y / 12` (FY or CY based on `budget_frame`).
    - Return component preview with columns: `date, frame, year_key, revenue_pct_gdp, primary_outlays_pct_gdp, gdp, revenue_annual_usd_mn, primary_outlays_annual_usd_mn, revenue_month_usd_mn, primary_outlays_month_usd_mn`.
- Compute base primary deficit series: `primary_deficit_base = primary_outlays_month − revenue_month`.
- Reuse existing additional revenue builder to get `additional_revenue_month` (uses parsed `additional_revenue_*`).

Acceptance criteria:
- Given simple GDP and shares, outputs match hand-calculated monthly and annual amounts.

### M3 — Wiring (scripts/run_forward.py)
- Build `GDPModel` as today.
- Call `build_budget_component_series(...)` to get components and preview.
- Compute `primary_deficit_base_month_usd_mn` and `primary_deficit_adj_month_usd_mn = base − additional_revenue_month` (if enabled).
- Pass `primary_deficit_adj_month_usd_mn` into the engine (unchanged budget identity).
- Remove calls to legacy `build_primary_deficit_series`; keep the function in place but unused (temporary) or mark for removal in a follow-up.

Acceptance criteria:
- Runs complete without referencing `deficits.annual_pct_gdp`.
- Engine receives adjusted primary deficit identical in units and index to before.

### M4 — Diagnostics
- Expand monthly `deficits_preview.csv` (same filename, schema expanded):
  - Columns: `date, frame, year_key, gdp, revenue_pct_gdp, revenue_annual_usd_mn, revenue_month_usd_mn, primary_outlays_pct_gdp, primary_outlays_annual_usd_mn, primary_outlays_month_usd_mn, additional_revenue_mode, additional_revenue_input_value, additional_revenue_annual_usd_mn, additional_revenue_month_usd_mn, primary_deficit_base_pct_gdp, primary_deficit_base_annual_usd_mn, primary_deficit_base_month_usd_mn, primary_deficit_adj_pct_gdp, primary_deficit_adj_annual_usd_mn, primary_deficit_adj_month_usd_mn`.
- New annual `deficits_preview_annual.csv`:
  - Group by `year_key` in `budget.frame`; aggregate to annual USD and include annual %GDP shares.
- Implement writers:
  - `write_deficits_preview_monthly(...)` (extend existing writer)
  - `write_deficits_preview_annual(...)` (new)

Acceptance criteria:
- CSVs written to `output/<run_id>/diagnostics/` with complete columns.
- Annual CSV aggregates reconcile to monthly sums within tolerance.

### M5 — Sanity checks & logging
- Warn if `revenue_pct_gdp` ∉ [10, 25] or `primary_outlays_pct_gdp` ∉ [15, 30].
- Warn if `|primary_deficit_adj_pct_gdp|` > 10.
- Check identities per year (within tolerance):
  - `base ≈ outlays − revenue`
  - `adjusted ≈ base − additional_revenue`
- Log whether `budget.frame` is FY or CY and that components mode is active.

Acceptance criteria:
- Deliberately extreme inputs produce warnings; normal inputs are quiet.

### M6 — Tests (tests/)
- Loader tests:
  - Parses `budget.frame`, `budget.annual_revenue_pct_gdp`, `budget.annual_outlays_pct_gdp`, and `budget.additional_revenue`.
  - Errors when either share map is missing.
- Builder tests:
  - Component monthly series and previews match expected values.
  - Base and adjusted primary deficits satisfy identities.
- Diagnostics tests:
  - Monthly CSV has full set of columns; types are as expected.
  - Annual CSV reconciles to monthly sums and %GDP aligns with GDP.
- Integration test:
  - End-to-end run writes both diagnostics; engine receives adjusted deficit with correct length and NaN-free.

Acceptance criteria:
- All new tests pass locally and in CI.

### M7 — Migration & docs
- Update `README.md` to reflect `budget` schema; remove references to `deficits.annual_pct_gdp`.
- Update example `input/macro.yaml` in repo to `budget`.
- Note breaking change and migration steps.

Acceptance criteria:
- README and example config are in sync with loader behavior; running the example works out of the box.

### M8 — FY & CY overview spreadsheets (budget + interest summary)
- Goal: Write `overview.csv` under both `fiscal_year/spreadsheets/` and `calendar_year/spreadsheets/` for forward projection years only.
- Columns (in order):
  - `year` (fiscal or calendar)
  - `gdp_usd_bn`
  - `gdp_growth_pct`
  - `revenue_usd_bn`
  - `revenue_pct_gdp`
  - `primary_outlays_usd_bn`
  - `primary_outlays_pct_gdp`
  - `primary_deficit_usd_bn` (adjusted = outlays − revenue − additional_revenue)
  - `primary_deficit_pct_gdp`
  - `additional_revenue_usd_bn`
  - `additional_revenue_pct_gdp`
  - `interest_expense_usd_bn`
  - `interest_expense_pct_gdp`
  - `effective_interest_rate_pct`
  - `pce_inflation_pct`
- Implementation:
  - Compute annual nominal GDP for each frame and `y/y` growth using the same frame mapping as diagnostics.
  - Aggregate monthly `revenue_month_usd_mn`, `primary_outlays_month_usd_mn`, and `additional_revenue_month_usd_mn` to annual USD; convert to billions by dividing by 1_000.
  - Compute adjusted primary deficit: `primary_outlays_annual − revenue_annual − additional_revenue_annual`. Also compute %GDP columns as `(usd / gdp) × 100`.
  - Pull annual interest expense from engine outputs (annualized) and compute %GDP.
  - Compute effective interest rate as `interest_expense_annual / average(debt_start_of_year, debt_end_of_year)`; reuse the helper used for `historical_effective_rates.csv` to ensure consistency.
  - Pull PCE inflation as `y/y` percent from the PCE index aligned to the frame (FY or CY) consistent with diagnostics.
  - Restrict rows to forward projection years; exclude any historical/calibration years.
  - Writers:
    - `write_budget_overview_annual(frame: FiscalFrame, ...) -> None` that emits the CSV for a given frame.
    - Hook this writer from `scripts/run_forward.py` after existing annual spreadsheets are written for each frame.
  - File names:
    - `output/<run_id>/fiscal_year/spreadsheets/overview.csv`
    - `output/<run_id>/calendar_year/spreadsheets/overview.csv`
- Formatting & units:
  - USD in billions rounded to 1 decimal; percentages rounded to 2 decimals.
  - No missing values; fill zeros for `additional_revenue_*` when the feature is disabled.
- Acceptance criteria:
  - Both CSVs exist with the exact columns above and only projection years.
  - `%GDP` columns equal `USD / GDP` within tolerance after rounding; identity holds: `primary_outlays = revenue + additional_revenue + primary_deficit`.
  - Effective interest rate matches diagnostics series within 5 bps for overlapping years.
  - PCE inflation aligns with the inflation preview for the same frame.

### Sequencing & effort
1) M1 (loader) → 2) M2 (builders) → 3) M3 (wiring) → 4) M4 (diagnostics) → 5) M5 (sanity) → 6) M6 (tests) → 7) M7 (docs) → 8) M8 (overview spreadsheets)

### Risks & mitigations
- Downstream code expecting `deficits_frame`: introduce a temporary alias property and refactor call sites in this feature.
- CSV schema consumers: expanding columns could break parsers; document and version outputs in the run directory header metadata if needed.
- FY vs CY aggregation subtleties: ensure `year_key` mapping uses `fiscal_year(...)` for FY and direct `.year` for CY consistently across monthly and annual.

### Definition of Done
- New `budget` schema is accepted by loader; runs complete; diagnostics (monthly and annual) written; FY & CY overview spreadsheets written; sanity checks active; tests pass; docs updated.


