## Work Plan: Inflation Indexing for Additional Revenue

### Objective
Implement inflation indexing for `deficits.additional_revenue` driven by an anchor amount and `index` (None/PCE/CPI), plus write a YAML config echo alongside the existing JSON echo.

### Deliverables
- Config schema extended to include `inflation.pce`, `inflation.cpi`, and `deficits.additional_revenue` fields: `anchor_year`, `anchor_amount`, `index`.
- Additional revenue builder supports anchor+index flow with forward-only compounding; legacy per-year maps continue to work.
- YAML config echo written to `diagnostics/config_echo.yaml` (byte-identical to input).
- New diagnostics for indexing written to `diagnostics/inflation_index_preview.csv`, with extended fields added to `diagnostics/additional_revenue_preview.csv` when anchor+index is used.
- Tests covering parsing, computation, errors, case-insensitivity, diagnostics, and output file.

## Implementation Tasks

### 1) Configuration parsing and model updates
- Update `src/macro/config.py`
  - Extend `MacroConfig` dataclass with optional fields:
    - `inflation_pce: Optional[Dict[int, float]]`
    - `inflation_cpi: Optional[Dict[int, float]]`
    - `additional_revenue_anchor_year: Optional[int]`
    - `additional_revenue_anchor_amount: Optional[float]`  // USD millions when `mode=level`; percent when `mode=pct_gdp`
    - `additional_revenue_index: Optional[Literal["none", "pce", "cpi"]]`
  - Load from YAML:
    - Parse top-level `inflation.pce` and `inflation.cpi` maps using existing `_validate_fy_growth_map` (values as percent, not decimals).
    - Under `deficits.additional_revenue`, parse (if present):
      - `anchor_year` (int)
      - `anchor_amount` (float)
      - `index` (string) → normalize to lowercase in {"none","pce","cpi"}
  - Validation rules (raise ValueError with clear messages):
    - If `additional_revenue_enabled` is true and any of `anchor_year`, `anchor_amount`, or `index` supplied:
      - Require `mode` in {"level","pct_gdp"}
      - If `index` in {"pce","cpi"}, ensure corresponding inflation series contains all FY/CY years from `anchor_year+1` through last modeled year (based on horizon)
    - If both legacy maps and anchor fields provided: prefer anchor fields; emit deprecation warning (via logger) once.
    - If `index` not in allowed set after normalization: error.
  - `to_normalized_dict()`:
    - Include `inflation` block when provided for transparency (`pce`/`cpi` maps as given).
    - Include anchor fields and normalized `index` under `deficits.additional_revenue` when provided.

### 2) Additional revenue builder logic and diagnostics
- Update `src/macro/additional_revenue.py`
  - Add helper `compute_indexed_series(years: list[int], anchor_year: int, anchor_amount: float, index: str, pce: Dict[int, float] | None, cpi: Dict[int, float] | None) -> Dict[int, float]` that:
    - Returns a per-year map aligned to `years`.
    - If `index == "none"`: constant series at `anchor_amount` for all years.
    - If `index in {"pce","cpi"}`: forward-only compounding from `anchor_year` using product Π(1 + I_y/100) for y in (anchor_year+1..t). For t < anchor_year, hold constant at `anchor_amount` (no back-indexing).
  - Modify `build_additional_revenue_series` to support two paths:
    - New path: if `additional_revenue_anchor_year` and `additional_revenue_anchor_amount` and `additional_revenue_index` are present, build an annual series:
      - If `mode=pct_gdp`: treat computed values as percent-of-GDP and convert to USD millions using GDP for the proper frame per year.
      - If `mode=level`: treat computed values directly as USD millions per year.
    - Legacy path: retain existing per-year maps (`annual_pct_gdp` or `annual_level_usd_millions`).
    - Precedence: prefer anchor+index when both provided; log a one-time deprecation warning when falling back to legacy.
  - Diagnostics:
    - Write `diagnostics/inflation_index_preview.csv` containing per-year rows with: `frame`, `year_key`, `mode`, `index`, `anchor_year`, `anchor_amount`, `inflation_source`, `inflation_rate_pct`, `cumulative_factor`, `indexed_value_unit`.
    - Extend `diagnostics/additional_revenue_preview.csv` with `index`, `anchor_year`, `anchor_amount`, `inflation_rate_pct`, `cumulative_factor` when anchor+index is used.

### 3) YAML config echo copy
- Update `scripts/run_forward.py`
  - After `write_config_echo(...)`, copy `args.config` to `run_dir/diagnostics/config_echo.yaml` using a direct byte copy (`shutil.copyfile`) to preserve formatting and comments.

## Tests and Sanity Checks

### Unit tests
- Parsing (`src/macro/config.py`): new file `tests/test_config_inflation_index.py`
  - Accepts valid inflation maps and anchor fields; normalizes `index` case-insensitively.
  - Rejects unknown `index` values.
  - Errors when inflation years are missing for required range.
  - Coexistence: both legacy and anchor provided → anchor wins; deprecation warning emitted.
- Builder (`src/macro/additional_revenue.py`): extend `tests/test_additional_revenue_builder.py` or add new `tests/test_additional_revenue_indexed.py`
  - `mode=level`, `index=none`: constant series at anchor (USD millions), monthly equals annual/12.
  - `mode=level`, `index=pce` and `index=cpi`: correct compounding forward; pre-anchor years constant.
  - `mode=pct_gdp`, `index=pce`: percent series compounding applied before conversion to dollars using GDP.
  - Negative and zero inflation rates honored.
  - Inflation diagnostics generation: `inflation_index_preview.csv` has expected columns; `cumulative_factor` is the product of (1 + rate/100) across years; 1.0 at anchor year.
  - Sanity: when `index=none`, `inflation_rate_pct` is 0 and `cumulative_factor` is 1 across all years; `indexed_value_unit` equals `anchor_amount`.

### Integration tests
- Update or add in `tests/test_run_wiring_additional_revenue.py`:
  - Provide `inflation` and anchor fields; verify run completes and `additional_revenue_preview.csv` reflects indexed values with extended columns.
- New test `tests/test_config_echo_yaml.py`:
  - Run with a temporary YAML config; verify `diagnostics/config_echo.yaml` exists and is byte-identical to the input.
- End-to-end anchor+index sanity: With `pce={2026: 2.0, 2027: 3.0}`, `anchor_year=2025`, `anchor_amount=100`, verify 2026 factor=1.02, 2027 factor≈1.0506; preview values match.

## Docs and examples
- Update `README.md` snippets:
  - Add an example showing `deficits.additional_revenue` with `mode: level`, `anchor_year`, `anchor_amount` (USD millions), and `index: PCE`.
  - Mention top-level `inflation` block and the new diagnostics files.

## Rollout and Backward Compatibility
- Default behavior unchanged when new fields are absent.
- Legacy per-year schedules continue to work; when anchor fields provided, they take precedence.
- Clear errors for invalid/missing inflation years and invalid `index` values.

## Acceptance Criteria (DoD)
- Anchor+index produces correct series for `level` and `pct_gdp` modes per spec.
- Diagnostics files are written with correct columns and values; sanity checks pass.
- `diagnostics/config_echo.json` and byte-identical `diagnostics/config_echo.yaml` are written.
- All new and existing tests pass.

## Estimated Effort and Sequence
- Parsing/model updates: 1–2 hours
- Builder logic + helper + diagnostics: 1–2 hours
- YAML echo copy: 10 minutes
- Tests: 2–3 hours
- Docs: 30 minutes

Sequence:
1) Add dataclass fields and parsing for `inflation` and anchor+index, with validations.
2) Implement builder helper and integrate with `build_additional_revenue_series` (prefer anchor path); write diagnostics.
3) Add YAML echo copy in the run script.
4) Write/adjust tests; run suite and fix issues.
5) Update README and examples.
