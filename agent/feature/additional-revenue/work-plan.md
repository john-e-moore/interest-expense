## Work Plan — Additional Revenue Offset (%GDP or Level)

### Objectives
- Implement an optional additional revenue path (FY/CY) entered as percent of GDP or as an annual USD level (millions), converted to a monthly series that reduces the primary deficit before engine execution.
- Maintain existing budget identity and outputs; add diagnostics and tests for transparency and correctness.

### Deliverables
- Config parsing in `src/macro/config.py` for `deficits.additional_revenue` with:
  - `mode: pct_gdp | level`
  - `annual_pct_gdp: {year: percent}` (percent, not decimal)
  - `annual_level_usd_millions: {year: usd_mn}`
- Series builder `src/macro/additional_revenue.py` producing monthly USD series and a preview DataFrame.
- Wiring in `scripts/run_forward.py`: subtract series from monthly primary deficit before calling the engine.
- Diagnostics outputs: `output/<run>/diagnostics/additional_revenue_preview.csv`; extend `monthly_trace.csv` with `additional_revenue_month_usd_mn` and optionally `primary_deficit_adj_month_usd_mn`.
- Tests covering parsing, FY/CY mapping, arithmetic, wiring, and edge cases.

### Phase 1 — MVP (ON only when configured)
1) Config parsing
   - Extend `MacroConfig` to include:
     - `additional_revenue_mode: Literal["pct_gdp", "level"] | None`
     - `additional_revenue_annual_pct_gdp: dict[int, float] | None`
     - `additional_revenue_annual_level_usd_millions: dict[int, float] | None`
   - Validation rules:
     - If `mode == pct_gdp`, require `annual_pct_gdp` and forbid `annual_level_usd_millions`.
     - If `mode == level`, require `annual_level_usd_millions` and forbid `annual_pct_gdp`.
     - Keys must be ints; values finite; warn on extreme magnitudes (|pct| > 10 or level > 2,000,000).
     - Use `deficits.frame` for FY vs CY semantics.
2) Builder: annual → monthly USD
   - New helper: `build_additional_revenue_series(cfg, gdp_model, index) -> (pd.Series, pd.DataFrame)` in `src/macro/additional_revenue.py`.
   - Logic:
     - Determine needed years from `index` using FY (`fiscal_year`) or CY per `deficits.frame`.
     - Forward‑fill to horizon; backfill to anchor as needed.
     - `pct_gdp` mode: annual = (pct/100) × GDP_y (from `gdp_fy/gdp_cy`).
     - `level` mode: annual = provided USD millions.
     - Allocate evenly by month within the year present in `index` (annual/12 per month).
   - Return monthly series (`additional_revenue_month_usd_mn`) and preview rows with: `date, frame, year_key, mode, input_value, gdp, additional_revenue_annual_usd_mn, additional_revenue_month_usd_mn`.
   - Sanity checks: year-sum ≈ annual for full years; log warnings for extremes.
3) Wire into run script
   - After building the base `primary_deficit` monthly series, build `additional_revenue_month_usd_mn` when configured.
   - Compute `primary_deficit_adj = primary_deficit - additional_revenue_month_usd_mn`.
   - Write `diagnostics/additional_revenue_preview.csv` and extend `diagnostics/monthly_trace.csv`.
   - Pass the adjusted series to the engine instead of the unadjusted primary deficit.
4) Tests
   - Parsing: modes, exclusivity, type normalization, FY/CY adherence.
   - Mapping: FY and CY month→year mapping and GDP source selection.
   - Arithmetic: monthly allocation and year‑sum ≈ annual; partial‑year proportionality at anchor.
   - Wiring: end‑to‑end run shows `primary_deficit_adj = primary_deficit - additional_revenue` and reduced GFN/issuance relative to baseline.
   - Edge cases: negative values (tax cuts) increase deficit; additional revenue > deficit (surplus); missing years fill; invalid values raise.

### Phase 2 — Output polish & docs
1) Outputs
   - Add `additional_revenue` line item to annual FY/CY spreadsheets for transparency.
   - Ensure legends/labels in visuals remain accurate if new fields are plotted (optional).
2) Docs
   - Add example snippets to `README.md` and `agent/specs` references showing both modes.
   - Note sign conventions and units.

### Diagnostics & QA
- Always write `additional_revenue_preview.csv` when configured.
- Extend `monthly_trace.csv` with `additional_revenue_month_usd_mn` and optionally `primary_deficit_adj_month_usd_mn`.
- Optional QA chart: FY decomposition showing impact of additional revenue on `GFN` components for anchor+1 year.

### Acceptance Criteria
- With `additional_revenue` configured, monthly series exists and preview CSV is written.
- Year‑sum coherence holds for full years; partial‑year months sum proportionally.
- Engine consumes adjusted primary deficit; end‑to‑end outputs reflect reduced deficits (and interest/issuance) vs baseline.
- Backward compatibility: absence of `additional_revenue` yields identical results to current behavior.

### Risks & Mitigations
- Frame mismatch (FY vs CY) or GDP availability: use the existing `GDPModel` and validate coverage; raise with clear messages.
- Extreme or conflicting inputs (both mappings or wrong mode): validate and fail fast with actionable errors.
- Very large negative adjusted deficits (surplus) causing retirements: log warnings; consider later retirement/buyback handling if needed.

### Rollout Plan
- Default OFF: feature only activates when `deficits.additional_revenue` is present.
- Provide FY and level examples in the docs; add a small integration test fixture under `tests/fixtures/`.

### Estimated Effort
- Phase 1: 4–6 hours (parser, builder, wiring, tests, diagnostics).
- Phase 2: 2–3 hours (outputs and docs).

### Phase 3 — Feature flag: additional_revenue.enabled (default OFF)
1) Config parsing
   - Extend `deficits.additional_revenue` with `enabled: false` (default when absent).
   - In `src/macro/config.py`, add `additional_revenue_enabled: bool = False` to `MacroConfig` and parse the flag with safe coercion to bool.
2) Wiring behavior
   - Only build and subtract the additional revenue series when `enabled is True`.
   - If mappings are present but `enabled` is false (or missing), log a DEBUG note and ignore the series (no subtraction, no preview CSV).
   - Echo `enabled` in `config_echo.json` for traceability.
3) Diagnostics & outputs
   - When disabled, do not write `additional_revenue_preview.csv` and do not add the `additional_revenue` column into annual CSVs.
   - When enabled, behavior remains as in Phase 1–2.
4) Tests
   - Parsing defaults: when `enabled` missing, flag is false.
   - Disabled path: run produces no `additional_revenue_preview.csv`; annual CSVs lack the column; engine uses unadjusted primary deficit.
   - Enabled path: parity with existing tests; column appears; adjusted deficit < base for positive revenue.
5) Docs
   - Update `README.md` snippets to include `enabled: true` in examples, and call out the default is OFF.

Estimated Effort: 1–2 hours.


