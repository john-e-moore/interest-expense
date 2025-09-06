
# PRE-SPEC PROMPT (Copy-Paste for Agent)
**Project:** Interest Expense – Fresh Forward Projection Engine  
**Context you may assume:** Only `src/historical.py` and its outputs are available from prior work. Also available: `input/` folder containing `macro.yaml` and the Treasury Interest Expense on the Public Debt spreadsheet (IEOD/IntExp). **Do not** use or reference any other legacy code.

---

## SCOPE (Build-from-scratch Forward Model Only)
- Project **monthly** interest expense starting at the **anchor month** in `macro.yaml` (inclusive) for ~30 years.
- Use historical data **only for calibration and QA visuals**; never join history into the projection frame.
- Produce annual **CY** and **FY** tables in levels and **% of GDP** (using GDP as callables, not monthly-joined).
- Emit rich **diagnostics** and **sentinel assertions** at each step to catch mistakes early.

**Out of scope:** Rewriting `historical.py`. Joining monthly GDP into any dataframe. Left-joining historical frames to projection frames.

---

## OPERATING RULES (Follow Exactly)
1. **Small Steps + Pause Protocol**: After every step:
   - (a) run tests; (b) write intermediate artifacts to `output/diagnostics/`;
   - (c) print a concise **Step Report** (see template below);
   - (d) **STOP** and wait for my approval before continuing.
2. **No monthly GDP joins**: GDP is a callable (per-year) used **only** at annualization.
3. **No history↔projection joins**: Projection begins at anchor month and never merges with the historical frame.
4. **Sentinel assertions everywhere**: Fail fast with human-readable messages when assumptions break.
5. **Determinism**: Fix random seeds where relevant.
6. **Docstrings**: Every function/class must document inputs, outputs, invariants.
7. **Tech**: Python 3.11, numpy/pandas/matplotlib, pytest. **No seaborn.** Save plots as PNG.

---

## REPO LAYOUT (create exactly)
```
src/
  core/
    dates.py            # fiscal_year(), month helpers (pure)
    types.py            # Protocols & dataclasses for ports/DTOs
  macro/
    config.py           # load_macro_yaml(path) -> MacroConfig
    gdp.py              # build_gdp_function(...) -> GDPModel (callables)
    rates.py            # RateProvider Protocol + implementations
    issuance.py         # IssuancePolicy Protocol + implementations
  calibration/
    matrix.py           # build_X(...) from historical outputs
    fit.py              # calibrate_shares(...) constrained SLSQP
  engine/
    state.py            # DebtState dataclass
    accrual.py          # compute_interest(state, rates, shares) (pure)
    transitions.py      # update_state(state, rates, shares) (pure)
    project.py          # ProjectionEngine (class orchestrator)
  annualize.py          # CY/FY aggregation + %GDP (pure)
  diagnostics/qa.py     # save diagnostics CSVs + QA plots
tests/
output/
  diagnostics/
  calendar_year/{spreadsheets,visualizations}/
  fiscal_year/{spreadsheets,visualizations}/
input/
  macro.yaml
  IntExp_spreadsheet.xlsx  # (name may differ; detect at runtime)
```

---

## INTERFACES & DATA MODELS
Use **ports & adapters** with `typing.Protocol` for swappability and testing.

```python
# src/core/types.py
from typing import Protocol, Mapping
from dataclasses import dataclass
import pandas as pd

class RateProvider(Protocol):
    def get(self, ts: pd.Timestamp) -> Mapping[str, float]:
        """Return macro rates for month ts, e.g. r_3m, r_2y, r_10y."""

class GDPModel(Protocol):
    def gdp_cy(self, year: int) -> float: ...
    def gdp_fy(self, year: int) -> float: ...

class IssuancePolicy(Protocol):
    def shares(self, ts: pd.Timestamp) -> tuple[float, float, float]:
        """(SHORT, NB, TIPS) >=0 and sum=1; may vary by time."""

@dataclass(frozen=True)
class MacroConfig:
    anchor_date: str              # e.g., "2025-07-31"
    anchor_gdp: float
    gdp_growth_fy: dict[int,float]    # {2026:0.04, ...}
    horizon_months: int | None = 360
```

```python
# src/engine/state.py
from dataclasses import dataclass

@dataclass
class DebtState:
    stock_short: float
    stock_nb: float
    stock_tips: float
    wam_months: float | None = None

    def total(self) -> float:
        return self.stock_short + self.stock_nb + self.stock_tips
```
---

## CRITICAL INVARIANTS (enforce with assertions)
- Shares are nonnegative and sum to ~1 (±1e-6) each month.
- No NaNs in calibration matrix; `NB` column variance > 0.
- Projection index `min` ≥ anchor month; **no historical dates** in projection DF.
- GDP anchor holds: `gdp_fy(FY(anchor)) == anchor_gdp` (±1e-6).
- Rates provided for every projected month; finite values.

Provide helper functions like `assert_shares_valid()`, `assert_finite_df()`, and re-use them.

---

## STEP PLAN (execute one step at a time)

### Step A — Helpers (dates)
- Implement `core/dates.fiscal_year(ts)` (FY starts Oct 1).
- **Tests:** Sep 30 vs Oct 1 boundary; vectorized correctness.
- **Artifacts:** `output/diagnostics/sample_fy_check.csv` (10 demo rows).

**Step Report**: function signature, min/max dates used in sample, sample mapping head/tail.

---

### Step B — Macro load + GDP as function
- Implement `macro/config.load_macro_yaml(path)` → `MacroConfig`.
- Implement `macro/gdp.build_gdp_function(anchor_date, anchor_gdp, annual_yoy)` → `GDPModel` with `gdp_cy(year)`, `gdp_fy(year)` callables. **Do not** write monthly GDP anywhere.
- **Tests:** anchor FY equals `anchor_gdp`; FY growth compounding; simple CY mapping.
- **Artifacts:** `output/diagnostics/gdp_check.csv` (year, gdp_fy, gdp_cy).

**Step Report**: anchor FY, gdp_fy(anchorFY), gdp_fy(anchorFY+1), small preview table.

---

### Step C — Rate providers
- Protocol: `RateProvider`.
- Implement `ConstantRatesProvider` (for tests) and `MonthlyCSVRateProvider` that reads `input/` CSV/XLS and validates full coverage for `proj_idx`.
- **Artifacts:** `output/diagnostics/rates_preview.csv` over the projection horizon (date + key rates).
- **Tests:** coverage, non-negativity (or allowed negatives), finite values.

**Step Report**: preview head/tail, date coverage, columns present.

---

### Step D — Issuance policy
- Protocol: `IssuancePolicy`.
- Implement `FixedSharesPolicy(short, nb, tips)` and (optional) `PiecewiseSharesPolicy` loaded from `macro.yaml`.
- **Tests:** shares sum to 1, bounds, time-varying behavior if piecewise.
- **Artifacts:** `output/diagnostics/issuance_preview.csv` (date, shares for first 24 months).

**Step Report**: example shares and validation summary.

---

### Step E — Calibration matrix (from historical outputs)
- Read **only** from `output/historical/` artifacts written by `historical.py` (e.g., monthly interest totals and/or stocks by bucket). If a path is unclear, **pause and ask me** for the exact file.
- Build `calibration/matrix.build_X(...)` → `X (SHORT, NB, TIPS)`, `y` (actual monthly interest) over the last 36–60 hist months.
- Validate: no NaNs, `NB` variance > 0.
- **Artifacts:** `output/diagnostics/calibration_matrix.csv` (date, y, SHORT, NB, TIPS).
- **Tests:** shape checks, no-NaN, variance thresholds.

**Step Report**: shapes, variances, head/tail, date range used.

---

### Step F — Constrained calibration fit
- Implement `calibration/fit.calibrate_shares(X, y, tip_cap=0.2)` using SLSQP with constraints `s≥0`, `sum(s)=1` (+ optional caps).
- Add **sanity bounds** before saving: `SHORT∈[0.05,0.60]`, `NB∈[0.05,0.85]`, `TIPS∈[0.00,0.20]` (tune later).
- **Artifacts:** `output/parameters.json` (only if bounds pass).
- **Tests:** recover synthetic shares within ±5pp.

**Step Report**: shares, objective value, bounds check result, parameters path.

---

### Step G — Projection engine
- Implement `engine/project.ProjectionEngine(rates: RateProvider, issuance: IssuancePolicy)` with `run(idx, start_state) -> monthly_df`.
- Keep **accrual** and **transitions** as **pure functions** in separate modules.
- Inputs: `proj_idx = date_range(anchor_month, periods=horizon_months, freq="MS")`.
- Starting state: read from historical output for **month prior to anchor** (stocks by bucket). If not available, **pause and ask** me for a seed state or a simple rule.
- **Artifacts:** `output/diagnostics/monthly_trace.parquet` with:
  - date, interest_{short,nb,tips,total}, stock_{short,nb,tips,total}, key rates, shares.
- **Tests:** 3-month golden run under constant rates/shares: finite numbers, index continuity, shares validity.

**Step Report**: first/last 3 rows, totals, date coverage, artifact path.

---

### Step H — Annualization + %GDP
- Implement `annualize.py`: from monthly interest, produce CY and FY tables (levels and %GDP). **Use GDP callables** (`gdp_cy/y`, `gdp_fy/y`)—**never** monthly-join GDP.
- **Artifacts:**
  - `output/calendar_year/spreadsheets/annual.csv`
  - `output/fiscal_year/spreadsheets/annual.csv`
- **Tests:** CY uses `gdp_cy`, FY uses `gdp_fy`; %GDP finite; years monotonic.

**Step Report**: two sample years with (level, %GDP) for CY & FY; file paths.

---

### Step I — QA visuals + bridge
- Implement `diagnostics/qa.py` to produce:
  1) Monthly interest overlay (hist vs proj) around the splice (2018–2026).
  2) Average effective rate line: `interest / avg_outstanding` (consistent denominator).
  3) Bridge table FY(anchorFY)→FY(anchorFY+1): stock effect, rate effect, mix/term effect, TIPS component.
- **Artifacts:**
  - `output/*/visualizations/*.png`
  - `output/diagnostics/bridge_table.csv`
- **Tests:** presence of files; simple value sanity checks on bridge columns.

**Step Report**: image paths, quick stats, bridge snippet.

---

## STEP REPORT (Template – print after every step)
```
STEP: <name>
Artifacts:
- <path 1>
- <path 2>
Shapes / ranges:
- df_name: shape=(r,c), date_min=..., date_max=...
Head/Tail (key tables):
<df.head(3)>
...
<df.tail(3)>
Key scalars:
- anchor_month=..., gdp_fy_anchor=..., shares=(..., ..., ...)
Tests: PASSED=<n>, FAILED=<m>
NEXT: (waiting for user approval)
```

---

## TEST MATRIX (minimum)
- `tests/test_dates.py`: FY boundary checks.
- `tests/test_gdp.py`: anchor level, growth compounding, CY mapping.
- `tests/test_rates.py`: provider coverage & finiteness.
- `tests/test_issuance.py`: shares validity, piecewise behavior.
- `tests/test_calibration_matrix.py`: shapes, NaNs, variance.
- `tests/test_calibration_fit.py`: synthetic recovery ±5pp.
- `tests/test_engine_golden.py`: 3-month constant run (finite, contiguous, sums sane).
- `tests/test_annualize.py`: CY/FY use correct GDP callables; %GDP finite.
- `tests/test_integration_smoke.py`: end-to-end 12-month run using ConstantRates + FixedShares → outputs exist + basic assertions.

---

## ARTIFACT PATHS (write exactly here)
- `output/diagnostics/sample_fy_check.csv`
- `output/diagnostics/gdp_check.csv`
- `output/diagnostics/rates_preview.csv`
- `output/diagnostics/issuance_preview.csv`
- `output/diagnostics/calibration_matrix.csv`
- `output/parameters.json`
- `output/diagnostics/monthly_trace.parquet`
- `output/calendar_year/spreadsheets/annual.csv`
- `output/fiscal_year/spreadsheets/annual.csv`
- `output/calendar_year/visualizations/*.png`
- `output/fiscal_year/visualizations/*.png`
- `output/diagnostics/bridge_table.csv`

---

## IMPLEMENTATION NOTES (important)
- **Anchor date**: read from `input/macro.yaml`; projection index starts at **month start** of that date.
- **Historical inputs**: consume only the CSVs generated by `historical.py` from `output/historical/`. If a filename is ambiguous, **pause and ask** me to confirm paths.
- **Rates**: For dev, use `ConstantRatesProvider`; for production, accept a CSV/XLS adapter reading from `input/` with validation.
- **Calibration**: If the matrix shows `NB` variance ~0 or NaNs, **raise** with a message and write the matrix CSV.
- **GDP**: Implement FY→CY mapping as a simple policy (e.g., 25/75 blend) with a docstring; we can revisit later.
- **No seaborn**: Use matplotlib. One chart per figure.

**Remember:** after each step, write artifacts, print Step Report, and **pause** for my review.
