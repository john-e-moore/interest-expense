## Work plan: Macro enhancements (feature/macro)

### Milestones
1) YAML schema + loader updates (FY basis)
2) Macro model updates (GDP path + forward variable rates)
3) Historical effective-rate pipeline (monthly) and CSV output
4) Annual aggregations (FY, CY) and historical charts
5) Combined historical + forward effective-rate chart
6) Wire into run flow and outputs
7) Tests (unit + integration) and sanity checks

### Detailed tasks and sequencing

M1) YAML schema + loader updates
- Add `gdp.annual_fy_growth_rate` to `input/macro.yaml` (FY-based percent growth).
- Add `variable_rates_annual` (FY-based percent) for `SHORT`, `NB`, `TIPS`.
- Extend config loader to parse into typed structures; validate keys are integers (FY years) and values are floats.
- Behavior for missing FY years: default to last specified or 0.0 (growth) with warning; for variable rates, default to last specified with warning.
- Deliverables: parsed config objects accessible to the macro model; logs for parsed years and defaults.

M2) Macro model updates
- GDP evolution: construct GDP level path using `annual_fy_growth_rate` per FY window.
- Forward rates: read `variable_rates_annual` for `SHORT`, `NB`, `TIPS`; apply piecewise-constant interpolation across FY periods by default.
- Define clear interfaces for obtaining monthly forward effective rates from annual FY inputs.
- Deliverables: GDP no longer flat given positive growth; forward projections reflect FY variable rates.

M3) Historical effective-rate pipeline (monthly)
- Inputs: `output/<run_id>/diagnostics/outstanding_by_bucket_scaled.csv`, `output/<run_id>/diagnostics/interest_monthly_by_category.csv`.
- Transform:
  - Reshape outstanding to one row per date (or year+month) per bucket with `outstanding_amount`.
  - Inner-join to interest on year+month and bucket/category (map names if needed).
  - Compute `effective_rate_monthly = interest_expense / outstanding_amount`.
- Guardrails: drop or flag nonpositive denominators; flag extreme rates (< 0 or > 0.10 monthly) and exclude from aggregates; log counts.
- Output: `output/<run_id>/diagnostics/effective_rate_monthly_by_bucket.csv` with required columns.

M4) Annual aggregations + historical charts
- Compute FY and CY weighted averages (by monthly outstanding) per bucket and overall.
- Outputs:
  - FY chart: `output/<run_id>/fiscal_year/visualizations/effective_rate.png`.
  - CY chart: `output/<run_id>/calendar_year/visualizations/effective_rate.png`.
- Chart specs: percent y-axis, legend, optional last-value labels.

M5) Combined historical + forward chart
- Combine historical series with forward series derived from M2.
- Annotate projection start (vertical line + label).
- Output: `output/<run_id>/visualizations/effective_rate_historical_forward.png`.

M6) Run flow integration
- Ensure artifacts write under the current `<run_id>` alongside existing outputs.
- Add concise logs: parsed year ranges, join sizes, filtered rows, output paths.

M7) Tests and sanity checks
- Unit tests:
  - YAML parsing for FY-based `gdp.annual_fy_growth_rate` and `variable_rates_annual` (types, defaults, missing years).
  - GDP path construction over a small FY map; verify compounding per FY windows.
  - Effective-rate computation on synthetic data; correct joins and zero-handling.
  - Annual weighted aggregation correctness.
- Integration tests:
  - Small end-to-end run produces all artifacts with expected columns and non-empty content.
  - Chart files exist and are non-empty.
- Sanity checks (runtime):
  - Flag monthly effective rates < 0 or > 10%.
  - Limit discontinuity at historical-to-forward join (e.g., > 100 bps) and log.
  - GDP path non-decreasing with positive growth; log violations.

### Acceptance criteria (DoD)
- Config loads FY-based GDP growth and variable rates; warnings on defaults are logged.
- Monthly effective-rate CSV exists with valid rows for positive outstanding.
- FY and CY charts exist at specified paths; combined chart includes projection annotation.
- GDP path responds to growth inputs; forward effective rates reflect FY variable rates.
- All unit and integration tests pass; sanity checks produce no critical flags under normal inputs.

### Risks and mitigations
- Bucket/category name mismatches: introduce explicit mapping; validate coverage.
- Sparse FY inputs: piecewise-constant interpolation and warning logs; document behavior.
- Extreme/unstable rates from tiny denominators: filter and report in QA summary.

### Artifacts
- `output/<run_id>/diagnostics/effective_rate_monthly_by_bucket.csv`
- `output/<run_id>/fiscal_year/visualizations/effective_rate.png`
- `output/<run_id>/calendar_year/visualizations/effective_rate.png`
- `output/<run_id>/visualizations/effective_rate_historical_forward.png`


