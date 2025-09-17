## Revenue & Primary Outlays Split (as % of GDP) — feature/revenue-outlays

### Goals
- Replace the `deficits` block with a new `budget` block in `macro.yaml` containing: `frame`, `annual_revenue_pct_gdp`, `annual_outlays_pct_gdp`, and `additional_revenue`.
- Add explicit revenue and primary outlays paths as percent of GDP (FY or CY) and derive primary deficit as: primary_deficit = primary_outlays − revenue.
- Keep the existing `additional_revenue` (tariffs/offset) logic and diagnostics nested under `budget`; apply it after deriving the base primary deficit from components.
- Expand diagnostics: include revenue, primary outlays, additional revenue, and primary deficit in both USD and % of GDP, at monthly (existing) and annual levels.
- Do not implement GDP–revenue elasticity now; note as a future enhancement in this branch.

### Scope
- Config schema updates in `input/macro.yaml` and loader changes in `src/macro/config.py`.
- Builders in `src/macro/deficits.py` (or a new helper module) to:
  - Build monthly revenue and primary outlays series (USD mn/month) from FY/CY %GDP maps using the `GDPModel`.
  - Derive the base primary deficit series as (outlays − revenue).
  - Integrate the existing `additional_revenue` series (if enabled) to compute an adjusted primary deficit for the engine.
- Diagnostics:
  - Expand the existing `deficits_preview.csv` monthly diagnostic to include new columns.
  - Add a new annual diagnostic `deficits_preview_annual.csv` aggregated to FY and/or CY depending on `deficits.frame`.
- Tests for config parsing, series construction, diagnostics, and backward compatibility.

---

### Configuration Schema (input/macro.yaml)

- Introduce a new `budget` block replacing the old `deficits` block. It governs the frame and contains the two component share maps and the existing `additional_revenue` sub-block.

```yaml
budget:
  frame: FY  # or CY (governs all budget-share maps below)

  # Percent of GDP (not decimal), keyed by FY/CY year
  annual_revenue_pct_gdp:
    2026: 18.0
    2027: 18.1

  annual_outlays_pct_gdp:
    2026: 21.0
    2027: 20.9

  # Existing: additional revenue (tariffs/offset), unchanged semantics
  additional_revenue:
    enabled: true
    mode: level        # "pct_gdp" | "level"
    anchor_year: 2025
    anchor_amount: 300000
    index: PCE         # or CPI or none
```

Rules:
- Values are percentages, not decimals.
- Year keys are interpreted in the `budget.frame` basis: FY if `FY`, otherwise CY.
- Coverage: forward-fill the last provided value through the projection horizon; backfill to the anchor year if needed.
- Validity: all provided shares must be finite; enforce nonnegative for `annual_revenue_pct_gdp` and `annual_outlays_pct_gdp` (warn or error on negatives — see Sanity Checks). `additional_revenue` may be negative to represent tax cuts.
- Requirement: both `annual_revenue_pct_gdp` and `annual_outlays_pct_gdp` must be provided. Omission of either is an error.

Loader changes (src/macro/config.py):
- Replace `deficits` parsing with a new `budget` section:
  - `budget_frame: FiscalFrame`
  - `budget_annual_revenue_pct_gdp: Dict[int, float]`
  - `budget_annual_outlays_pct_gdp: Dict[int, float]`
  - `additional_revenue_*` fields parsed from `budget.additional_revenue` (schema unchanged: mode, maps/levels or anchor/index fields, enabled flag).
- Validation mirrors existing parsing: normalize to `{int(year): float(percent)}` and ensure values are finite.

---

### Series Construction

Prereqs:
- Build `GDPModel` as done today from `gdp.anchor_value_usd_millions` and `gdp.annual_fy_growth_rate`.

New helpers (e.g., `src/macro/budget.py` or extend `src/macro/deficits.py`):
- `build_budget_component_series(cfg: MacroConfig, gdp_model: GDPModel, index: pd.DatetimeIndex) -> tuple[pd.Series, pd.Series, pd.DataFrame]`
  - Inputs: config, GDP model, and projection index (monthly).
  - Outputs: `(revenue_month_usd_mn, primary_outlays_month_usd_mn, preview_df_components)` where each series is monthly USD mn, aligned to `index`, and preview lists per-month rows for each component (see Diagnostics for columns).
  - Logic: compute annual USD = (pct/100) × GDP_y using `budget_annual_revenue_pct_gdp` and `budget_annual_outlays_pct_gdp`, allocate evenly to months in year; both maps are required.

Adjust existing builder wiring in `scripts/run_forward.py`:
- Compute `primary_deficit_base_month_usd_mn = primary_outlays_month_usd_mn − revenue_month_usd_mn`.
- Compute `additional_revenue_month_usd_mn` using existing helper when enabled.
- Compute `primary_deficit_adj_month_usd_mn = primary_deficit_base_month_usd_mn − additional_revenue_month_usd_mn` (unchanged sign convention).
- Pass `primary_deficit_adj_month_usd_mn` to the engine as today.

---

### Diagnostics

Monthly (expand existing `deficits_preview.csv`):
- One row per projection month with at least these columns:
  - `date`, `frame` (FY|CY), `year_key` (FY or CY year as int), `gdp` (USD mn)
  - Revenue: `revenue_pct_gdp`, `revenue_annual_usd_mn`, `revenue_month_usd_mn`
  - Primary Outlays: `primary_outlays_pct_gdp`, `primary_outlays_annual_usd_mn`, `primary_outlays_month_usd_mn`
  - Additional Revenue: `additional_revenue_mode`, `additional_revenue_input_value`, `additional_revenue_annual_usd_mn`, `additional_revenue_month_usd_mn`
  - Base Primary Deficit (before additional revenue): `primary_deficit_base_pct_gdp`, `primary_deficit_base_annual_usd_mn`, `primary_deficit_base_month_usd_mn`
  - Adjusted Primary Deficit (after additional revenue): `primary_deficit_adj_pct_gdp`, `primary_deficit_adj_annual_usd_mn`, `primary_deficit_adj_month_usd_mn`

Notes:
- `*_pct_gdp` fields are annual shares aligned to the `year_key` of each row.

Annual (new `deficits_preview_annual.csv`):
- Aggregation by `year_key` in the configured frame (`budget.frame`); include the same categories as monthly but at annual level:
  - `year_key`, `frame`, `gdp_annual_usd_mn`
  - `revenue_pct_gdp`, `revenue_annual_usd_mn`
  - `primary_outlays_pct_gdp`, `primary_outlays_annual_usd_mn`
  - `additional_revenue_annual_usd_mn`
  - `primary_deficit_base_pct_gdp`, `primary_deficit_base_annual_usd_mn`
  - `primary_deficit_adj_pct_gdp`, `primary_deficit_adj_annual_usd_mn`

File locations:
- Monthly: `output/<run_id>/diagnostics/deficits_preview.csv` (same path, expanded schema)
- Annual:  `output/<run_id>/diagnostics/deficits_preview_annual.csv`

---

### Sanity Checks & Guardrails
- Range checks (warn-level):
  - `revenue_pct_gdp` not in [10, 25] → warn
  - `primary_outlays_pct_gdp` not in [15, 30] → warn
  - `|primary_deficit_adj_pct_gdp|` > 10 → warn
- Consistency checks:
  - For full-year coverage in the monthly index, sum of `*_month_usd_mn` over months ≈ `*_annual_usd_mn` (tolerance: 1e-6 relative or 0.5 USD mn absolute per year).
  - `primary_deficit_base_annual_usd_mn ≈ primary_outlays_annual_usd_mn − revenue_annual_usd_mn` (within tolerance) when components are present.
  - Adjusted deficit identity: `primary_deficit_adj_annual_usd_mn ≈ primary_deficit_base_annual_usd_mn − additional_revenue_annual_usd_mn`.
- Input validation:
  - Reject negative values in `annual_revenue_pct_gdp` and `annual_outlays_pct_gdp` (error). Allow negative `additional_revenue` (tax cuts) as before.

---

### Tests
Unit tests (new/updated under `tests/`):
- Config parsing:
  - Parses `budget.frame`, `budget.annual_revenue_pct_gdp`, and `budget.annual_outlays_pct_gdp` with correct typing and frame adherence.
  - Missing either share map raises a clear error.
- Series construction:
  - Given simple GDP path and known shares, monthly and annual USD levels match expected values.
  - Base deficit equals outlays − revenue.
- Additional revenue integration:
  - When enabled, adjusted deficit equals base deficit minus additional revenue (monthly and annual).
  - When disabled, adjusted == base.
- Diagnostics:
  - Monthly CSV columns exactly match the expanded schema.
  - Annual CSV aggregates match sums of monthly and %GDP values align with GDP for that year.
- Sanity checks:
  - Range and identity checks trigger warnings as expected on contrived inputs.

---

### Engine Wiring (unchanged budget identity)
- The engine continues to consume a single monthly `primary_deficit` series (USD mn/month).
- We compute and pass `primary_deficit_adj_month_usd_mn` as today; the only change is how the base series is derived when components are provided.

---

### Backward Compatibility & Migration
- Breaking change to `input/macro.yaml`: the `deficits` block is replaced by `budget`.
- Migration:
  - Move `deficits.frame` → `budget.frame`.
  - Remove `deficits.annual_pct_gdp` (net). Provide both `budget.annual_revenue_pct_gdp` and `budget.annual_outlays_pct_gdp`.
  - Move `deficits.additional_revenue` → `budget.additional_revenue` (schema unchanged).
- Diagnostics remain at the same filenames but with expanded columns.

---

### Non-goals (for this step)
- Do not implement GDP–revenue elasticity or automatic stabilizers in this step. A future spec may add an optional `revenue_elasticity` block keyed off GDP growth deviations.
- Do not change the sign conventions or the `additional_revenue` API.

---

### Implementation Notes
- Prefer reusing the existing FY/CY handling (`fiscal_year`) and GDP getters (`gdp_fy`, `gdp_cy`).
- Keep monthly allocation flat within a year for now (consistent with existing deficit handling).
- Add helper writers `write_deficits_preview_annual(...)` and extend the existing monthly writer.
- Ensure logs clearly indicate budget frame and that component-driven primary deficit is in use.


