from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

import json
import numpy as np
import pandas as pd
from scipy.optimize import minimize, LinearConstraint, Bounds


def calibrate_shares(X: np.ndarray, y: np.ndarray, tip_cap: float = 0.20) -> Tuple[np.ndarray, Dict[str, float]]:
    """
    Constrained least-squares fit of constant issuance shares s = (s_short, s_nb, s_tips)
    to minimize ||X s - y||^2 with:
      - s >= 0
      - sum(s) = 1
      - bounds: SHORT∈[0.05,0.60], NB∈[0.05,0.85], TIPS∈[0.00,tip_cap]

    Returns (s, diagnostics).
    """
    assert X.ndim == 2 and X.shape[1] == 3, "X must be (n,3) for SHORT, NB, TIPS"
    assert y.ndim == 1 and y.shape[0] == X.shape[0], "y must align with X rows"

    # Scale problem to improve conditioning
    scale = 1.0 / max(1.0, float(np.max(np.abs(y))))
    Xs = X * scale
    ys = y * scale

    # Objective and gradient
    def obj(s: np.ndarray) -> float:
        r = Xs @ s - ys
        return float(r @ r)

    def grad(s: np.ndarray) -> np.ndarray:
        r = Xs @ s - ys
        return 2.0 * (Xs.T @ r)

    # Equality constraint: sum(s) = 1 (linear)
    A = np.ones((1, 3))
    lc = LinearConstraint(A, lb=[1.0], ub=[1.0])

    # Bounds
    bounds = (
        (0.05, 0.60),  # SHORT
        (0.05, 0.85),  # NB
        (0.00, float(tip_cap)),  # TIPS
    )

    # Initial guess: feasible shares inside bounds and summing to 1
    s0 = np.array([0.20, 0.70, min(0.10, tip_cap)], dtype=float)

    res = minimize(
        obj,
        s0,
        method="trust-constr",
        jac=grad,
        bounds=Bounds([b[0] for b in bounds], [b[1] for b in bounds]),
        constraints=[lc],
        options={"maxiter": 2000, "xtol": 1e-12, "gtol": 1e-12, "verbose": 0},
    )
    if not res.success:
        raise RuntimeError(f"Calibration optimization failed: {res.message}")

    s = np.asarray(res.x, dtype=float)
    rss = obj(s)
    tss = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - (rss / tss if tss > 0 else np.nan)
    diag = {
        "objective_rss": rss,
        "r2": r2,
        "tip_cap": float(tip_cap),
        "converged": bool(res.success),
        "message": str(res.message),
        "nit": int(res.nit),
    }
    return s, diag


def run_fit_from_artifacts(
    matrix_path: str | Path = "output/diagnostics/calibration_matrix.csv",
    out_params: str | Path = "output/parameters.json",
    out_diag: str | Path = "output/diagnostics/calibration_fit.json",
    tip_cap: float = 0.20,
) -> Tuple[Path, Path]:
    df = pd.read_csv(matrix_path, parse_dates=["Record Date"])
    # Columns: Record Date, y, SHORT, NB, TIPS
    X = df[["SHORT", "NB", "TIPS"]].to_numpy(float)
    y = df["y"].to_numpy(float)
    s, diag = calibrate_shares(X, y, tip_cap=tip_cap)

    shares = {"short": float(s[0]), "nb": float(s[1]), "tips": float(s[2])}
    params = {
        "issuance_shares": shares,
        "tip_cap": float(tip_cap),
        "window_months": int(df.shape[0]),
        "objective_rss": float(diag["objective_rss"]),
        "r2": float(diag["r2"]),
    }

    out_params_p = Path(out_params)
    out_params_p.parent.mkdir(parents=True, exist_ok=True)
    with out_params_p.open("w", encoding="utf-8") as f:
        json.dump(params, f, indent=2, sort_keys=True)

    out_diag_p = Path(out_diag)
    out_diag_p.parent.mkdir(parents=True, exist_ok=True)
    with out_diag_p.open("w", encoding="utf-8") as f:
        json.dump(diag, f, indent=2, sort_keys=True)

    return out_params_p, out_diag_p


