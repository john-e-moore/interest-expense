## Primary Deficit Input — % of GDP (FY/CY) and Engine Wiring

### Goal
- Add a configurable primary deficit path expressed as percent of GDP (FY or CY), convert it to monthly USD flows, and wire it into the projection engine’s budget identity: GFN = primary_deficit + interest + other_interest + redemptions.
- Outcome: Forward issuance and stocks reflect deficits; FY2026+ interest levels rise in line with assumed deficits, smoothing the FY(anchor) → FY(anchor+1) visual transition without changing the splice methodology.

### Scope
- Config schema: accept `deficits.frame: FY|CY` and `deficits.annual_pct_gdp: {year: percent}` where percent is e.g. `3.0` for 3% of GDP.
- Conversion: build a monthly primary deficit series in USD millions over the projection index based on the chosen frame and the GDP model.
- Engine: pass the monthly series to the engine; no change to the budget identity formula.
- Diagnostics/QA: write preview CSV; include basic sanity checks; add tests.

### Configuration Schema (macro.yaml)
- New/clarified section:
```yaml
deficits:
  frame: FY        # or CY (already present, validated)
  annual_pct_gdp:  # mapping of year→percent (not decimal)
    2025: 3.0
    2026: 2.8
    2027: 2.5
```
- Rules:
  - Values are percentages, not decimals. Convert internally: pct_decimal = pct / 100.0.
  - Years are fiscal years when `frame: FY`, calendar years when `frame: CY`.
  - Missing years: forward-fill the last provided value through the projection horizon; backfill to the anchor year if needed.
  - Negative values are allowed (surplus), but must be finite.

### Conversion to Monthly USD
- Build the GDP model first (already done during annualization). Use the same model here to ensure consistency.
- For each projection month `t` with date index `idx`:
  - Determine year key `Y_t`:
    - If `frame == FY`: `Y_t = fiscal_year(t)` and use `gdp_t = gdp_model.gdp_fy(Y_t)`.
    - If `frame == CY`: `Y_t = t.year` and use `gdp_t = gdp_model.gdp_cy(Y_t)`.
  - Look up `pct_decimal = pct_map[Y_t]` (after fill).
  - Compute annual USD level: `D_annual = pct_decimal * gdp_t` (units: USD millions).
  - Allocate monthly evenly within the given year frame: `D_month = D_annual / 12`.
    - Only months within the projection index receive allocations (no backfill of pre‑anchor months).
- Output: `deficits_monthly: pd.Series` over `idx` (USD millions per month).

Notes:
- Equal monthly allocation is acceptable for a first pass and matches the engine’s aggregation assumptions. If desired, a future enhancement can weight by seasonal patterns.

### Engine Wiring (no API change)
- The engine already supports a monthly `deficits_monthly` series and uses the budget identity:
  - `GFN_t = primary_deficit_t + interest_total_t + other_interest_t + redemptions_t`.
- Update the forward run script to:
  1) Parse `deficits.annual_pct_gdp` from config.
  2) Build the monthly series per spec above using the GDP model and `deficits.frame`.
  3) Pass it to `ProjectionEngine.run(..., deficits_monthly=series, ...)`.

### Diagnostics & Outputs
- Write `output/<run>/diagnostics/deficits_preview.csv` with columns:
  - `date, frame, year_key, pct_gdp, gdp, deficit_month_usd_mn, deficit_annual_usd_mn`
- Include `deficit_month_usd_mn` in the `monthly_trace` CSV (optional but useful), or keep it implicit via GFN and add it to the preview only. Minimum requirement is the preview file.
- QA visuals (optional follow‑up): add an overlay of `GFN` components by FY for the anchor and next year.

### Optional Enhancements (toggles; default ON for Other Interest)

1) Other Interest Forecast (exogenous) — DEFAULT ON
- Purpose: Align forward coverage with history by adding a separate exogenous `other_interest` stream (e.g., guarantee fees, non-marketable), preventing a downward break at the anchor.
- Config (either mode):
```yaml
other_interest:
  enabled: true           # default true; build and pass monthly series unless explicitly disabled
  frame: FY               # or CY
  annual_pct_gdp:         # percent, not decimal (optional if using absolute)
    2025: 0.20
    2026: 0.18
  # OR absolute levels in USD millions (choose one mode)
  # annual_usd_mn:
  #   2025: 6000.0
  #   2026: 6200.0
```
- Conversion and wiring:
  - If `annual_pct_gdp` provided, map to GDP frame (FY/CY) using same logic as deficits; compute annual USD = pct * GDP; distribute evenly by month; series over projection index only.
  - If `annual_usd_mn` provided, use those levels per year; distribute evenly by month.
  - Pass as `other_interest_monthly` to the engine (units: USD millions/month).
- Diagnostics: write `diagnostics/other_interest_preview.csv` with `date, frame, year_key, pct_gdp(optional), annual_usd_mn, monthly_usd_mn`.
- Sanity: for fully covered years, monthly sum equals annual target; partial anchor year reconciles proportionally to months included.

2) Smooth Issuance-Share Transitions
- Purpose: Avoid abrupt changes in composition of issuance at the anchor (e.g., bills collapsing instantly). Linearly ramp shares from current effective mix to target shares over `N` months.
- Config:
```yaml
issuance_shares_transition:
  enabled: false        # default false; when true, ramp shares
  months: 6             # number of months to linearly interpolate (>=1)
```
- Behavior:
  - Derive starting shares at the anchor from the `start_state` composition: `s0_short = B_short / (B_short+B_nb+B_tips)` etc.
  - Target shares = `issuance_default_shares` (or fitted shares from `parameters.json` if present, consistent with current behavior).
  - For projection months m = 0..N-1 after anchor: `s_t = s0*(1 - m/N) + s_target*(m/N)` per bucket; for m ≥ N: `s_t = s_target`.
  - Ensure shares remain ≥0 and sum to 1 at each step (renormalize if needed due to rounding).
- Implementation: add a `TransitionalSharesPolicy` used in place of `FixedSharesPolicy` when enabled; it exposes the same `.get(index)` API and returns a time‑varying shares DataFrame.
- Diagnostics: write `diagnostics/issuance_transition_preview.csv` with `date, share_short, share_nb, share_tips, is_transition_window`.
- Tests: verify monotonic interpolation and that shares sum to 1; verify effective reduction of anchor jump in a small synthetic scenario.

### Sanity Checks
- Percentages must be finite; warn if |pct| > 15%.
- After construction:
  - Check that `sum(deficit_month_usd_mn over FY Y)` ≈ `pct_decimal[Y] * gdp_fy(Y)` (±1e-6 relative tolerance) for years fully covered by the index; for partial years (anchor FY), allow proportional tolerance based on months present.
  - Ensure `GFN_t ≥ redemptions_t` rarely goes negative given large surpluses; if `GFN_t < 0`, allow but warn that issuance shares will be applied to a negative GFN (interpreted as net retirements). Future enhancement: explicit handling for buybacks.

### Tests
- Unit: mapping from annual %GDP to monthly USD (FY and CY frames), including anchor FY partial coverage and forward fill.
- Unit: budget identity holds with non‑zero deficits (extend `tests/test_engine_identity.py`).
- UAT/Integration: run short horizon with sample deficits and assert:
  - `deficits_preview.csv` exists and matches expected totals per year.
  - FY(anchor+1) interest increases when positive deficits are applied vs zero deficits.
- Sanity: verify that constructed FY totals equal `pct * gdp_fy` for fully covered years.

### Backward Compatibility
- If `deficits.annual_pct_gdp` is absent, default to 0% across horizon (current behavior).
- `deficits.frame` remains required (already validated).

### Example (macro.yaml)
```yaml
anchor_date: 2025-07-31
horizon_months: 360

gdp:
  anchor_fy: 2025
  anchor_value_usd_millions: 30353902.0
  annual_fy_growth_rate:
    2026: 4.0
    2027: 3.5

deficits:
  frame: FY
  annual_pct_gdp:
    2025: 3.0
    2026: 2.8
    2027: 2.5

issuance_default_shares: { short: 0.2, nb: 0.7, tips: 0.1 }
rates:
  type: constant
  values: { short: 0.04, nb: 0.05, tips: 0.03 }
```

### Implementation Notes
- Parser: extend `src/macro/config.py` to read `deficits.annual_pct_gdp` (percent) into a normalized dict of `{year: pct_float}`; keep `deficits_frame` unchanged.
- Builder: in `scripts/run_forward.py`, after constructing `idx` and `gdp_model`, create the monthly series per this spec and write the preview CSV.
- Engine: no change required outside passing the series (already supported). Consider adding `deficit_month_usd_mn` into `monthly_trace` rows for transparency.
- Optional: parse `other_interest` block if `enabled: true`; build monthly series (pct‑of‑GDP or absolute), write preview CSV, and pass into engine.
- Optional: if `issuance_shares_transition.enabled`, select `TransitionalSharesPolicy` that ramps from `start_state` shares to target over `months`.

### Acceptance Criteria
- Config with `deficits.annual_pct_gdp` produces a non‑zero monthly series and `deficits_preview.csv`.
- Budget identity holds at monthly granularity with the new deficits input.
- FY totals of primary deficit equal `pct * GDP` for fully covered years; partial years reconcile proportionally to the months included in the index.
- Tests and sanity checks pass, and FY(anchor+1) interest increases versus zero‑deficit runs, all else equal.


