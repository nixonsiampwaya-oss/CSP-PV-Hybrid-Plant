from models.pv_model import run_pvsam
import numpy as np
from capex_opex.excel_capex_opex import calc_capex_opex
from pathlib import Path
from models.csp_model import run_basic_mspt
import sys
sys.path.append(".")
from models.dispatch_opt import optimize_dispatch, export_dispatch_to_csv, calculate_firm_bonus

def run_hybrid_summary(desired_array_size: float, P_ref: float, t_TES_hours: float):
    """
    Runs your PV + CSP + TES + finance pipeline with the same internal settings,
    exposing only desired_array_size (kWdc), P_ref (MWe), and t_TES_hours (h).
    Returns CFs and PPA price.
    """
    # == FILES ==
    excel_file = Path("capex_opex/CAPEX OPEX model CSP-PV MJ2500.xlsx")

    # == PV (unchanged defaults) ==
    dc_to_ac_ratio = 1.2  # DC to AC ratio for PV system

    # == CSP (unchanged defaults, except P_ref from arg) ==
    solarm = 3
    eta_PB = 0.40

    # == TES / GRID (unchanged, except t_TES_hours from arg) ==
    max_to_grid = 100  # MWe limit

    # == ECONOMIC MODEL (unchanged) ==
    x_price = 1
    debt = 0.8
    equity = 0.2
    debt_rate = 0.05
    equity_rate = 0.08
    tax_rate = 0.25
    lifetime_years = 30
    construction_years = 2

    # == MISC DISTANCES (unchanged) ==
    dist_to_grid = 0
    dist_to_road = 0
    dist_to_gas = 0
    dist_to_water = 0
    other_comp = 0

    # -------------------------
    # PV model (unchanged call)
    # -------------------------
    df_pv, pv_summary, pv_obj, annual_energy_kwh, land_area_m2, name_plate_kwdc = run_pvsam(
        system_kwargs=dict(
            desired_array_size=desired_array_size,
            dc_to_ac_ratio=dc_to_ac_ratio,
        )
    )

    # -------------------------
    # CSP model (unchanged call)
    # -------------------------
    df_csp, csp_summary, mspt = run_basic_mspt(
        P_ref=P_ref,
        solarm=solarm,
    )

    # Prepare series (unchanged)
    q_csp = df_csp['P_rec_MWt_calculated'].tolist()
    e_pv  = (df_pv['AC_kWh'] / 1000).tolist()

    # -------------------------
    # Dispatch optimization (unchanged)
    # -------------------------
    res, model, E_cap, PV_to_heater_max, CF_hybrid, CF_pb = optimize_dispatch(
        q_csp,
        e_pv,
        eta_PB=eta_PB,
        x_price=x_price,
        max_to_grid=max_to_grid,
        allow_spill=True,
        objective_mode="revenue",                 # unchanged
        PB_e_max=csp_summary.get("NetCapacity_MWe"),
        E_cap=(csp_summary.get("NetCapacity_MWe") * t_TES_hours) / eta_PB,
        solarm=solarm,
    )

    bonus = calculate_firm_bonus(res, base_price=50.0, bonus_rate=0.2, margin=0.05, min_hours=3)

    # -------------------------
    # CAPEX/OPEX inputs (unchanged)
    # -------------------------
    inputs = {
        "PB Installed Capacity (Gross)":            csp_summary.get("NetCapacity_MWe")*1000,
        "Solar Field Aperture Area (Mirror Area)":  csp_summary.get("Solar_Field_Area_m2"),
        "Thermal Energy Storage Capacity ":         E_cap,
        "Receiver Power (Max Rated)":               csp_summary.get("Receiver_Design_MWt"),
        "Tower Height (w/o Receiver)":              csp_summary.get("Tower_Height_m"),
        "Electric Heater Thermal Power (Max Rated)":PV_to_heater_max*1000,
        "Land Area CSP":                            csp_summary.get("Land_Area_acre") * 4046.86,
        "PV Installed Capacity":                    name_plate_kwdc * 1000,
        "Battery Pack Power (Max Rated)":           0,
        "Battery Pack Capacity":                    0,
        "Battery Annual Generation (for OPEX)":     0,
        "Land Area PV":                             land_area_m2,
        "CSP Annual Generation (for OPEX)":         csp_summary.get("Annual_kWh") / 1_000_000,
        "Distance to Grid ":                        dist_to_grid,
        "Distance to Road":                         dist_to_road,
        "Distance to Gas":                          dist_to_gas,
        "Distance to Water":                        dist_to_water,
        "Other Component Size":                     other_comp,
    }

    # Overrides (unchanged)
    overrides = {
        # Tower defaults per your comment
        "BOP": 74.8,          # MUSD
        # If you meant tower, your comment says 125 but you set 115 here—kept as-is
        "SF_aperture": 115,   # MUSD
        "PV_modules": 0.3,    # MUSD
        "pv_fixed_opex_coeff": 1,
    }

    capex_musd, opex_musd, capex_df, opex_df = calc_capex_opex(
        excel_file, inputs, return_breakdowns=True, ref_cost_overrides=overrides
    )

    # Finance (unchanged)
    wacc = (debt * debt_rate * (1 - tax_rate)) + (equity * equity_rate)
    sigma_capex = sum((capex_musd * 10**6) / (construction_years * (1 + wacc)**t)
                      for t in range(0, construction_years - 1))
    sigma_opex = sum(1 / (1 + wacc)**t
                     for t in range(1, lifetime_years + construction_years - 1))
    A = sigma_capex / sigma_opex
    PPA = (A + opex_musd * 10**6) / bonus['total_revenue_with_bonus']  # USD/MWh if revenue is in USD

    # Return ONLY the requested outputs
    return {
        "CF_hybrid": float(CF_hybrid),
        "CF_pb": float(CF_pb),
        "PPA_USD_per_MWh": float(PPA),
        "PPA_USD_per_kWh": float(PPA / 1000.0),
    }
