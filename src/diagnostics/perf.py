from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd

from macro.config import load_macro_yaml
from macro.rates import build_month_index, ConstantRatesProvider
from macro.issuance import FixedSharesPolicy
from engine.state import DebtState
from engine.project import ProjectionEngine


def run_perf_profile(config_path: str | Path = "input/macro.yaml", *, out_base: str | Path | None = None, stocks_path: str | Path = "output/diagnostics/outstanding_by_bucket_scaled.csv") -> Path:
    cfg = load_macro_yaml(config_path)
    idx = build_month_index(cfg.anchor_date, cfg.horizon_months)

    if cfg.rates_constant is None:
        raise SystemExit("macro.yaml must provide constant rates for perf run")
    rp = ConstantRatesProvider({"short": cfg.rates_constant[0], "nb": cfg.rates_constant[1], "tips": cfg.rates_constant[2]})

    # Issuance: from parameters if present; else defaults
    params_path = Path("output/parameters.json")
    if params_path.exists():
        import json as _json

        s = _json.loads(params_path.read_text()).get("issuance_shares", {})
        issuance = FixedSharesPolicy(short=float(s.get("short", 0.2)), nb=float(s.get("nb", 0.7)), tips=float(s.get("tips", 0.1)))
    else:
        if cfg.issuance_default_shares is None:
            raise SystemExit("No parameters and no issuance_default_shares")
        short, nb, tips = cfg.issuance_default_shares
        issuance = FixedSharesPolicy(short=short, nb=nb, tips=tips)

    # Start state from latest scaled stocks; fall back to synthetic if not present
    try:
        stocks = pd.read_csv(stocks_path, parse_dates=["Record Date"]).sort_values("Record Date")
        last = stocks.iloc[-1]
        start_state = DebtState(stock_short=float(last["stock_short"]), stock_nb=float(last["stock_nb"]), stock_tips=float(last["stock_tips"]))
    except FileNotFoundError:
        # Synthesize a small starting state using issuance_default_shares if available
        base_total = 1e7
        if cfg.issuance_default_shares is not None:
            s, n, t = cfg.issuance_default_shares
        else:
            s, n, t = 0.2, 0.7, 0.1
        start_state = DebtState(stock_short=base_total * s, stock_nb=base_total * n, stock_tips=base_total * t)

    deficits = pd.Series(0.0, index=idx)
    engine = ProjectionEngine(rates_provider=rp, issuance_policy=issuance)

    t0 = time.perf_counter()
    trace_out = (Path(out_base) / "diagnostics" / "monthly_trace.parquet") if out_base is not None else None
    df = engine.run(idx, start_state, deficits, trace_out_path=trace_out)
    t1 = time.perf_counter()

    out = (Path(out_base) / "diagnostics" / "perf_profile.json") if out_base is not None else Path("output/diagnostics/perf_profile.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "months": int(len(idx)),
        "seconds": float(t1 - t0),
        "rows": int(len(df)),
        "cols": int(df.shape[1]),
    }, indent=2))
    return out


