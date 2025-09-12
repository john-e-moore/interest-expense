from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Literal, Optional, Tuple

import json
import math
import os

import yaml


FiscalFrame = Literal["FY", "CY"]


@dataclass(frozen=True)
class MacroConfig:
    """Canonical macro configuration used across the project.

    All currency units are USD millions.
    """

    anchor_date: date
    horizon_months: int

    # GDP anchoring
    gdp_anchor_fy: int
    gdp_anchor_value_usd_millions: float

    # Frame for deficits and reporting inputs
    deficits_frame: FiscalFrame

    # Optional default issuance shares to validate early (SHORT/NB/TIPS)
    issuance_default_shares: Optional[Tuple[float, float, float]] = None

    # Optional constant rates for early validation (annualized, decimals)
    rates_constant: Optional[Tuple[float, float, float]] = None

    # Optional FY-based GDP growth map (percent, not decimals): {FY: pct}
    gdp_annual_fy_growth_rate: Optional[Dict[int, float]] = None

    # Optional FY-based variable rates (percent, not decimals): {bucket: {FY: pct}}
    # bucket keys normalized to lowercase: short, nb, tips
    variable_rates_annual: Optional[Dict[str, Dict[int, float]]] = None

    def to_normalized_dict(self) -> Dict[str, object]:
        data = asdict(self)
        data["anchor_date"] = self.anchor_date.isoformat()
        data["units"] = {"currency": "USD", "scale": "millions"}
        # Name issuance keys for readability
        if self.issuance_default_shares is not None:
            s, n, t = self.issuance_default_shares
            data["issuance_default_shares"] = {"short": s, "nb": n, "tips": t}
        if self.rates_constant is not None:
            bs, nb, tips = self.rates_constant
            data["rates_constant"] = {"short": bs, "nb": nb, "tips": tips}
        # Keep FY growth and variable rates as provided (percent), with normalized keys
        if self.gdp_annual_fy_growth_rate is not None:
            data["gdp_annual_fy_growth_rate"] = {int(k): float(v) for k, v in self.gdp_annual_fy_growth_rate.items()}
        if self.variable_rates_annual is not None:
            vr: Dict[str, Dict[int, float]] = {}
            for k, m in self.variable_rates_annual.items():
                vr[k] = {int(yy): float(val) for yy, val in m.items()}
            data["variable_rates_annual"] = vr
        return data


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _parse_date(value: object, field_name: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).date()
        except ValueError as exc:
            raise ValueError(f"{field_name} must be ISO date (YYYY-MM-DD), got {value!r}") from exc
    raise ValueError(f"{field_name} must be a date string")


def _finite(value: float) -> bool:
    return not (math.isnan(value) or math.isinf(value))


def _validate_shares(shares: Dict[str, object]) -> Tuple[float, float, float]:
    required = ("short", "nb", "tips")
    missing = [k for k in required if k not in shares]
    if missing:
        raise ValueError(f"issuance_default_shares missing keys: {missing}")
    short = float(shares["short"])  # type: ignore[arg-type]
    nb = float(shares["nb"])  # type: ignore[arg-type]
    tips = float(shares["tips"])  # type: ignore[arg-type]
    for name, v in ("short", short), ("nb", nb), ("tips", tips):
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"share {name} out of bounds [0,1]: {v}")
    total = short + nb + tips
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"shares must sum to 1.0 (±1e-6), got {total}")
    return short, nb, tips


def _validate_rates_constant(values: Dict[str, object]) -> Tuple[float, float, float]:
    required = ("short", "nb", "tips")
    missing = [k for k in required if k not in values]
    if missing:
        raise ValueError(f"rates_constant missing keys: {missing}")
    short = float(values["short"])  # type: ignore[arg-type]
    nb = float(values["nb"])  # type: ignore[arg-type]
    tips = float(values["tips"])  # type: ignore[arg-type]
    for name, v in ("short", short), ("nb", nb), ("tips", tips):
        if not _finite(v):
            raise ValueError(f"rate {name} not finite: {v}")
    return short, nb, tips


def _validate_fy_growth_map(values: Dict[object, object], *, field: str) -> Dict[int, float]:
    if not isinstance(values, dict):
        raise ValueError(f"{field} must be a mapping of FY->percent")
    out: Dict[int, float] = {}
    for k, v in values.items():
        try:
            year = int(k)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"{field} keys must be integers (FY years), got {k!r}") from exc
        val = float(v)  # type: ignore[arg-type]
        if not _finite(val):
            raise ValueError(f"{field}[{year}] must be finite, got {val}")
        out[year] = val
    return out


def _validate_variable_rates_annual(values: Dict[str, object]) -> Dict[str, Dict[int, float]]:
    if not isinstance(values, dict):
        raise ValueError("variable_rates_annual must be a mapping of bucket->{FY->percent}")
    out: Dict[str, Dict[int, float]] = {}
    for bucket, mapping in values.items():
        if not isinstance(mapping, dict):
            raise ValueError(f"variable_rates_annual[{bucket!r}] must be a mapping of FY->percent")
        key = str(bucket).lower()
        if key not in {"short", "nb", "tips"}:
            # Allow forward-compat; accept unknown keys but keep normalized
            key = key
        out[key] = _validate_fy_growth_map(mapping, field=f"variable_rates_annual[{key}]")
    return out


def load_macro_yaml(path: os.PathLike[str] | str) -> MacroConfig:
    """Load and validate macro configuration from YAML.

    Returns a MacroConfig with canonicalized fields and units assumptions.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config YAML not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    if not isinstance(raw, dict):
        raise ValueError("Top-level YAML must be a mapping/dict")

    # Required
    anchor_date = _parse_date(raw.get("anchor_date"), "anchor_date")
    horizon_months = int(raw.get("horizon_months", 0))
    if horizon_months <= 0:
        raise ValueError("horizon_months must be a positive integer")

    gdp = raw.get("gdp")
    if not isinstance(gdp, dict):
        raise ValueError("gdp section must be provided as a mapping")
    try:
        gdp_anchor_fy = int(gdp.get("anchor_fy"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("gdp.anchor_fy must be an integer") from exc
    gdp_anchor_value = float(gdp.get("anchor_value_usd_millions", 0.0))
    if not _finite(gdp_anchor_value) or gdp_anchor_value <= 0:
        raise ValueError("gdp.anchor_value_usd_millions must be positive and finite")

    gdp_annual_fy_growth_rate: Optional[Dict[int, float]] = None
    if isinstance(gdp.get("annual_fy_growth_rate"), dict):
        gdp_annual_fy_growth_rate = _validate_fy_growth_map(
            gdp["annual_fy_growth_rate"], field="gdp.annual_fy_growth_rate"  # type: ignore[index]
        )

    deficits = raw.get("deficits")
    if not isinstance(deficits, dict) or "frame" not in deficits:
        raise ValueError("deficits.frame must be provided and be 'FY' or 'CY'")
    frame = str(deficits["frame"]).upper()
    if frame not in {"FY", "CY"}:
        raise ValueError("deficits.frame must be 'FY' or 'CY'")

    # Optional validations
    issuance_default_shares: Optional[Tuple[float, float, float]] = None
    if isinstance(raw.get("issuance_default_shares"), dict):
        issuance_default_shares = _validate_shares(raw["issuance_default_shares"])  # type: ignore[index]

    rates_constant: Optional[Tuple[float, float, float]] = None
    rates = raw.get("rates")
    if isinstance(rates, dict) and rates.get("type") == "constant":
        values = rates.get("values")
        if not isinstance(values, dict):
            raise ValueError("rates.values must be a mapping when type is 'constant'")
        rates_constant = _validate_rates_constant(values)

    # Optional FY-based variable rates (percent)
    variable_rates_annual: Optional[Dict[str, Dict[int, float]]] = None
    if isinstance(raw.get("variable_rates_annual"), dict):
        variable_rates_annual = _validate_variable_rates_annual(raw["variable_rates_annual"])  # type: ignore[index]

    return MacroConfig(
        anchor_date=anchor_date,
        horizon_months=horizon_months,
        gdp_anchor_fy=gdp_anchor_fy,
        gdp_anchor_value_usd_millions=gdp_anchor_value,
        deficits_frame=frame,  # type: ignore[arg-type]
        issuance_default_shares=issuance_default_shares,
        rates_constant=rates_constant,
        gdp_annual_fy_growth_rate=gdp_annual_fy_growth_rate,
        variable_rates_annual=variable_rates_annual,
    )


def write_config_echo(config: MacroConfig, out_path: os.PathLike[str] | str = "output/diagnostics/config_echo.json") -> Path:
    """Write normalized config echo JSON for diagnostics and auditing."""
    out = Path(out_path)
    _ensure_dir(out.parent)
    with out.open("w", encoding="utf-8") as f:
        json.dump(config.to_normalized_dict(), f, indent=2, sort_keys=True)
    return out



