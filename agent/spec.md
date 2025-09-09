
# Interest Expense — Forward Projection Engine (Mini‑Spec)

**Variant:** Aggregated tenor‑bucket simulator (Bills = SHORT, Notes/Bonds = NB, TIPS).  
**Goal:** Produce monthly and annual (CY/FY) interest expense and % of GDP for ~30 years starting at the anchor date, using a small, transparent state that is calibrated to history.

---

## 1) Scope & Purpose

- Build a clean forward model that **starts at the anchor month** in `input/macro.yaml` and **never joins historical rows** into the projection frame.
- Use outputs from `src/historical.py` **only** for calibration and QA visuals.
- Output annual **CY** and **FY** tables (levels and % of GDP) plus diagnostic artifacts.

### Non‑Goals / Anti‑Requirements
- No CUSIP‑level simulation (no auction calendars, coupons by CUSIP, day‑counts).
- No monthly GDP joins; GDP must be **annual callables** only.
- No left‑joins between historical frames and projection frames.
- No seaborn; matplotlib only (one chart per figure).

---

## 2) Anchor, Horizon, Units

- **Anchor date:** read from `input/macro.yaml` (e.g., `2025-07-31`). Projection index begins at the **month start** of the anchor (e.g., `2025-07-01`).
- **Horizon:** default `360` months (30 years); configurable via `macro.yaml`.
- **Currency & units:** Use nominal USD. Match the units of `historical.py` outputs (typically USD **millions**). Declare/convert explicitly at load time and keep consistent throughout.

---

## 3) Inputs & Data Contracts

### 3.1 `input/macro.yaml` (schema)
```yaml
anchor_date: "YYYY-MM-DD"     # month-end; engine uses month-start internally
horizon_months: 360           # optional; default 360
gdp:
  anchor_gdp_fy: 30000000.0   # FY-level nominal GDP at FY(anchor_date); units match outputs
  growth_fy:                  # FY YoY growth rates (fractional, not %)
    2026: 0.040
    2027: 0.035
primary_deficit:              # REQUIRED for budget-identity mode
  # Provide either FY or CY series; engine will map to months
  frame: "FY"                 # "FY" or "CY"
  values:
    2026: 1100000.0           # e.g., USD millions (match units)
rates:                        # One of:
  mode: "constant"            # "constant" or "table"
  constant:
    r_3m: 0.045               # annualized
    r_2y: 0.042
    r_10y: 0.045
    r_tips_10y_real: 0.020
  table:                      # if mode == "table", point to a CSV/XLS in input/
    path: "input/rate_path.csv"
issuance_policy:              # optional override of calibrated shares
  mode: "fixed"               # "fixed" or "piecewise"
  fixed:
    short: 0.25
    nb: 0.65
    tips: 0.10
  piecewise:
    - start: "2026-10-01"     # month-start
      short: 0.30
      nb: 0.60
      tips: 0.10
```

**Notes**
- If a **debt stock path** (total debt outstanding) is supplied in `macro.yaml`, it can be used in “stock‑driven mode” (optional). Default is **budget‑identity mode** using primary deficits (see §6).
- If both FY and CY deficits are supplied, FY takes precedence.

### 3.2 Historical inputs (from `output/historical/`)
Provide **csv** files from `historical.py`. Expected (names can differ; adapter layer will map, but the following columns must exist):

1) **Monthly interest** (history):  
   - Columns: `date (YYYY-MM-DD, MS)`, `interest_total`  
   - Optional detail: `interest_short`, `interest_nb`, `interest_tips`

2) **Outstanding by bucket** at month‑end (for seed at `anchor-1`):  
   - Columns: `date`, `stock_short`, `stock_nb`, `stock_tips`

If filenames/columns differ, the adapter must translate and unit‑test the mapping. The engine must raise with a human message if any required column is missing.

---

## 4) Architecture & Interfaces

### 4.1 Ports (Protocols)
```python
# RateProvider: returns macro rates needed for month t
def get(ts: pd.Timestamp) -> Mapping[str, float]  # r_3m, r_2y, r_10y, r_tips_10y_real, ...

# GDPModel: annual callables only
def gdp_cy(year: int) -> float
def gdp_fy(year: int) -> float

# IssuancePolicy: issuance shares for month t
def shares(ts: pd.Timestamp) -> tuple[float, float, float]  # (SHORT, NB, TIPS); sums to 1
```

### 4.2 Data Models
```python
@dataclass(frozen=True)
class MacroConfig:
    anchor_date: str
    anchor_gdp: float
    gdp_growth_fy: dict[int, float]
    horizon_months: int = 360

@dataclass
class DebtState:
    stock_short: float
    stock_nb: float
    stock_tips: float
    wam_months: float | None = None
    def total(self) -> float: ...
```

### 4.3 Projection Engine
```python
class ProjectionEngine:
    def __init__(self, rates: RateProvider, issuance: IssuancePolicy): ...
    def run(self, idx: pd.DatetimeIndex, start_state: DebtState,
            deficits_monthly: pd.Series) -> pd.DataFrame:
        """
        Returns monthly DataFrame indexed by date with columns:
          interest_{short,nb,tips,total}, stock_{short,nb,tips,total},
          shares_{short,nb,tips}, key_rates...
        """
```

### 4.4 Pure Functions
- `build_gdp_function(anchor_date, anchor_gdp, growth_fy) -> GDPModel`  
- `annualize(monthly_df, gdp_model) -> (cy_levels, fy_levels, cy_pct, fy_pct)`  
- `calibration.build_X(hist_interest_df, hist_stock_df) -> (X, y)`  
- `calibration.fit.calibrate_shares(X, y, tip_cap=0.2) -> (short, nb, tips)`  
- `accrual.compute_interest(state, rates, shares) -> dict`  
- `transitions.update_state(state, rates, shares, new_issuance) -> state`

---

## 5) Accrual & Transition Policy (Simplified)

Let **k ∈ {short, nb, tips}**. For month *t*:

- **Rollover / Maturities**
  - Bills (short): **fully roll** each month (`R_t^short = B_t^short`).  
  - NB: treat as a single bucket with **average life** rule *or* a small set of cohorts (optional future enhancement). For this mini‑spec, use a **fixed monthly decay rate** chosen to match the historical WAM (calibrated constant).  
  - TIPS: same decay rule as NB for principal; add CPI indexation to principal.

- **Interest Accrual**
  - Bills: `interest_short_t = (r_3m_t / 12) * B_t^short_post`  
  - NB: `interest_nb_t = (coupon_nb / 12) * B_t^nb_post`  
    - `coupon_nb` for **existing stock** is the historical average coupon at anchor; **new issuance** uses current `r_2y/r_5y/...` collapsed to an effective `coupon_new_nb ≈ r_10y_t` (policy knob; keep simple).  
  - TIPS: `interest_tips_t = (real_coupon / 12) * principal_tips_adj + inflation_accretion_t`  
    - Inflation accretion derived from CPI path implied by real vs nominal, or a direct CPI assumption if provided.

- **Gross Financing Need (Budget Identity)**
  - `GFN_t = primary_deficit_t + interest_total_t + redemptions_t`  
  - `redemptions_t = Σ_k R_t^k`

- **Issuance**
  - `new_t^k = s_t^k * GFN_t` where `s_t^k = IssuancePolicy.shares(t)` and `Σ_k s_t^k = 1`.

- **State Update**
  - `B_{t+1}^k = (B_t^k - R_t^k) + new_t^k`

**Note:** If “stock‑driven mode” is used, skip the budget identity and set total new issuance so that `Σ_k B_{t+1}^k` matches the exogenous debt target; allocate by shares.

---

## 6) Calibration (What & How)

- Construct a design matrix `X_t = [exposure_short_t, exposure_nb_t, exposure_tips_t]` from the last **36–60** historical months so that `y_t (actual interest)` is well explained by `X_t` under **non‑negative**, **sum‑to‑one** constraints (use SLSQP).  
- Save `output/diagnostics/calibration_matrix.csv` (date, y, columns of X).  
- Fit `s = (short, nb, tips)` and enforce sanity bounds (e.g., `TIPS ≤ 0.2`).  
- If `var(NB) ≈ 0` or NaNs appear, **raise** and stop; do not write `parameters.json`.

Output: `output/parameters.json` with validated shares and any decay parameter used for NB/TIPS.

---

## 7) Annualization & % of GDP

- Tag months as **CY** (`date.year`) and **FY** (`fiscal_year(date)`, Oct–Sep).  
- **Levels:** sum monthly interest by CY and FY.  
- **% of GDP:** divide by `gdp_cy(year)` and `gdp_fy(year)` **from callables** only.

Outputs:
- `output/calendar_year/spreadsheets/annual.csv`  
- `output/fiscal_year/spreadsheets/annual.csv`

---

## 8) Diagnostics & QA

- `output/diagnostics/monthly_trace.parquet`: per‑month state, interest by bucket, rates, shares.  
- `output/diagnostics/bridge_table.csv`: FY(anchorFY)→FY(anchorFY+1) decomposition into **stock**, **rate**, **mix/term**, **TIPS accretion** effects.  
- Plots (PNG):  
  1) Monthly interest (2018–2026): history (solid) vs projection (dashed).  
  2) Average effective rate paid: `interest / avg_outstanding`.  
  3) Annual CY/FY with %GDP.

---

## 9) Acceptance Criteria (Definition of Done)

1. **Anchor & GDP**
   - `gdp_fy(FY(anchor)) == anchor_gdp` (±1e-6).  
   - Projection index min == month‑start(anchor). No historical rows in projected DF.

2. **Calibration**
   - `calibration_matrix.csv` exists; no NaNs; `var(NB) > 0`.  
   - Shares `≥ 0`, sum to 1; within sanity bounds; parameters.json written only if valid.

3. **Projection math**
   - Monthly loop passes sentinel assertions (finite numbers; shares valid; rates present).  
   - `monthly_trace.parquet` exists with required columns.

4. **Annualization**
   - CY uses `gdp_cy`, FY uses `gdp_fy`; `%GDP` finite and reasonable.  
   - Annual CSVs exist with monotonic year indices.

5. **Visual continuity**
   - Splice plots show no discontinuity except what’s attributable to macro paths or issuance policy changes.

---

## 10) Test Matrix (Minimum)

- `test_dates.py`: FY boundary (Sep 30 vs Oct 1).  
- `test_gdp.py`: anchor level, compounding of FY growth, CY mapping.  
- `test_rates.py`: provider coverage for projection index; finiteness.  
- `test_issuance.py`: shares validity (fixed & piecewise).  
- `test_calibration_matrix.py`: shapes, NaNs, variance.  
- `test_calibration_fit.py`: recover synthetic shares within ±5pp.  
- `test_engine_golden.py`: 3‑month constant run—finite numbers, contiguous dates.  
- `test_annualize.py`: CY/FY %GDP uses correct callable.  
- `test_integration_smoke.py`: 12‑month run writes all artifacts.

---

## 11) Implementation Guardrails

- **Do not** monthly‑join GDP.  
- **Do not** merge historical data into projection frames.  
- Use `@dataclass` for `MacroConfig` and `DebtState`.  
- Keep accrual/transition **pure**; engine is the only stateful class.  
- Always write artifacts **before** plotting; plots are purely for QA.

---

## 12) Future Upgrade Path (Optional)

- Replace NB bucket with **tenor cohorts** (2y/3y/5y/7y/10y/20y/30y) while keeping the same ports/tests.  
- Split FRNs from SHORT; add a simple reset rule.  
- Add a cash buffer / buybacks module if needed.

---

**End of Mini‑Spec**
