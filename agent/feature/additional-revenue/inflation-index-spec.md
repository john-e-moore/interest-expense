## Feature: Inflation Indexing for Additional Revenue

### Overview
Introduce inflation indexing for the `additional_revenue` feature so that, instead of providing a full per-year schedule, users specify a single anchor amount and an `index` that determines how the value evolves over time. Also output a YAML copy of the input configuration alongside the existing JSON config echo.

### Goals
- Allow `additional_revenue` to be driven by an anchor value and an inflation index: `None`, `PCE`, or `CPI`.
- Add inflation rate series to `macro.yaml` for `pce` and `cpi` in the same map-of-year-to-rate format used elsewhere.
- Persist a byte-for-byte YAML copy of the input configuration (e.g., `macro.yaml`) to the run output alongside the existing JSON config echo.

### Non-goals
- Do not integrate external data sources for inflation; all rates come from `macro.yaml`.
- Do not change unrelated modeling logic for interest expense or GDP beyond what is needed to interpret `additional-revenue`.

## Configuration Schema

### New fields in `macro.yaml`
- `inflation` (object)
  - `pce` (map<int year, float ratePct>)
  - `cpi` (map<int year, float ratePct>)

Notes:
- Rates are in percentage points per year, e.g., `3.1` means 3.1%.
- Format mirrors existing growth-rate maps: `{2025: 3.1, 2026: 2.9, ...}`.
- Year coverage must include all projection years in which an index is referenced.

### Changes to `deficits.additional_revenue` configuration
- Replace the requirement to specify values for every year with:
  - `enabled` (bool): existing behavior retained.
  - `mode` (string): existing; determines interpretation of the value: `level` (USD millions per year) or `pct_gdp` (percent of GDP).
  - `anchor_year` (int): the year to which `anchor_amount` applies.
  - `anchor_amount` (number): the value in `mode` units for `anchor_year`. If `mode=level`, units are USD millions; if `mode=pct_gdp`, units are percent of GDP.
  - `index` (string): one of `None`, `PCE`, `CPI` (case-insensitive). When `None`, value is constant over time in the selected `mode` units.

Backward compatibility:
- If legacy per-year schedules for `deficits.additional_revenue` are still present, prefer the new `anchor_*` + `index` fields when provided; otherwise, continue supporting legacy schedules unchanged. Emit a deprecation warning when legacy schedules are used.

### Example `macro.yaml` fragment
```yaml
inflation:
  pce: {2025: 3.1, 2026: 2.9, 2027: 2.4}
  cpi: {2025: 3.2, 2026: 2.8, 2027: 2.5}

deficits:
  frame: FY
  additional_revenue:
    enabled: true
    mode: level        # or pct_gdp
    anchor_year: 2025
    anchor_amount: 10.0   # USD millions if mode=level; percent if pct_gdp
    index: PCE            # None | PCE | CPI
```

## Behavior and Computation

### Indexing logic
- Let `I_y` be the inflation rate for year y (in percent) from `inflation.pce` or `inflation.cpi` depending on `index`.
- The value for year `t` is computed relative to `anchor_year` and `anchor_amount`:
  - If `index == None`: `value_t = anchor_amount` for all t.
  - Else (`index in {PCE, CPI}`): for `t >= anchor_year`:
    - `value_t = anchor_amount * Π_{y=anchor_year+1..t} (1 + I_y/100)`
  - For years `t < anchor_year` that appear in the projection horizon, use `value_t = anchor_amount` (no back-indexing).

Notes:
- Negative or zero inflation is allowed.
- When `mode = pct_gdp`, the computed `value_t` is in percent-of-GDP units and may itself change over time if an index is applied. Any conversion to dollar terms (if needed elsewhere) follows existing GDP pathways.
- Rounding should follow existing model conventions; avoid introducing new rounding until final presentation stages.

### Validation
- If `index == PCE`, require that `inflation.pce` contains entries for all years from `anchor_year+1` through the last modeled year.
- If `index == CPI`, require that `inflation.cpi` contains entries for all years from `anchor_year+1` through the last modeled year.
- `index` is case-insensitive but must be one of `none`, `pce`, `cpi` after normalization.
- `anchor_year` must be an integer year present in the model horizon.
- `anchor_amount` must be a finite number.
- If both legacy per-year schedules and the new fields are supplied, prefer the new fields and warn once.

## Output Changes

### Config echo in YAML
- In addition to the existing `diagnostics/config_echo.json`, write `diagnostics/config_echo.yaml` containing a byte-for-byte copy of the input YAML configuration as provided by the user.
- Implementation detail: copy the input YAML file directly (do not re-serialize) to preserve key order, comments, and formatting. If multiple YAML inputs exist, copy the primary macro configuration file that the JSON echo reflects.

### Inflation indexing diagnostics
- Write `diagnostics/inflation_index_preview.csv` whenever the anchor+index path is used (regardless of `mode`).
- Columns (one row per model year used):
  - `frame` (FY/CY)
  - `year_key` (int)
  - `mode` (level | pct_gdp)
  - `index` (none | pce | cpi)
  - `anchor_year` (int)
  - `anchor_amount` (float) — USD millions if `mode=level`, percent if `mode=pct_gdp`
  - `inflation_source` (PCE | CPI | None)
  - `inflation_rate_pct` (float) — rate for `year_key` (0.0 for anchor year or when `index=none`)
  - `cumulative_factor` (float) — Π(1 + I_y/100) from anchor_year+1..year_key; 1.0 at anchor year
  - `indexed_value_unit` (float) — the computed value in `mode` units prior to any GDP conversion
- Also extend `diagnostics/additional_revenue_preview.csv` with columns `index`, `anchor_year`, `anchor_amount`, `inflation_rate_pct`, and `cumulative_factor` when anchor+index is used.

## Errors and Messaging
- Missing inflation series entries for required years: raise a clear configuration error indicating the missing years and the chosen `index`.
- Unknown `index` value: raise an error listing allowed values.
- If `additional-revenue.enabled` is true but neither the new fields nor a legacy schedule is provided: raise a configuration error with guidance.
- When legacy schedule is used: log a deprecation warning pointing to the new fields.

## Testing
- Unit tests:
  - `index=None` yields a constant series in both `level` and `pct_gdp` modes.
  - `index=PCE` and `index=CPI` compound correctly year-over-year from `anchor_year`.
  - Negative, zero, and positive inflation rates are handled correctly.
  - Missing inflation years raise errors with correct messaging.
  - Case-insensitive handling of `index`.
  - Legacy schedule continues to work; new fields take precedence when both are present.
  - Inflation diagnostics generation: `inflation_index_preview.csv` is produced with expected columns; `cumulative_factor` equals the product of (1 + rate/100) across years; 1.0 at anchor year.
- Integration tests:
  - End-to-end run produces both `config_echo.json` and a byte-identical `config_echo.yaml` to the input `macro.yaml`.
  - End-to-end run with anchor+index writes `diagnostics/inflation_index_preview.csv` and `diagnostics/additional_revenue_preview.csv` contains the extended columns.

## Implementation Notes
- Parser:
  - Extend configuration loading to parse `inflation.pce` and `inflation.cpi` maps.
  - Normalize `index` to lowercase internally and validate.
- Engine:
  - Implement a helper to compute the indexed series given `anchor_year`, `anchor_amount`, `index`, and the appropriate inflation series.
  - Ensure forward-only compounding; no back-indexing.
- Output:
  - At the same point `config_echo.json` is written, also copy the input YAML to `diagnostics/config_echo.yaml` via a direct file copy.
  - When anchor+index is used, write `diagnostics/inflation_index_preview.csv` with the columns above. Also include indexing columns in `additional_revenue_preview.csv`.

## Performance
- Negligible; O(N) over the projection horizon for compounding.

## Risks and Edge Cases
- Partial inflation series: fail fast with explicit instruction to add missing years.
- Users may expect back-indexing for pre-anchor years; current behavior holds value constant for those years to avoid ambiguous historical reconstruction.
- If GDP series is missing or altered, it does not affect this feature directly unless other parts of the pipeline convert `gdp_pct` to dollars.

## Acceptance Criteria
- Given the example above and projection years 2025–2027:
  - `index=None`, `mode=level`, `anchor_amount=10.0` → [2025: 10.0, 2026: 10.0, 2027: 10.0]
  - `index=PCE`, `mode=level`, `anchor_amount=10.0`, `pce={2025:3.1, 2026:2.9}` → [2025: 10.0, 2026: 10.0*(1+2.9/100)=10.29, 2027: 10.29*(1+2.4/100)=10.53896]
  - `index=CPI`, analogous using CPI rates.
- `diagnostics/config_echo.yaml` exists in the run output directory and is byte-identical to the input YAML file.
