from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# Ensure 'src' is on sys.path when invoked via subprocess
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from macro.config import load_macro_yaml, write_config_echo
from core.run_dir import create_run_directory
from core.logging_utils import setup_run_logger, get_git_sha, log_run_start, log_run_end
from macro.rates import build_month_index, ConstantRatesProvider, write_rates_preview
from macro.issuance import FixedSharesPolicy, write_issuance_preview
from engine.state import DebtState
from engine.project import ProjectionEngine
from annualize import annualize, write_annual_csvs
from macro.gdp import build_gdp_function
from diagnostics.qa import run_qa
from diagnostics.uat import run_uat


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="input/macro.yaml")
    ap.add_argument("--golden", action="store_true", help="Run short horizon (12 months)")
    ap.add_argument("--diagnostics", action="store_true", help="Write QA visuals and bridge")
    ap.add_argument("--dry-run", action="store_true", help="Parse config and exit (no run)")
    ap.add_argument("--perf", action="store_true", help="Run full-horizon performance profile")
    ap.add_argument("--debug", action="store_true", help="Enable DEBUG logging for this run")
    ap.add_argument("--outdir", default=None, help="Override output directory (for tests)")
    ap.add_argument("--uat", action="store_true", help="Run UAT checklist and write JSON report")
    args = ap.parse_args()

    cfg = load_macro_yaml(args.config)
    # Create timestamped run directory (or use override) and setup logging (T1, T2)
    base_out = args.outdir or "output"
    run_dir = create_run_directory(base_output_dir=base_out)
    logger = setup_run_logger(run_dir / "run_forward.log", debug=args.debug)
    log_run_start(logger, run_dir=run_dir, config_path=args.config, git_sha=get_git_sha())
    write_config_echo(cfg, out_path=run_dir / "diagnostics" / "config_echo.json")

    if args.dry_run:
        print("DRY RUN OK: config parsed, anchor=", cfg.anchor_date, "horizon=", cfg.horizon_months)
        log_run_end(logger, status="dry-run")
        return

    horizon = 12 if args.golden else cfg.horizon_months
    idx = build_month_index(cfg.anchor_date, horizon)

    # Providers
    if cfg.rates_constant is None:
        raise SystemExit("macro.yaml must provide constant rates for this step")
    rp = ConstantRatesProvider({"short": cfg.rates_constant[0], "nb": cfg.rates_constant[1], "tips": cfg.rates_constant[2]})
    write_rates_preview(rp, idx, out_path=str(run_dir / "diagnostics" / "rates_preview.csv"))

    # Issuance shares: use fitted if present; else config defaults
    params_path = run_dir / "parameters.json"
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
    write_issuance_preview(issuance, idx, out_path=str(run_dir / "diagnostics" / "issuance_preview.csv"))

    # Start state from latest stocks (scaled) month. If scaled stocks are missing, build them
    # from MSPD outstanding and scale to FY interest totals using config rates.
    scaled_path = run_dir / "diagnostics" / "outstanding_by_bucket_scaled.csv"
    if not scaled_path.exists():
        try:
            # Build outstanding by bucket from MSPD
            from calibration.stocks import (
                find_latest_mspd_file,
                build_outstanding_by_bucket_from_mspd,
                write_stocks_diagnostic,
                scale_stocks_for_calibration,
                write_scaled_stocks_diagnostic,
            )
            from calibration.matrix import (
                find_latest_interest_file,
                load_interest_raw,
                build_monthly_by_category,
                build_fy_totals,
                build_cy_totals,
                write_interest_diagnostics,
            )

            mspd_path = find_latest_mspd_file("input/MSPD_*.csv")
            stocks_raw = build_outstanding_by_bucket_from_mspd(mspd_path)
            # Write unscaled diagnostic for transparency
            write_stocks_diagnostic(stocks_raw, run_dir / "diagnostics" / "outstanding_by_bucket.csv")

            # Interest diagnostics to get FY totals
            int_path = find_latest_interest_file("input/IntExp_*")
            interest_raw = load_interest_raw(int_path)
            monthly_by_cat = build_monthly_by_category(interest_raw)
            fy_totals = build_fy_totals(monthly_by_cat)
            cy_totals = build_cy_totals(monthly_by_cat)
            # Also write interest diagnostics; useful for downstream steps
            write_interest_diagnostics(monthly_by_cat, fy_totals, cy_totals, out_dir=run_dir / "diagnostics")

            # Scale stocks so implied effective rate ~ target from config
            df_scaled, factor, implied_before = scale_stocks_for_calibration(
                stocks_raw, fy_totals, config_path=args.config
            )
            write_scaled_stocks_diagnostic(
                df_scaled,
                factor,
                out_csv=scaled_path,
                out_json=str(run_dir / "diagnostics" / "stock_rescale_report.json"),
                r_target=None,
                implied_before=implied_before,
                implied_after=None,
            )
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(f"Unable to build scaled stocks automatically: {exc}")

    stocks = pd.read_csv(scaled_path, parse_dates=["Record Date"]).sort_values("Record Date")
    last = stocks.iloc[-1]
    start_state = DebtState(stock_short=float(last["stock_short"]), stock_nb=float(last["stock_nb"]), stock_tips=float(last["stock_tips"]))

    # Simple deficits: zero for step 9 skeleton
    deficits = pd.Series(0.0, index=idx)

    # OTHER interest exogenous: set to zero here
    other = pd.Series(0.0, index=idx)

    engine = ProjectionEngine(rates_provider=rp, issuance_policy=issuance)
    df = engine.run(idx, start_state, deficits, other, trace_out_path=run_dir / "diagnostics" / "monthly_trace.parquet")
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
    p_cy, p_fy = write_annual_csvs(cy, fy, base_dir=str(run_dir))
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
            monthly_trace_path=run_dir / "diagnostics" / "monthly_trace.parquet",
            annual_cy_path=str(p_cy),
            annual_fy_path=str(p_fy),
            macro_path=args.config,
            out_base=str(run_dir),
        )
        print("Wrote QA:", p1, p2, p3)

    # Optional UAT checklist
    if args.uat:
        uat_path = run_uat(
            config_path=args.config,
            monthly_trace_path=run_dir / "diagnostics" / "monthly_trace.parquet",
            annual_cy_path=str(p_cy),
            annual_fy_path=str(p_fy),
            bridge_table_path=str(run_dir / "diagnostics" / "bridge_table.csv"),
            calibration_matrix_path=str(run_dir / "diagnostics" / "calibration_matrix.csv"),
            parameters_path=str(run_dir / "parameters.json"),
            out_path=str(run_dir / "diagnostics" / "uat_checklist.json"),
        )
        print("Wrote UAT checklist:", uat_path)

    # Optional performance profile over full horizon
    if args.perf:
        from diagnostics.perf import run_perf_profile

        perf_path = run_perf_profile(args.config, out_base=run_dir, stocks_path=scaled_path)
        print("Perf profile:", perf_path)

    log_run_end(logger, status="success")


if __name__ == "__main__":
    main()


