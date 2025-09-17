## Additional Revenue Offset — % of GDP or Level (feature/additional-revenue)

### Goal
- Allow users to specify an optional additional revenue path (FY or CY), either as a percent of GDP or as a dollar level (USD millions), which is subtracted from the primary deficit before propagation through the forward engine.

### Scope
- Config schema: add `deficits.additional_revenue` with explicit mode and values.
- Conversion: build a monthly USD series aligned to `deficits.frame` using the GDP model.
- Engine wiring: subtract from the monthly primary deficit prior to budget identity usage.
- Diagnostics/QA: write preview CSV; extend monthly trace; add tests.

---

## Configuration Schema (input/macro.yaml)

```yaml
deficits:
  frame: FY  # or CY
  annual_pct_gdp:
    2026: 3.0
    2027: 2.8

  additional_revenue:
    mode: pct_gdp   # "pct_gdp" or "level"
    # When mode == pct_gdp: provide percentages (not decimals)
    annual_pct_gdp:
      2026: 1.0   # 1.0% of GDP
      2027: 1.1
    # When mode == level: provide annual USD millions (nominal)
    # annual_level_usd_millions:
    #   2026: 300000
    #   2027: 300000
```

### Rules
- Exactly one of `annual_pct_gdp` or `annual_level_usd_millions` is accepted, determined by `mode`.
- Values are:
  - `pct_gdp` mode: percentages, not decimals (e.g., `1.0` means 1%).
  - `level` mode: USD millions per year (nominal).
- Sign convention: positive additional revenue reduces the deficit. Negative values are allowed to represent tax cuts (increase the deficit).
- Year keys use `deficits.frame`:
  - If `frame: FY`, keys are fiscal years; mapping uses `fiscal_year(date)`.
  - If `frame: CY`, keys are calendar years.
- Coverage: forward‑fill the last provided year through the projection horizon; backfill to the anchor year if needed.
- Validation: reject non‑finite values; warn on extreme magnitudes (e.g., |pct| > 10 or level > 2,000,000).

---

## Conversion to Monthly USD

Let `idx` be the monthly projection index (timestamps at month start). Build an aligned monthly series `additional_revenue_month_usd_mn` (USD millions per month):

- Determine the year key for each month `t ∈ idx` using `deficits.frame`.
- Compute the annual level for that year:
  - If `mode == pct_gdp`: `annual_usd_mn = (pct / 100.0) * gdp_y`, where `gdp_y` is from the GDP model (`gdp_fy(y)` or `gdp_cy(y)`).
  - If `mode == level`: `annual_usd_mn = provided_level_y`.
- Allocate evenly across the months of that year that fall within `idx`:
  - For months of year `y` present in `idx`, set `m = annual_usd_mn / 12.0` for each such month.
- Output: `additional_revenue_month_usd_mn: pd.Series` indexed by `idx`.

Notes:
- Even monthly allocation matches existing deficit handling; seasonal weighting can be a future enhancement.
- Allocation is only applied to months in the projection index; no pre‑anchor allocation.

---

## Engine Wiring

No change to the budget identity; we adjust the primary deficit input before calling the engine.

1) Build the current monthly primary deficit series (already implemented from `deficits.annual_pct_gdp`).
2) Build `additional_revenue_month_usd_mn` from this spec.
3) Compute the adjusted monthly series:
   - `primary_deficit_adj_month_usd_mn = primary_deficit_month_usd_mn - additional_revenue_month_usd_mn`.
4) Pass the adjusted series to the engine (as the `primary_deficit` input used in `GFN_t = primary_deficit_t + interest_t + other_interest_t + redemptions_t`).

### Implementation Notes
- New helper (e.g., `src/macro/additional_revenue.py`):
  - `build_additional_revenue_series(cfg: MacroConfig, gdp_model: GDPModel, index: pd.DatetimeIndex) -> tuple[pd.Series, pd.DataFrame]`
  - Returns the monthly series and a per‑month preview table.
- Extend config loader (`src/macro/config.py`) to parse and validate `deficits.additional_revenue` per schema above, storing:
  - `additional_revenue_mode: Literal["pct_gdp", "level"] | None`
  - `additional_revenue_annual_pct_gdp: dict[int, float] | None`
  - `additional_revenue_annual_level_usd_millions: dict[int, float] | None`
- Update the forward run script (`scripts/run_forward.py`) to build the series and subtract from the primary deficit before engine execution.

---

## Diagnostics & Outputs

- Write `output/<run>/diagnostics/additional_revenue_preview.csv` with columns:
  - `date, frame, year_key, mode, input_value, gdp, additional_revenue_annual_usd_mn, additional_revenue_month_usd_mn`
- Extend `output/<run>/diagnostics/monthly_trace.csv` with:
  - `additional_revenue_month_usd_mn`
  - `primary_deficit_adj_month_usd_mn` (optional if the engine already writes the final primary deficit).
- Annual summaries: include a new line item in annual breakdown spreadsheets (FY/CY) for transparency.

---

## Validation & Sanity Checks

- Year‑sum coherence: for any year fully present in `idx`, `sum(months_y) ≈ annual_usd_mn` within a small tolerance.
- GDP dependency: `pct_gdp` mode requires GDP for the year; use the existing GDP model (`gdp_fy/gdp_cy`).
- Mutually exclusive inputs: raise if `mode` conflicts with provided mappings, or both mappings are present.
- Finite checks: raise on NaN/Inf; coerce keys to `int`, raising on failure.
- Extreme values: log a warning for |pct| > 10% or |annual_level| > 2,000,000.

---

## Tests

- Parsing: modes, value types, year‑key normalization, exclusivity rules.
- FY vs CY mapping: month → year key mapping and GDP source selection.
- Builder arithmetic: monthly allocation and year‑sum ≈ annual level.
- Wiring: `primary_deficit_adj = primary_deficit - additional_revenue` end‑to‑end in the forward run.
- Edge cases: forward/backfill behavior; negative values (tax cuts) increasing the deficit; additional revenue exceeding the deficit (surplus).

---

## Backwards Compatibility

- If `deficits.additional_revenue` is absent, behavior is unchanged.
- Existing `deficits.annual_pct_gdp` semantics remain intact.

---

## Examples

### Example A — FY, percent of GDP
```yaml
deficits:
  frame: FY
  annual_pct_gdp:
    2026: 3.0
    2027: 2.8
  additional_revenue:
    mode: pct_gdp
    annual_pct_gdp:
      2026: 1.0
      2027: 1.1
```

### Example B — FY, level (USD millions)
```yaml
deficits:
  frame: FY
  annual_pct_gdp:
    2026: 3.0
    2027: 2.8
  additional_revenue:
    mode: level
    annual_level_usd_millions:
      2026: 300000
      2027: 300000
```


