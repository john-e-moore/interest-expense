## Feature spec: Macro enhancements (`feature/macro`)

### Objectives
- **Enable GDP growth path**: Allow yearly GDP growth rates in `input/macro.yaml` and propagate into the model so GDP is no longer flat.
- **Compute historical effective rates (monthly)**: Derive monthly effective rates by bucket from historical interest and outstanding tables; persist diagnostics.
- **Aggregate and visualize annual effective rates**: Produce annual averages for both fiscal year (FY) and calendar year (CY) and visualize.
- **Combine historical and forward effective rates**: Plot a single chart with a clear annotation for projection start.
- **Introduce variable annual rate inputs**: Add annual variable rate series for `SHORT`, `NB`, and `TIPS` in `input/macro.yaml` and use them in forward projections.

### Scope
- Updates to YAML schema and config loading.
- Data transforms for effective rate derivation.
- Generation of diagnostics CSV(s) and visualization(s).
- Integration into existing run output structure: `output/<run_id>/...`.

### YAML schema changes (`input/macro.yaml`)
1) GDP growth rate inputs
   - New key under `gdp`:
     - `annual_fy_growth_rate`: mapping of FY year (YYYY) to percent growth (float), e.g. `{2025: 4.0, 2026: 3.6}`.
   - Example:
```yaml
gdp:
  # Percent growth, FY basis
  annual_fy_growth_rate:
    2025: 4.0
    2026: 3.6
    2027: 3.2
```

2) Variable rate inputs for `SHORT`, `NB`, `TIPS` (FY basis)
   - New top-level key (or under an existing `rates:` block if present):
```yaml
variable_rates_annual:
  # Percent, FY basis
  SHORT:
    2025: 4.25
    2026: 3.75
  NB:
    2025: 4.60
    2026: 4.10
  TIPS:
    2025: 2.10
    2026: 2.00
```
   - Values are in percent (annualized). Years are fiscal years (FY); no calendar-year conversion is required.

### Model and loader updates
- Extend config loader to parse the above keys into structured objects with explicit types.
- In the macro model, evolve GDP using `annual_fy_growth_rate` on an FY basis:
  - For each FY t with growth g_t, apply multiplicative growth to the GDP level path for that FY window.
  - Define behavior for missing years: default to the latest specified growth rate, or `0.0` if none present; log a warning on fallback.
- In the forward rate projection logic (FY basis), read `variable_rates_annual` per category and apply appropriately to `SHORT`, `NB`, `TIPS` instruments/segments. Define interpolation between FY annual points (step, linear, or piecewise-constant); default to piecewise-constant unless overridden.

### Historical effective rate computation (monthly)
Inputs
- `output/<run_id>/diagnostics/outstanding_by_bucket_scaled.csv`
- `output/<run_id>/diagnostics/interest_monthly_by_category.csv`

Transform
- Melt/pivot `outstanding_by_bucket_scaled` to one row per `date` (or `year`+`month`) per `security_bucket` with `outstanding_amount`.
- Inner-join to `interest_monthly_by_category` on `year` and `month` (and on the bucket/category key when applicable). Ensure consistent bucket/category naming or map explicitly.
- Compute `effective_rate_monthly = interest_expense / outstanding_amount`.

Output
- Write monthly table to: `output/<run_id>/diagnostics/effective_rate_monthly_by_bucket.csv` with at minimum:
  - `date` (ISO or `year`+`month`), `security_bucket`, `outstanding_amount`, `interest_expense`, `effective_rate_monthly`.
- Guardrails:
  - Drop or flag rows where `outstanding_amount <= 0`; avoid division by zero.
  - Clamp obviously erroneous rates (e.g., negative or > 100% monthly) by flagging and excluding from aggregates; report counts in a small QA summary.

### Annual averaging and visualizations
- Compute two aggregates from the monthly table:
  1) FY average effective rate per bucket and overall (weighted by monthly outstanding or simple mean—prefer weighted; specify in column `effective_rate_fy_weighted`).
  2) CY average effective rate per bucket and overall (`effective_rate_cy_weighted`).
- Visualize historical annual averages:
  - FY chart path: `output/<run_id>/fiscal_year/visualizations/effective_rate.png`.
  - CY chart path: `output/<run_id>/calendar_year/visualizations/effective_rate.png`.
  - Include legend, y-axis in percent, and data labels for last value per series (optional).

### Combine historical and forward effective rates
- Produce a single chart `output/<run_id>/visualizations/effective_rate_historical_forward.png`:
  - Historical series from computed monthly/annual history.
  - Forward series from projection using `variable_rates_annual` and the model.
  - Annotate projection start with a vertical line and label (e.g., "Projection start: YYYY-MM").
  - Provide a legend distinguishing historical vs forward.

### Implementation tasks
1) Extend YAML schema and loader to support `gdp.annual_fy_growth_rate` and `variable_rates_annual` (FY basis).
2) Update macro model to build GDP path using FY growth rates and to consume variable annual rates for `SHORT`, `NB`, `TIPS` in projections on an FY basis.
3) Build effective-rate computation pipeline from diagnostics inputs; write monthly CSV.
4) Add FY and CY annual aggregations; write intermediate CSVs as needed.
5) Create FY and CY historical charts.
6) Combine historical and forward effective rates into a single chart with annotation.
7) Wire outputs into the run flow so artifacts appear under the current `<run_id>`.

### Acceptance criteria
- `input/macro.yaml` changes are parsed without errors; missing years follow documented fallback behavior with warnings.
- `output/<run_id>/diagnostics/effective_rate_monthly_by_bucket.csv` exists and contains non-empty data with valid `effective_rate_monthly` for rows where `outstanding_amount > 0`.
- FY and CY annual average CSVs or in-memory frames are produced; FY and CY charts exist at specified paths.
- Combined historical+forward effective rate chart exists with a clearly marked projection start.
- GDP no longer flat when growth rates are provided; forward rates reflect FY-basis `variable_rates_annual`.

### Testing
- Unit tests
  - YAML parsing for `gdp.annual_fy_growth_rate` and `variable_rates_annual` (types, defaults, missing years).
  - GDP path construction given a small growth map (verify FY aggregation windows and compounding).
  - Effective rate calculation given small synthetic inputs (correct joins, division, zero-handling).
  - Annual aggregation correctness (weighted vs unweighted—test both if both supported).
- Integration tests
  - End-to-end run on a small fixture set to ensure all artifacts are written with expected columns and non-empty content.
  - Chart generation smoke tests (files created, basic dimensions > 0 bytes).

### Sanity checks (runtime QA)
- Interest expense sanity: For each month, `interest_expense` should be within plausible bounds relative to `outstanding_amount` and known rates; flag if `effective_rate_monthly` < 0 or > 10% monthly.
- Continuity: Historical-to-forward transition should avoid discontinuities > X bps (configurable threshold, e.g., 100 bps) unless justified; log if exceeded.
- GDP path: With positive growth inputs, FY GDP should be non-decreasing; log any violation.
- Coverage: Report counts of dropped/flagged rows (zero/negative outstanding, extreme rates).

### Logging and diagnostics
- Add concise logs for:
  - Parsed growth and variable rate years and any defaults applied.
  - Join cardinalities before/after; number of rows filtered.
  - Output file paths written.

### Performance and reliability
- Operate comfortably on datasets up to current diagnostics sizes; aim for transforms < a few seconds per run.
- Deterministic outputs given the same inputs; seed any randomized behavior (if any).

### Risks and edge cases
- Mismatch between bucket names in outstanding vs interest tables; specify or implement a mapping.
- Sparse or missing years in `variable_rates_annual`; define interpolation and defaulting explicitly.
- Division-by-zero and tiny denominators producing extreme rates; implement filters and QA logs.

### Deliverables
- Updated loader/model code.
- New diagnostics CSV: `effective_rate_monthly_by_bucket.csv` under `<run_id>/diagnostics`.
- FY and CY charts under their respective folders, plus combined historical+forward chart.
- Unit and integration tests; all tests pass; sanity checks yield no critical flags under normal inputs.


