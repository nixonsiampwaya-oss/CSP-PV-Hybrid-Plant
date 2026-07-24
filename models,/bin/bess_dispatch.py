"""
models/bess_dispatch.py
Implements export-cap + BESS dispatch with min SoC.
"""
from __future__ import annotations
from typing import Dict, Tuple
import numpy as np
import pandas as pd


def run_bess_dispatch(df: pd.DataFrame,
                      export_limit_mw: float = 2.5,
                      bess_energy_mwh: float = 20.0,
                      bess_power_mw: float = 2.5,
                      eta_c: float = 1.0,
                      eta_d: float = 1.0,
                      initial_soc_mwh: float = 0.0,
                      soc_min_frac: float = 0.20) -> Tuple[pd.DataFrame, Dict]:
    """
    Apply a simple heuristic: export PV up to cap, store surplus; when PV below cap,
    discharge down to min SoC to reach cap.

    df must contain column "AC_kWh".
    """
    limit_kwh = export_limit_mw * 1000.0
    pwr_kwh   = bess_power_mw   * 1000.0
    min_soc_mwh = soc_min_frac * bess_energy_mwh

    n = len(df)
    soc_mwh         = np.zeros(n, dtype=float)
    charge_kwh      = np.zeros(n, dtype=float)
    discharge_kwh   = np.zeros(n, dtype=float)
    grid_export_kwh = np.zeros(n, dtype=float)
    curtail_kwh     = np.zeros(n, dtype=float)

    soc = max(initial_soc_mwh, min_soc_mwh)

    # tolerate either AC_kWh or AC_KWh
    ac_col = "AC_KWh" if "AC_KWh" in df.columns else "AC_kWh"

    for t in range(n):
        pv_kwh = float(df.iloc[t][ac_col])

        # direct to grid up to cap
        direct_to_grid = min(pv_kwh, limit_kwh)
        grid_export = direct_to_grid

        # surplus -> charge
        surplus = pv_kwh - direct_to_grid
        if surplus > 0:
            room_kwh = max(0.0, (bess_energy_mwh - soc) * 1000.0)
            can_charge = max(0.0, min(surplus, pwr_kwh, room_kwh))
            charge = can_charge * eta_c
            charge_kwh[t] = charge
            soc += charge / 1000.0
            curtail_kwh[t] = max(0.0, surplus - can_charge)

        # deficit -> discharge (respect min SoC)
        if pv_kwh < limit_kwh:
            need = limit_kwh - pv_kwh
            available_kwh_above_min = max(0.0, (soc - min_soc_mwh) * 1000.0)
            can_discharge = min(pwr_kwh, need, available_kwh_above_min)
            discharge = can_discharge * eta_d
            discharge_kwh[t] = discharge
            grid_export += discharge
            soc -= discharge / 1000.0

        grid_export_kwh[t] = grid_export
        soc_mwh[t] = soc

    out = df.copy()
    out["Grid_kWh"]            = grid_export_kwh
    out["BESS_Charge_kWh"]     = charge_kwh
    out["BESS_Discharge_kWh"]  = discharge_kwh
    out["Curtail_kWh"]         = curtail_kwh
    out["SOC_MWh"]             = soc_mwh

    summary = {
        "PV_total_kWh":             float(out[ac_col].sum()),
        "Grid_export_total_kWh":    float(out["Grid_kWh"].sum()),
        "BESS_charge_total_kWh":    float(out["BESS_Charge_kWh"].sum()),
        "BESS_discharge_total_kWh": float(out["BESS_Discharge_kWh"].sum()),
        "Curtail_total_kWh":        float(out["Curtail_kWh"].sum()),
        "Final_SOC_MWh":            float(out["SOC_MWh"].iloc[-1]),
        "Min_SOC_MWh":              float(min_soc_mwh),
    }

    return out, summary
