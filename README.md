# Interest Expense Engine

A fast, transparent engine that projects federal interest expense forward month-by-month and rolls the results up to fiscal-year (FY) and calendar-year (CY) views. It links budget flows (revenue, primary outlays, policy offsets) to debt issuance and interest costs, and reports the results in dollars and percent of GDP.

## Big picture

- Start from an anchor date and a GDP path.
- For each month, accrue interest on the existing debt stock using provided rates, redeem maturing debt, and issue new debt to meet the gross financing need.
- Gross financing need (GFN) each month is: primary deficit + interest + redemptions.
- Primary deficit is built from revenue and primary outlays; an optional additional_revenue policy can reduce it.
- Results are annualized to FY and CY, then written as concise spreadsheets and diagnostics for auditability.

## Quick start

```bash
# Optional: create and activate a virtualenv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run with the default config and full diagnostics
./run.sh

# Or run directly with a custom config and output directory
bash scripts/run.sh /absolute/path/to/input/macro.yaml /absolute/path/to/output
```

- Outputs are written under `output/<timestamp>/...` and mirrored diagnostics are available under `output/diagnostics/` for convenience.

## Command-line interface

The main entrypoint is `scripts/run_forward.py` (wrapped by `scripts/run.sh`). Key flags:

- `--config input/macro.yaml`: path to the macro configuration.
- `--golden`: shorten horizon to 12 months for a quick smoke run.
- `--diagnostics`: write diagnostics (rates, issuance, QA tables, bridges).
- `--dry-run`: parse config and exit (no projection run).
- `--perf`: run a performance profile over the full horizon.
- `--debug`: enable debug logging.
- `--uat`: produce a UAT checklist JSON.
- `--outdir output`: set/override the base output directory.

`run.sh` enables `--diagnostics`, `--perf`, `--debug`, and `--uat` by default.

## Configuration (input/macro.yaml)

All currency units are USD millions; rates and shares are in percent unless noted.

- `anchor_date` (YYYY-MM-DD): starting month for the projection.
- `horizon_months` (int): number of months to project.
- `gdp`:
  - `anchor_fy` (int): fiscal year of the GDP anchor.
  - `anchor_value_usd_millions` (float): nominal GDP level for `anchor_fy`.
  - `annual_fy_growth_rate` (map FY->percent): nominal FY GDP growth path.
- `inflation` (optional):
  - `pce` (map FY->percent)
  - `cpi` (map FY->percent)
- `budget`:
  - `frame`: `FY` or `CY` for how revenue/outlays series are interpreted.
  - `annual_revenue_pct_gdp` (map FY/CY->percent)
  - `annual_outlays_pct_gdp` (map FY/CY->percent)
  - `additional_revenue` (optional):
    - `enabled` (bool)
    - `mode`: `pct_gdp` or `level`
    - If `pct_gdp`: `annual_pct_gdp` (map year->percent)
    - If `level`: either `annual_level_usd_millions` (map year->amount) OR an anchor/index triplet:
      - `anchor_year` (int)
      - `anchor_amount` (USD millions)
      - `index`: `none`, `PCE`, or `CPI` (case-insensitive)
- `issuance_default_shares` (optional): `{short: 0.2, nb: 0.7, tips: 0.1}` must sum to 1.0.
- `rates`: constant rates block (optional for quick validation):
  - `type: constant`
  - `values`: `{short: 0.03, nb: 0.04, tips: 0.02}` (decimals)
- `variable_rates_annual` (optional): per-year rates (decimals) by bucket, keys normalized to `short|nb|tips`:
  - Example: `short: {2025: 0.0433, 2026: 0.0412, ...}`
- `other_interest` (optional, default enabled): exogenous interest not tied to marketable debt accrual
  - `enabled` (bool)
  - `frame`: `FY` or `CY`
  - `annual_pct_gdp` (map year->percent) or `annual_usd_mn` (map year->USD millions)
- `issuance_shares_transition` (optional): controls transition from starting stock mix to target shares
  - `enabled` (bool, default true)
  - `months` (int, default 6)

Validation and normalization of this YAML is implemented in `src/macro/config.py`. The engine also writes a normalized echo of the configuration to `output/<run_id>/diagnostics/config_echo.json`.

## What the engine does

1. Create a timestamped run directory and set up logging.
2. Build the monthly index for the projection horizon.
3. Initialize the starting marketable debt stock from historical MSPD data and scale it to match historical interest totals.
4. Build a GDP model mapping FY and CY years to nominal GDP.
5. Build monthly revenue and primary outlays series from budget shares and GDP; apply `additional_revenue` offsets if enabled.
6. Build an exogenous `other_interest` series if configured.
7. Compute the monthly primary deficit series used by the engine.
8. Project month-by-month:
   - Accrue interest on existing stock at the given rates.
   - Redeem maturing debt (decay), compute redemptions.
   - Compute GFN = primary deficit + interest + redemptions (plus any `other_interest`).
   - Issue new debt in the target shares to meet GFN; update the stock levels.
9. Write a monthly trace with stocks, accrual interest, other interest, redemptions, and issuance shares.
10. Annualize results to FY and CY, computing interest as a share of GDP.
11. Write overview and annual spreadsheets and optional diagnostics.

## Outputs

Under `output/<run_id>/`:

- `fiscal_year/spreadsheets/annual.csv`
- `calendar_year/spreadsheets/annual.csv`
  - Minimal rollups: `year, interest, gdp, pct_gdp` (+ `additional_revenue` when enabled)
- `fiscal_year/spreadsheets/overview.csv`
- `calendar_year/spreadsheets/overview.csv`
  - Dashboard view per year with: GDP level/growth; revenue/outlays and %GDP; primary deficit and %GDP; additional revenue; interest expense and %GDP; effective rate; PCE inflation.
- `diagnostics/` (selected):
  - `monthly_trace.parquet` (or `.csv` fallback)
  - `rates_preview.csv`, `issuance_preview.csv`
  - `deficits_preview.csv`, `deficits_preview_annual.csv`
  - QA: historical vs forward breakdowns, effective rates, stocks diagnostics
  - `config_echo.json` and `config_echo.yaml`

Note on interest alignment:
- The annual rollups add `other_interest` to `interest_total` just before annualization to reflect total interest burden in `annual.csv`.
- The overview spreadsheets intentionally use the engine’s `interest_total` as-is so they match `annual.csv` and avoid double-counting `other_interest`.

## Architecture

- `scripts/run_forward.py`: orchestrates the run, writes outputs/diagnostics.
- `src/engine/`: monthly projection engine
  - `project.py`: main loop, budget identity, issuance, state updates
  - `state.py`, `accrual.py`, `transitions.py`
- `src/macro/`: inputs and series builders
  - `config.py`: YAML parsing/validation and normalized echo
  - `gdp.py`, `budget.py`, `rates.py`, `issuance.py`, `additional_revenue.py`, `other_interest.py`
- `src/annualize.py`: FY/CY aggregation and `overview.csv` writer
- `src/diagnostics/`: QA, UAT, performance tooling

## Testing

```bash
make test
```

## Troubleshooting

- Mismatched years or missing series: check `output/<run_id>/diagnostics/config_echo.json` and the various `*_preview.csv` files to ensure your paths and frames match.
- Interest %GDP discrepancies between `annual.csv` and `overview.csv`: confirm that `overview.csv` is not adding `other_interest` on top of `interest_total` (the code is designed to avoid double-counting).
- Missing parquet support: the engine will fall back to CSV for the monthly trace.
- YAML errors: see exceptions; keys and shapes are validated in `src/macro/config.py`.

## License

Proprietary — internal use only unless stated otherwise.
