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

    # Frame for budget inputs (revenue/outlays shares)
    budget_frame: FiscalFrame

    # Annual revenue and primary outlays as percent of GDP by year (percent, not decimal)
    # Interpreted in the frame specified by budget_frame
    budget_annual_revenue_pct_gdp: Dict[int, float]
    budget_annual_outlays_pct_gdp: Dict[int, float]

    # Additional revenue offset (optional)
    # mode: "pct_gdp" or "level"; values keyed by FY/CY year based on deficits_frame
    additional_revenue_mode: Optional[Literal["pct_gdp", "level"]] = None
    additional_revenue_annual_pct_gdp: Optional[Dict[int, float]] = None
    additional_revenue_annual_level_usd_millions: Optional[Dict[int, float]] = None
    additional_revenue_enabled: bool = False

    # Inflation indexing inputs (optional)
    # Top-level inflation series (percent, not decimals): {FY: pct}
    inflation_pce: Optional[Dict[int, float]] = None
    inflation_cpi: Optional[Dict[int, float]] = None

    # Additional revenue anchor/index configuration (optional)
    additional_revenue_anchor_year: Optional[int] = None
    additional_revenue_anchor_amount: Optional[float] = None
    additional_revenue_index: Optional[Literal["none", "pce", "cpi"]] = None

    # Other interest (exogenous add-on to interest), default enabled
    other_interest_enabled: bool = True
    other_interest_frame: Optional[FiscalFrame] = None
    other_interest_annual_pct_gdp: Optional[Dict[int, float]] = None
    other_interest_annual_usd_mn: Optional[Dict[int, float]] = None

    # Issuance shares transition (default ON)
    issuance_transition_enabled: bool = True
    issuance_transition_months: int = 6

    # Optional default issuance shares to validate early (SHORT/NB/TIPS)
    issuance_default_shares: Optional[Tuple[float, float, float]] = None

    # Optional constant rates for early validation (annualized, decimals)
    rates_constant: Optional[Tuple[float, float, float]] = None

    # Optional FY-based GDP growth map (percent, not decimals): {FY: pct}
    gdp_annual_fy_growth_rate: Optional[Dict[int, float]] = None

    # Optional FY-based variable rates (percent, not decimals): {bucket: {FY: pct}}
    # bucket keys normalized to lowercase: short, nb, tips
    variable_rates_annual: Optional[Dict[str, Dict[int, float]]] = None

    # Back-compat property aliases (read-only) to ease transition within codebase
    @property
    def deficits_frame(self) -> FiscalFrame:  # alias for legacy callers
        return self.budget_frame

    def to_normalized_dict(self) -> Dict[str, object]:
        data = asdict(self)
        data["anchor_date"] = self.anchor_date.isoformat()
        data["units"] = {"currency": "USD", "scale": "millions"}
        # Emit inflation block for transparency
        if self.inflation_pce is not None or self.inflation_cpi is not None:
            infl: Dict[str, object] = {}
            if self.inflation_pce is not None:
                infl["pce"] = {int(k): float(v) for k, v in self.inflation_pce.items()}
            if self.inflation_cpi is not None:
                infl["cpi"] = {int(k): float(v) for k, v in self.inflation_cpi.items()}
            data["inflation"] = infl
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
        # Nest budget fields for readability
        if self.budget_frame is not None:
            budget_block: Dict[str, object] = {"frame": self.budget_frame}
            if self.budget_annual_revenue_pct_gdp is not None:
                budget_block["annual_revenue_pct_gdp"] = {int(k): float(v) for k, v in self.budget_annual_revenue_pct_gdp.items()}
            if self.budget_annual_outlays_pct_gdp is not None:
                budget_block["annual_outlays_pct_gdp"] = {int(k): float(v) for k, v in self.budget_annual_outlays_pct_gdp.items()}
            # Nest additional_revenue if configured
            if self.additional_revenue_mode is not None or self.additional_revenue_enabled:
                add_rev: Dict[str, object] = {"enabled": bool(self.additional_revenue_enabled)}
                if self.additional_revenue_mode is not None:
                    add_rev["mode"] = self.additional_revenue_mode
                if self.additional_revenue_mode == "pct_gdp" and self.additional_revenue_annual_pct_gdp is not None:
                    add_rev["annual_pct_gdp"] = {int(k): float(v) for k, v in self.additional_revenue_annual_pct_gdp.items()}
                if self.additional_revenue_mode == "level" and self.additional_revenue_annual_level_usd_millions is not None:
                    add_rev["annual_level_usd_millions"] = {int(k): float(v) for k, v in self.additional_revenue_annual_level_usd_millions.items()}
                # Anchor/index fields
                if self.additional_revenue_anchor_year is not None:
                    add_rev["anchor_year"] = int(self.additional_revenue_anchor_year)
                if self.additional_revenue_anchor_amount is not None:
                    add_rev["anchor_amount"] = float(self.additional_revenue_anchor_amount)
                if self.additional_revenue_index is not None:
                    add_rev["index"] = self.additional_revenue_index
                budget_block["additional_revenue"] = add_rev
            data["budget"] = budget_block
        # Nest other_interest for readability
        other_block: Dict[str, object] = {"enabled": self.other_interest_enabled}
        if self.other_interest_frame is not None:
            other_block["frame"] = self.other_interest_frame
        if self.other_interest_annual_pct_gdp is not None:
            other_block["annual_pct_gdp"] = {int(k): float(v) for k, v in self.other_interest_annual_pct_gdp.items()}
        if self.other_interest_annual_usd_mn is not None:
            other_block["annual_usd_mn"] = {int(k): float(v) for k, v in self.other_interest_annual_usd_mn.items()}
        data["other_interest"] = other_block
        # Issuance transition block
        data["issuance_shares_transition"] = {
            "enabled": self.issuance_transition_enabled,
            "months": int(self.issuance_transition_months),
        }
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

    budget = raw.get("budget")
    if not isinstance(budget, dict) or "frame" not in budget:
        raise ValueError("budget.frame must be provided and be 'FY' or 'CY'")
    frame = str(budget["frame"]).upper()
    if frame not in {"FY", "CY"}:
        raise ValueError("budget.frame must be 'FY' or 'CY'")

    # Revenue and outlays shares (required)
    if not isinstance(budget.get("annual_revenue_pct_gdp"), dict):
        raise ValueError("budget.annual_revenue_pct_gdp must be provided as a mapping")
    if not isinstance(budget.get("annual_outlays_pct_gdp"), dict):
        raise ValueError("budget.annual_outlays_pct_gdp must be provided as a mapping")
    budget_annual_revenue_pct_gdp = _validate_fy_growth_map(budget["annual_revenue_pct_gdp"], field="budget.annual_revenue_pct_gdp")
    budget_annual_outlays_pct_gdp = _validate_fy_growth_map(budget["annual_outlays_pct_gdp"], field="budget.annual_outlays_pct_gdp")

    # Additional revenue parsing (optional)
    additional_revenue_mode: Optional[Literal["pct_gdp", "level"]] = None
    additional_revenue_annual_pct_gdp: Optional[Dict[int, float]] = None
    additional_revenue_annual_level_usd_millions: Optional[Dict[int, float]] = None
    additional_revenue_enabled: bool = False
    # Anchor/index fields
    additional_revenue_anchor_year: Optional[int] = None
    additional_revenue_anchor_amount: Optional[float] = None
    additional_revenue_index: Optional[Literal["none", "pce", "cpi"]] = None
    add_rev = budget.get("additional_revenue") if isinstance(budget, dict) else None
    if isinstance(add_rev, dict):
        if "enabled" in add_rev:
            try:
                additional_revenue_enabled = bool(add_rev.get("enabled", False))
            except Exception:  # noqa: BLE001
                additional_revenue_enabled = False
        mode_str = str(add_rev.get("mode", "")).strip().lower()
        if mode_str in {"pct_gdp", "level"}:
            additional_revenue_mode = mode_str  # type: ignore[assignment]
        elif mode_str:
            raise ValueError("budget.additional_revenue.mode must be 'pct_gdp' or 'level'")
        # Validate maps
        if isinstance(add_rev.get("annual_pct_gdp"), dict):
            additional_revenue_annual_pct_gdp = _validate_fy_growth_map(add_rev["annual_pct_gdp"], field="budget.additional_revenue.annual_pct_gdp")
        if isinstance(add_rev.get("annual_level_usd_millions"), dict):
            additional_revenue_annual_level_usd_millions = _validate_fy_growth_map(add_rev["annual_level_usd_millions"], field="budget.additional_revenue.annual_level_usd_millions")
        # Anchor/index (optional)
        if "anchor_year" in add_rev:
            try:
                additional_revenue_anchor_year = int(add_rev.get("anchor_year"))
            except Exception as exc:  # noqa: BLE001
                raise ValueError("budget.additional_revenue.anchor_year must be an integer") from exc
        if "anchor_amount" in add_rev:
            try:
                additional_revenue_anchor_amount = float(add_rev.get("anchor_amount"))
            except Exception as exc:  # noqa: BLE001
                raise ValueError("budget.additional_revenue.anchor_amount must be a number") from exc
            if not _finite(additional_revenue_anchor_amount):
                raise ValueError("budget.additional_revenue.anchor_amount must be finite")
        if "index" in add_rev:
            idx_val = str(add_rev.get("index", "")).strip().lower()
            if idx_val in {"none", "pce", "cpi"}:
                additional_revenue_index = idx_val  # type: ignore[assignment]
            elif idx_val:
                raise ValueError("budget.additional_revenue.index must be one of: none, PCE, CPI")
        # Exclusivity checks
        if additional_revenue_enabled:
            anchor_present = (
                additional_revenue_anchor_year is not None
                or additional_revenue_anchor_amount is not None
                or additional_revenue_index is not None
            )
            if anchor_present:
                # Require completeness of anchor triplet
                if additional_revenue_anchor_year is None or additional_revenue_anchor_amount is None or additional_revenue_index is None:
                    raise ValueError("additional_revenue anchor/index requires anchor_year, anchor_amount, and index together")
                # With anchor+index present, skip legacy map requirements
            else:
                # Legacy paths require corresponding maps
                if additional_revenue_mode == "pct_gdp" and additional_revenue_annual_pct_gdp is None:
                    raise ValueError("additional_revenue.mode is pct_gdp but annual_pct_gdp missing")
                if additional_revenue_mode == "level" and additional_revenue_annual_level_usd_millions is None:
                    raise ValueError("additional_revenue.mode is level but annual_level_usd_millions missing")
                if additional_revenue_mode is None and (additional_revenue_annual_pct_gdp or additional_revenue_annual_level_usd_millions):
                    raise ValueError("additional_revenue provided without a valid mode")
                if additional_revenue_annual_pct_gdp is not None and additional_revenue_annual_level_usd_millions is not None:
                    raise ValueError("Provide only one of annual_pct_gdp or annual_level_usd_millions for additional_revenue")

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

    # Other interest (optional block); default enabled when absent
    other_interest_enabled: bool = True
    other_interest_frame: Optional[FiscalFrame] = None
    other_interest_annual_pct_gdp: Optional[Dict[int, float]] = None
    other_interest_annual_usd_mn: Optional[Dict[int, float]] = None

    other = raw.get("other_interest")
    if isinstance(other, dict):
        if "enabled" in other:
            other_interest_enabled = bool(other.get("enabled", True))
        if "frame" in other:
            fr = str(other.get("frame", "")).upper()
            if fr in {"FY", "CY"}:
                other_interest_frame = fr  # type: ignore[assignment]
        if isinstance(other.get("annual_pct_gdp"), dict):
            other_interest_annual_pct_gdp = _validate_fy_growth_map(other["annual_pct_gdp"], field="other_interest.annual_pct_gdp")
        if isinstance(other.get("annual_usd_mn"), dict):
            # USD millions directly; validate finite via growth map helper reuse
            other_interest_annual_usd_mn = _validate_fy_growth_map(other["annual_usd_mn"], field="other_interest.annual_usd_mn")

    # Issuance transition (optional); default enabled
    issuance_transition_enabled = True
    issuance_transition_months = 6
    trans = raw.get("issuance_shares_transition")
    if isinstance(trans, dict):
        if "enabled" in trans:
            issuance_transition_enabled = bool(trans.get("enabled", True))
        if "months" in trans:
            try:
                issuance_transition_months = max(1, int(trans.get("months", 6)))
            except Exception:  # noqa: BLE001
                issuance_transition_months = 6

    # Inflation block (optional, top-level)
    inflation_pce: Optional[Dict[int, float]] = None
    inflation_cpi: Optional[Dict[int, float]] = None
    if isinstance(raw.get("inflation"), dict):
        infl = raw.get("inflation")
        if isinstance(infl.get("pce"), dict):
            inflation_pce = _validate_fy_growth_map(infl["pce"], field="inflation.pce")  # type: ignore[index]
        if isinstance(infl.get("cpi"), dict):
            inflation_cpi = _validate_fy_growth_map(infl["cpi"], field="inflation.cpi")  # type: ignore[index]

    return MacroConfig(
        anchor_date=anchor_date,
        horizon_months=horizon_months,
        gdp_anchor_fy=gdp_anchor_fy,
        gdp_anchor_value_usd_millions=gdp_anchor_value,
        budget_frame=frame,  # type: ignore[arg-type]
        budget_annual_revenue_pct_gdp=budget_annual_revenue_pct_gdp,
        budget_annual_outlays_pct_gdp=budget_annual_outlays_pct_gdp,
        additional_revenue_mode=additional_revenue_mode,
        additional_revenue_annual_pct_gdp=additional_revenue_annual_pct_gdp,
        additional_revenue_annual_level_usd_millions=additional_revenue_annual_level_usd_millions,
        additional_revenue_enabled=additional_revenue_enabled,
        additional_revenue_anchor_year=additional_revenue_anchor_year,
        additional_revenue_anchor_amount=additional_revenue_anchor_amount,
        additional_revenue_index=additional_revenue_index,  # type: ignore[arg-type]
        inflation_pce=inflation_pce,
        inflation_cpi=inflation_cpi,
        other_interest_enabled=other_interest_enabled,
        other_interest_frame=other_interest_frame,  # type: ignore[arg-type]
        other_interest_annual_pct_gdp=other_interest_annual_pct_gdp,
        other_interest_annual_usd_mn=other_interest_annual_usd_mn,
        issuance_transition_enabled=issuance_transition_enabled,
        issuance_transition_months=issuance_transition_months,
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



