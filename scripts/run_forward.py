from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from macro.config import load_macro_yaml, write_config_echo
from macro.rates import build_month_index, ConstantRatesProvider, write_rates_preview
from macro.issuance import FixedSharesPolicy, write_issuance_preview
from engine.state import DebtState
from engine.project import ProjectionEngine
from annualize import annualize, write_annual_csvs
from macro.gdp import build_gdp_function
from diagnostics.qa import run_qa


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="input/macro.yaml")
    ap.add_argument("--golden", action="store_true", help="Run short horizon (12 months)")
    ap.add_argument("--diagnostics", action="store_true", help="Write QA visuals and bridge")
    ap.add_argument("--dry-run", action="store_true", help="Parse config and exit (no run)")
    args = ap.parse_args()

    cfg = load_macro_yaml(args.config)
    write_config_echo(cfg)

    if args.dry_run:
        print("DRY RUN OK: config parsed, anchor=", cfg.anchor_date, "horizon=", cfg.horizon_months)
        return

    horizon = 12 if args.golden else cfg.horizon_months
    idx = build_month_index(cfg.anchor_date, horizon)

    # Providers
    if cfg.rates_constant is None:
        raise SystemExit("macro.yaml must provide constant rates for this step")
    rp = ConstantRatesProvider({"short": cfg.rates_constant[0], "nb": cfg.rates_constant[1], "tips": cfg.rates_constant[2]})
    write_rates_preview(rp, idx)

    # Issuance shares: use fitted if present; else config defaults
    params_path = Path("output/parameters.json")
    if params_path.exists():
        import json

        with params_path.open("r", encoding="utf-8") as f:
            params = json.load(f)
        s = params.get("issuance_shares", {})
        issuance = FixedSharesPolicy(short=float(s.get("short", 0.2)), nb=float(s.get("nb", 0.7)), tips=float(s.get("tips", 0.1)))
    else:
        if cfg.issuance_default_shares is None:
            raise SystemExit("No parameters.json and no issuance_default_shares in macro.yaml")
        short, nb, tips = cfg.issuance_default_shares
        issuance = FixedSharesPolicy(short=short, nb=nb, tips=tips)
    write_issuance_preview(issuance, idx)

    # Start state from latest stocks (scaled) month
    stocks = pd.read_csv("output/diagnostics/outstanding_by_bucket_scaled.csv", parse_dates=["Record Date"]).sort_values("Record Date")
    last = stocks.iloc[-1]
    start_state = DebtState(stock_short=float(last["stock_short"]), stock_nb=float(last["stock_nb"]), stock_tips=float(last["stock_tips"]))

    # Simple deficits: zero for step 9 skeleton
    deficits = pd.Series(0.0, index=idx)

    # OTHER interest exogenous: set to zero here
    other = pd.Series(0.0, index=idx)

    engine = ProjectionEngine(rates_provider=rp, issuance_policy=issuance)
    df = engine.run(idx, start_state, deficits, other)
    print(df.head(3))
    print(df.tail(3))

    # Step 11: Annualization & % of GDP
    # Build GDP model; if macro.yaml lacks forward growth, assume 0 growth for required years
    # Determine required FY/CY years from the projection index
    years_needed = sorted(set([d.year for d in idx] + [d.year + 1 for d in idx]))
    anchor_fy = pd.Timestamp(cfg.anchor_date).year if hasattr(cfg, "anchor_date") else idx[0].year
    growth_fy = {y: 0.0 for y in years_needed if y >= anchor_fy}
    gdp_model = build_gdp_function(cfg.anchor_date, cfg.gdp_anchor_value_usd_millions, growth_fy)

    # Use interest including OTHER for totals
    monthly_for_annual = df.copy()
    monthly_for_annual = monthly_for_annual.assign(interest_total=monthly_for_annual["interest_total"] + monthly_for_annual.get("other_interest", 0.0))
    cy, fy = annualize(monthly_for_annual, gdp_model)
    p_cy, p_fy = write_annual_csvs(cy, fy)
    print("Wrote annual CSVs:", p_cy, p_fy)

    # Optional diagnostics & visuals
    if args.diagnostics:
        # Ensure headless backend
        try:
            import matplotlib

            matplotlib.use("Agg")
        except Exception:
            pass
        p1, p2, p3 = run_qa(
            monthly_trace_path="output/diagnostics/monthly_trace.parquet",
            annual_cy_path=str(p_cy),
            annual_fy_path=str(p_fy),
            macro_path=args.config,
        )
        print("Wrote QA:", p1, p2, p3)


if __name__ == "__main__":
    main()


