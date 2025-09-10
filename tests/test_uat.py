from __future__ import annotations

from pathlib import Path
import json

import pandas as pd

from diagnostics.uat import run_uat


def _write_minimal_macro(tmp: Path) -> Path:
    yml = tmp / "macro.yaml"
    yml.write_text(
        """
anchor_date: 2024-09-01
horizon_months: 12
gdp:
  anchor_fy: 2024
  anchor_value_usd_millions: 30000000
deficits:
  frame: FY
rates:
  type: constant
  values:
    short: 0.03
    nb: 0.04
    tips: 0.02
issuance_default_shares:
  short: 0.2
  nb: 0.7
  tips: 0.1
""",
        encoding="utf-8",
    )
    return yml


def _write_minimal_monthly(tmp: Path) -> Path:
    # 12 months with simple stocks and interest
    dates = pd.date_range("2024-09-01", periods=12, freq="MS")
    df = pd.DataFrame(
        {
            "date": dates,
            "stock_short": 1000.0,
            "stock_nb": 5000.0,
            "stock_tips": 1000.0,
            "interest_short": 1000.0 * 0.03 / 12.0,
            "interest_nb": 5000.0 * 0.04 / 12.0,
            "interest_tips": 1000.0 * 0.02 / 12.0,
            "interest_total": (1000.0 * 0.03 / 12.0) + (5000.0 * 0.04 / 12.0) + (1000.0 * 0.02 / 12.0),
            "other_interest": 0.0,
            "shares_short": 0.2,
            "shares_nb": 0.7,
            "shares_tips": 0.1,
            "gfn": 0.0,
            "redemptions_short": 1000.0,
            "redemptions_nb": 50.0,
            "redemptions_tips": 10.0,
            "redemptions_total": 1060.0,
        }
    )
    (tmp).mkdir(parents=True, exist_ok=True)
    out = tmp / "monthly_trace.csv"
    df.to_csv(out, index=False)
    return out


def _write_annual(tmp: Path, kind: str) -> Path:
    # Make annual tables with GDP columns and interest
    if kind == "CY":
        p = tmp / "calendar_year" / "spreadsheets" / "annual.csv"
    else:
        p = tmp / "fiscal_year" / "spreadsheets" / "annual.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"year": [2024, 2025], "interest": [1000.0, 1100.0], "gdp": [30000000.0, 30300000.0]})
    df.to_csv(p, index=False)
    return p


def _write_bridge(tmp: Path) -> Path:
    p = tmp / "output" / "diagnostics" / "bridge_table.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        {
            "fy_from": [2024],
            "fy_to": [2025],
            "delta_interest": [100.0],
            "stock_effect": [40.0],
            "rate_effect": [30.0],
            "mix_term_effect": [20.0],
            "tips_accretion": [0.0],
            "other_effect": [10.0],
        }
    )
    df.to_csv(p, index=False)
    return p


def _write_calibration_matrix(tmp: Path) -> Path:
    p = tmp / "output" / "diagnostics" / "calibration_matrix.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"date": ["2024-08-01", "2024-09-01"], "y": [10.0, 10.5], "SHORT": [1.0, 1.0], "NB": [2.0, 2.1], "TIPS": [0.5, 0.5]})
    df.to_csv(p, index=False)
    return p


def _write_parameters(tmp: Path) -> Path:
    p = tmp / "output" / "parameters.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump({"issuance_shares": {"short": 0.2, "nb": 0.7, "tips": 0.1}}, f)
    return p


def test_run_uat_minimal(tmp_path: Path, monkeypatch):
    # Arrange directory structure under tmp_path
    macro = _write_minimal_macro(tmp_path)

    # Place outputs under tmp/output like real layout
    out_dir = tmp_path / "output"
    out_dir.mkdir(exist_ok=True)
    monthly = _write_minimal_monthly(out_dir / "diagnostics")
    cy = _write_annual(out_dir, "CY")
    fy = _write_annual(out_dir, "FY")
    _write_bridge(tmp_path)
    _write_calibration_matrix(tmp_path)
    _write_parameters(tmp_path)

    # Act
    checklist_path = run_uat(
        config_path=macro,
        monthly_trace_path=monthly,
        annual_cy_path=cy,
        annual_fy_path=fy,
        bridge_table_path=tmp_path / "output" / "diagnostics" / "bridge_table.csv",
        calibration_matrix_path=tmp_path / "output" / "diagnostics" / "calibration_matrix.csv",
        parameters_path=tmp_path / "output" / "parameters.json",
        out_path=tmp_path / "output" / "diagnostics" / "uat_checklist.json",
    )

    # Assert
    assert checklist_path.exists()
    payload = json.loads(checklist_path.read_text(encoding="utf-8"))
    checks = payload.get("checks", {})
    assert checks.get("gdp_anchor_matches") is True
    assert checks.get("annual_has_gdp_columns") is True
    assert checks.get("bridge_sums_to_delta") is True
    assert checks.get("calibration_matrix_valid") is True
    assert checks.get("parameters_within_bounds") is True
    assert checks.get("monthly_trace_fields_present") is True
    assert checks.get("cli_outputs_present") is True


