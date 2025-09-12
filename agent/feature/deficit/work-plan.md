## Work Plan — Primary Deficit as %GDP, Optional Other Interest, Issuance Transition

### Objectives
- Implement primary deficit input as % of GDP (FY/CY), convert to monthly USD, and wire into the engine budget identity.
- Keep optional features toggled OFF by default: exogenous other_interest forecast and smooth issuance-share transitions.
- Provide diagnostics, tests, and sanity checks consistent with project standards.

### Deliverables
- Parser updates to `src/macro/config.py` for `deficits.annual_pct_gdp`.
- Monthly deficit series builder and `deficits_preview.csv`.
- Updated `scripts/run_forward.py` to pass deficits into the engine and write diagnostics.
- Optional: other_interest builder and preview; transitional issuance shares policy and preview.
- Tests: mapping correctness, budget identity with deficits, optional features behavior, and transitions.

### Phase 1 — Deficits-only MVP (ON by default when provided)
1) Config parsing
   - Extend `MacroConfig` loader to accept `deficits.annual_pct_gdp: {year: percent}` (percent, not decimal).
   - Normalize to `{int(year): float(percent)}`; no change to `deficits_frame`.
2) Builder: %GDP → monthly USD
   - New helper (e.g., `src/macro/deficits.py`):
     - `build_primary_deficit_series(cfg, gdp_model, index) -> (pd.Series, pd.DataFrame)`
     - Map FY/CY years using `fiscal_year` for FY; use `gdp_fy/gdp_cy` from `GDPModel`.
     - Forward-fill provided percentages across the horizon; backfill to anchor if needed.
     - Compute annual USD = pct_decimal * GDP; allocate evenly across months; restrict to projection index.
     - Return monthly series (USD mn/month) and a small preview table per-row for diagnostics.
     - Sanity checks: for fully covered years in index, monthly sum ≈ annual; warn on |pct| > 15%.
3) Wire into run script
   - In `scripts/run_forward.py`:
     - After building `idx` and `gdp_model`, call the builder, write `diagnostics/deficits_preview.csv`.
     - Pass the series as `deficits_monthly` to `ProjectionEngine.run`.
     - Optionally include the monthly deficit in `monthly_trace.csv` for transparency.
4) Tests
   - FY mapping: 12-month allocation sums to `pct * gdp_fy(year)`; partial anchor FY sums to months-in-index/12 fraction.
   - CY mapping: analogous checks.
   - Engine budget identity: with non-zero deficits, monthly `GFN = deficit + interest + other + redemptions` holds (extend existing identity test).

### Phase 2 — Optional Other Interest Forecast (default OFF)
1) Config parsing (optional block)
   - Accept either `%GDP` or `annual_usd_mn` under `other_interest:` with a `frame` and `enabled: false` by default.
2) Builder
   - Reuse logic pattern from deficits to build monthly USD series; write `other_interest_preview.csv`.
3) Wiring
   - When enabled, pass series as `other_interest_monthly` to the engine.
4) Tests
   - Verify annual sum consistency for fully covered years; partial-year proportionality at anchor.

### Phase 3 — Optional Smooth Issuance-Share Transition (default OFF)
1) Policy
   - Implement `TransitionalSharesPolicy` that linearly interpolates from start_state shares to target shares over N months.
   - Ensure shares remain in [0,1] and sum to 1 (renormalize if necessary).
2) Wiring
   - When `issuance_shares_transition.enabled: true`, use the transitional policy in place of fixed shares.
   - Write `issuance_transition_preview.csv` for the ramp window.
3) Tests
   - Validate interpolation and normalization; simple scenario shows reduced jump at anchor.

### Diagnostics & QA
- Always write `deficits_preview.csv` during runs with any deficits configuration.
- If options are enabled, also write `other_interest_preview.csv` and `issuance_transition_preview.csv`.
- Optionally add a QA plot decomposing `GFN` components by FY for the first two years to visualize contributions.

### Acceptance Criteria
- Deficits-only path:
  - Monthly deficit series constructed; preview CSV exists; budget identity holds; FY sums match `pct * GDP` for full years.
  - FY(anchor+1) interest increases versus zero-deficit baseline, ceteris paribus.
- Optional features:
  - When enabled, previews exist and annual sums match; engine consumes series without breaking identity.

### Risks & Mitigations
- Risk: Large negative deficits (surplus) can yield negative GFN; issuance shares applied to net retirements may reduce stocks quickly.
  - Mitigate by logging warnings; consider later explicit retirement/buyback logic if needed.
- Risk: Inconsistent GDP inputs vs deficits frame.
  - Mitigate by using the same `GDPModel` and validating coverage.

### Rollout Plan
- Defaults: options OFF; deficits-only first. Provide example macro.yaml snippet in docs.
- Backward compatible: if `deficits.annual_pct_gdp` absent, behavior remains as today (zero deficits).

### Estimated Effort
- Phase 1: 4–6 hours (parser, builder, wiring, tests, previews).
- Phase 2: 2–3 hours (optional).
- Phase 3: 3–4 hours (optional).


