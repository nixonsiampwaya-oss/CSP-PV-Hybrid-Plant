from __future__ import annotations
from typing import Dict, Tuple, Optional
import numpy as np
import pandas as pd
import PySAM.TroughPhysical as PhysicalTrough
from pathlib import Path


def run_basic_trough(
    # --- Resource ---
    weather_path: str = "input_data/tmy_38.730_-3.450_2005_2023.epw",

    # --- Simulation Control ---
    time_steps_per_hour: int = 1,
    time_start_s: Optional[int] = None,
    time_stop_s: Optional[int] = None,
    is_dispatch: int = 0, #Automatically set to 0 if not assigned explicitly or loaded from defaults

    # --- Power Cycle Design ---
    P_ref: float = 50.0,             # Rated plant capacity [MWe]
    specified_solar_multiple: float = 1.6,         # Solar multiple
    tshours: float = 0,            # TES hours
    I_bn_des: float = 950.0,         # W/m2
    eta_ref: float = 0.4,           # Gross cycle thermal efficiency
    gross_net_conversion_factor: float = 0.9,

    # --- Thermal Fluid and Temperature ---
    Fluid: int = 21,                 # 21 = Therminol VP-1
    T_loop_in_des: float = 293.0,    # °C
    T_loop_out: float = 391.0,       # °C

    # --- Field Design ---
    azimuth: float = 0.0,            # 0° = North–South alignment
    #row_spacing: float = 15.0,       # m

    # --- Collector Type (new) ---
    collector_name: str = "ST2",   # choose from Luz LS-3, ET150, ST2
    tracking_mode: int = 1,         # 1 = single-axis tracking
    export_csv_path: Optional[str] = None   # e.g. "outputs/trough_run.csv"
) -> Tuple[pd.DataFrame, Dict, object]:
    """
    Run a CSP Parabolic Trough model using PySAM (Physical model, no financials)
    with automatic field sizing and collector efficiency lookup.
    """

    # --- Collector library (detailed geometry) ---
    collector_data: Dict[str, Dict[str, float]] = {
        "Luz LS-3": {
            "A_aperture": 545.0,
            "W_aperture": 5.75,
            "L_SCA": 100.0,
            "ColperSCA": 12.0,
            "Ave_Focal_Length": 2.11,
            "Distance_SCA": 1.0,
            "L_aperture": 8.333
        },
        "ET150": {
            "A_aperture": 817.5,
            "W_aperture": 5.75,
            "L_SCA": 150.0,
            "ColperSCA": 12.0,
            "Ave_Focal_Length": 2.11,
            "Distance_SCA": 1.0,
            "L_aperture": 12.5
        },
        "ST2": {
            "A_aperture": 1047.0,
            "W_aperture": 6.87,
            "L_SCA": 160.0,
            "ColperSCA": 12.0,
            "Ave_Focal_Length": 2.49,
            "Distance_SCA": 1.1,
            "L_aperture": 13.33
        }
    }

    # --- Helper to assign collector data ---
    def set_collector(model, name: str):
        """Apply collector data to the SAM model SolarField group by name."""
        if name not in collector_data:
            raise ValueError(f"Collector '{name}' not found. Choose from: {list(collector_data.keys())}")

        data = collector_data[name]
        for key, value in data.items():
            try:
                setattr(model.SolarField, key, value)
            except TypeError:
            # If SAM expects an array, wrap the value in a list
                setattr(model.SolarField, key, [value])
        print(f"✅ Collector type set to: {name}")

    # --- Initialize model ---
    trough = PhysicalTrough.default("PhysicalTroughNone")
    trough.Weather.file_name = weather_path

    # --- Apply chosen collector type ---
    set_collector(trough, "ST2")

    # --- Field Sizing ---
    q_field_design_MWt = P_ref / eta_ref  # MWt at design
    A_sf_design = (q_field_design_MWt * 1e6) / (I_bn_des * 0.73)  # assume optical eff ≈ 0.73
    A_sf_total = A_sf_design * specified_solar_multiple
    

    # Collector geometry
    col = collector_data["ST2"]
    A_loop = col["A_aperture"]
    n_loops = int(np.ceil(A_sf_total / A_loop))

    # --- Assign system design ---
    trough.SolarField.azimuth = float(azimuth)
    trough.Powerblock.P_ref = float(P_ref)
    trough.Controller.specified_solar_multiple = float(specified_solar_multiple)
    trough.TES.tshours = float(tshours)
    trough.SolarField.I_bn_des = float(I_bn_des)
    trough.Powerblock.eta_ref = float(eta_ref)
    trough.SolarField.T_loop_in_des = float(T_loop_in_des)
    trough.SolarField.T_loop_out = float(T_loop_out)
    trough.SolarField.Fluid = int(Fluid)

    # --- Collector & Field Layout ---
    #trough.CollectorType.tracking_mode = int(tracking_mode)
    #trough.FieldLayout.row_spacing = float(row_spacing)
    #trough.FieldLayout.nLoops = n_loops

    # --- Simulation Control ---
    trough.Tou.is_dispatch = int(is_dispatch)
    trough.SystemControl.time_steps_per_hour = int(time_steps_per_hour)
    if time_start_s is not None:
        trough.SystemControl.time_start = int(time_start_s)
    if time_stop_s is not None:
        trough.SystemControl.time_stop = int(time_stop_s)

    # --- Run simulation ---
    trough.execute()

    # --- Extract Outputs ---
    A_sf = float(getattr(trough.Outputs, "total_aperture", float("nan")))  
    land_area = float(getattr(trough.Outputs, "total_land_area", float("nan")))  
    p_gross = np.array(getattr(trough.Outputs, "P_cycle", []), dtype=float)
    p_net = np.array(getattr(trough.Outputs, "P_out_net", []), dtype=float)
    q_sf_inc = np.array(getattr(trough.Outputs, "q_dot_rec_inc", []), dtype=float)
    q_rec = np.array(getattr(trough.Outputs, "q_dot_rec_abs", []), dtype=float)
    # q_tes = np.array(getattr(trough.Outputs, "e_tes", []), dtype=float)

    annual_kwh = float(getattr(trough.Outputs, "annual_energy", np.nansum(p_net) * 1e3))

    # --- Capacity factor ---
    try:
        cf_pct = float(trough.Outputs.capacity_factor)
    except Exception:
        total_hours = len(p_net) / float(trough.SystemControl.time_steps_per_hour or 1)
        denom = float(P_ref) * 1e3 * total_hours
        cf_pct = (annual_kwh / denom * 100.0) if denom > 0 else float("nan")

    # --- Outputs ---
    df_csp = pd.DataFrame({
        "Hour": np.arange(1, len(p_net) + 1, dtype=int),
        "q_sf_inc_MWt": q_sf_inc,
        "q_rec_MWt": q_rec,
        # "q_tes_state_MWht": q_tes,
        "P_gross_MWe": p_gross,
        "P_net_MWe": p_net,
    })

    print(f"{max(df_csp['q_sf_inc_MWt'])} at hour {df_csp['Hour'][df_csp['q_sf_inc_MWt'].idxmax()]}")
    print(f"{max(df_csp['q_rec_MWt'])} at hour {df_csp['Hour'][df_csp['q_rec_MWt'].idxmax()]}")

    csp_summary = {
        "CollectorType": collector_name,
        "DesignTurbineGross_MWe": float(P_ref),
        "NetCapacity_MWe": float(P_ref) * gross_net_conversion_factor,
        "CycleEfficiency": float(eta_ref),
        "GrossToNetFactor": float(gross_net_conversion_factor),
        "SolarMultiple": float(specified_solar_multiple),
        "TES_Hours": float(tshours),
        "DesignDNI_Wm2": float(I_bn_des),
        "HTF_Fluid_ID": int(Fluid),
        "Loop_Inlet_Temp_C": float(T_loop_out),
        "Loop_Outlet_Temp_C": float(T_loop_in_des),
        "Total_Aperture_Area_m2": A_sf_total,
        "Loops_Calculated": int(n_loops),
        "CapacityFactor_%": cf_pct,
        "Annual_kWh": annual_kwh,
        "TimeStepsPerHour": time_steps_per_hour,
        "Solar_Field_Area_m2": A_sf,
        "Land_Area_acre": land_area,
    }

    #  # --- Optional export to CSV ---
    # if export_csv_path:
    #     export_csv_path = Path(export_csv_path)
    #     export_csv_path.parent.mkdir(parents=True, exist_ok=True)

    #     # Write timeseries first
    #     df_csp.to_csv(export_csv_path, index=False, float_format="%.6f")

    #     # Append summary section
    #     with open(export_csv_path, "a", encoding="utf-8") as f:
    #         f.write("\n# ---- Summary ----\n")
    #         for k, v in csp_summary.items():
    #             f.write(f"{k},{v}\n")

    #     print(f"✅ Exported results to: {export_csv_path}")

    return df_csp, csp_summary, trough
