from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

import json
import math

import pandas as pd

from core.dates import fiscal_year
from macro.config import load_macro_yaml


def _read_monthly_trace(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if p.suffix.lower() == ".parquet" and p.exists():
        try:
            df = pd.read_parquet(p)
        except Exception:
            # fall back to CSV if parquet engine not available
            df = pd.read_csv(p.with_suffix(".csv"))
    else:
        if p.exists():
            df = pd.read_csv(p)
        elif p.with_suffix(".csv").exists():
            df = pd.read_csv(p.with_suffix(".csv"))
        else:
            raise FileNotFoundError(f"Monthly trace not found: {p}")
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"]).dt.to_period("M").dt.to_timestamp()
        df = df.set_index("date")
    else:
        df.index = pd.to_datetime(pd.DatetimeIndex(df.index)).to_period("M").to_timestamp()
        df.index.name = "date"
    return df


def _finite(x: float) -> bool:
    return not (math.isnan(float(x)) or math.isinf(float(x)))


def _find_col_case_insensitive(df: pd.DataFrame, name: str) -> str | None:
    lower = {c.lower(): c for c in df.columns}
    return lower.get(name.lower())


def run_uat(
    *,
    config_path: str | Path = "input/macro.yaml",
    monthly_trace_path: str | Path = "output/diagnostics/monthly_trace.parquet",
    annual_cy_path: str | Path = "output/calendar_year/spreadsheets/annual.csv",
    annual_fy_path: str | Path = "output/fiscal_year/spreadsheets/annual.csv",
    bridge_table_path: str | Path = "output/diagnostics/bridge_table.csv",
    calibration_matrix_path: str | Path = "output/diagnostics/calibration_matrix.csv",
    parameters_path: str | Path = "output/parameters.json",
    out_path: str | Path = "output/diagnostics/uat_checklist.json",
) -> Path:
    cfg = load_macro_yaml(config_path)

    # Load artifacts
    monthly = _read_monthly_trace(monthly_trace_path)
    cy = pd.read_csv(annual_cy_path)
    fy = pd.read_csv(annual_fy_path)

    # Helper for total interest including OTHER if present
    interest_total_col = "interest_total"
    if "other_interest" in monthly.columns:
        total_interest_series = (monthly[interest_total_col].astype(float) + monthly["other_interest"].astype(float)).astype(float)
    else:
        total_interest_series = monthly[interest_total_col].astype(float)

    checks: Dict[str, bool] = {}
    notes: Dict[str, object] = {}

    # 1) GDP anchor equals macro.yaml FY anchor
    row_anchor = fy.loc[fy["year"] == int(cfg.gdp_anchor_fy)]
    if not row_anchor.empty and "gdp" in row_anchor.columns:
        gdp_anchor_in_table = float(row_anchor.iloc[0]["gdp"])
        checks["gdp_anchor_matches"] = abs(gdp_anchor_in_table - float(cfg.gdp_anchor_value_usd_millions)) <= max(
            1e-6, 1e-6 * float(cfg.gdp_anchor_value_usd_millions)
        )
        notes["gdp_anchor_table"] = gdp_anchor_in_table
        notes["gdp_anchor_config"] = float(cfg.gdp_anchor_value_usd_millions)
        notes["gdp_anchor_fy"] = int(cfg.gdp_anchor_fy)
    else:
        checks["gdp_anchor_matches"] = False
        notes["gdp_anchor_error"] = "FY anchor row or gdp column missing in FY annual CSV"

    # 2) CY/FY denominators printed alongside numerators for 2 sample years
    checks["annual_has_gdp_columns"] = ("gdp" in cy.columns) and ("gdp" in fy.columns)
    # record sample pairs
    notes["annual_cy_samples"] = cy.head(2)[["year", "interest", "gdp"]].to_dict(orient="records") if "gdp" in cy.columns else []
    notes["annual_fy_samples"] = fy.head(2)[["year", "interest", "gdp"]].to_dict(orient="records") if "gdp" in fy.columns else []

    # 3) Splice continuity near anchor: MoM pct change reasonable around anchor window
    anchor_dt = pd.Timestamp(cfg.anchor_date).to_period("M").to_timestamp()
    window_mask = (monthly.index >= (anchor_dt - pd.offsets.MonthBegin(6))) & (monthly.index <= (anchor_dt + pd.offsets.MonthBegin(6)))
    series_win = total_interest_series.loc[window_mask].sort_index()
    mom = series_win.pct_change().abs().dropna()
    notes["splice_window_mom_abs_max"] = float(mom.max()) if not mom.empty else 0.0
    # threshold: allow up to 100% swing MoM; this is conservative but flags wild spikes
    checks["splice_continuity"] = bool((mom <= 1.0).all()) if not mom.empty else True

    # 4) Bridge table attribution sums to ΔInterest within rounding
    try:
        bridge = pd.read_csv(bridge_table_path)
        comp_cols = [c for c in ["stock_effect", "rate_effect", "mix_term_effect", "tips_accretion", "other_effect"] if c in bridge.columns]
        if not bridge.empty and "delta_interest" in bridge.columns and comp_cols:
            delta = float(bridge.iloc[0]["delta_interest"])
            components_sum = float(bridge.iloc[0][comp_cols].sum())
            tol = max(1.0, 1e-3 * abs(delta))
            checks["bridge_sums_to_delta"] = abs(components_sum - delta) <= tol
            notes["bridge_components_sum"] = components_sum
            notes["bridge_delta_interest"] = delta
        else:
            checks["bridge_sums_to_delta"] = False
            notes["bridge_error"] = "Missing delta_interest or components in bridge table"
    except FileNotFoundError:
        checks["bridge_sums_to_delta"] = False
        notes["bridge_error"] = "Bridge table not found"

    # 5) Calibration matrix has no NaNs; NB variance > 0
    try:
        calib = pd.read_csv(calibration_matrix_path)
        has_nans = calib.replace([float("inf"), -float("inf")], pd.NA).isna().any().any()
        nb_col = _find_col_case_insensitive(calib, "NB")
        nb_var_ok = float(calib[nb_col].var()) > 0.0 if nb_col is not None else False
        checks["calibration_matrix_valid"] = (not has_nans) and nb_var_ok
        notes["calibration_cols"] = list(calib.columns)
        notes["calibration_nb_variance"] = float(calib[nb_col].var()) if nb_col is not None else None
    except FileNotFoundError:
        checks["calibration_matrix_valid"] = False
        notes["calibration_error"] = "Calibration matrix not found"

    # 6) Parameters within bounds and documented
    try:
        with Path(parameters_path).open("r", encoding="utf-8") as f:
            params = json.load(f)
        s = params.get("issuance_shares", {})
        short = float(s.get("short", float("nan")))
        nb = float(s.get("nb", float("nan")))
        tips = float(s.get("tips", float("nan")))
        sums_to_one = _finite(short) and _finite(nb) and _finite(tips) and abs((short + nb + tips) - 1.0) <= 1e-3
        in_bounds = all(0.0 <= v <= 1.0 for v in (short, nb, tips))
        checks["parameters_within_bounds"] = bool(sums_to_one and in_bounds)
        notes["parameters_issuance_shares"] = {"short": short, "nb": nb, "tips": tips}
    except FileNotFoundError:
        checks["parameters_within_bounds"] = False
        notes["parameters_error"] = "parameters.json not found"

    # 7) monthly_trace row has all expected fields
    expected_fields = {
        "stock_short",
        "stock_nb",
        "stock_tips",
        "interest_short",
        "interest_nb",
        "interest_tips",
        "interest_total",
        "shares_short",
        "shares_nb",
        "shares_tips",
        "gfn",
        "redemptions_short",
        "redemptions_nb",
        "redemptions_tips",
        "redemptions_total",
    }
    has_fields = expected_fields.issubset(set(monthly.columns))
    checks["monthly_trace_fields_present"] = bool(has_fields)
    notes["monthly_trace_missing_fields"] = sorted(list(expected_fields - set(monthly.columns)))

    # 8) CLI full run finishes and writes all outputs (proxy: required artifacts exist)
    outputs_exist = all(Path(p).exists() for p in [monthly_trace_path, annual_cy_path, annual_fy_path])
    checks["cli_outputs_present"] = bool(outputs_exist)

    # Write checklist JSON
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "checks": checks,
        "notes": notes,
    }
    with out.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    return out


__all__ = ["run_uat"]


