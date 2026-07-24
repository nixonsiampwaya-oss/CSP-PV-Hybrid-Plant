from __future__ import annotations
from typing import Dict, Tuple, Optional
import numpy as np
import pandas as pd
import PySAM.TcsmoltenSalt as TcsmoltenSalt

def run_basic_mspt(
    weather_path: str =  "input_data/tmy_38.730_-3.450_2005_2023.epw",
    P_ref: float = 115.0,          # MW
    design_eff: float = 0.412,     # gross cycle efficiency (fraction)
    solarm: float = 2.0,           # solar multiple
    tshours: float = 0,          # TES hours
    dni_des: float = 950.0,        # W/m2
    T_hot: float = 565.0,          # °C
    T_cold: float = 290.0,         # °C
    is_dispatch: int = 0,          # 0 = no optimization (faster)
    time_steps_per_hour: int = 1,  # coarsest sim grid
    disp_steps_per_hour: int = 1,  # coarsest dispatch grid (if dispatch on)
    time_start_s: Optional[int] = None,   # simulate a slice (seconds from Jan 1)
    time_stop_s: Optional[int] = None,
    lat: Optional[float] = None,   # optional explicit site coords
    lon: Optional[float] = None,
) -> Tuple[pd.DataFrame, Dict, object]:

    mspt = TcsmoltenSalt.default("MSPTNone")
    mspt.SolarResource.solar_resource_file = weather_path

    # Optional explicit site
    if lat is not None:
        for key in ("latitude", "lat"):
            try:
                mspt.value(key, float(lat))
                break
            except Exception:
                pass
    if lon is not None:
        for key in ("longitude", "lon"):
            try:
                mspt.value(key, float(lon))
                break
            except Exception:
                pass

    # System design (essentials)
    mspt.SystemDesign.P_ref = float(P_ref)
    mspt.SystemDesign.design_eff = float(design_eff)
    mspt.SystemDesign.solarm = float(solarm)
    mspt.SystemDesign.tshours = float(tshours)
    mspt.SystemDesign.dni_des = float(dni_des)
    mspt.SystemDesign.T_htf_hot_des = float(T_hot)
    mspt.SystemDesign.T_htf_cold_des = float(T_cold)
    mspt.HeliostatField.field_model_type = 1

    # Speed / control
    mspt.SystemControl.is_dispatch = int(is_dispatch)
    mspt.SystemControl.time_steps_per_hour = int(time_steps_per_hour)
    mspt.SystemControl.disp_steps_per_hour = int(disp_steps_per_hour)

    # Optional shorter window
    if time_start_s is not None:
        mspt.SystemControl.time_start = int(time_start_s)
    if time_stop_s is not None:
        mspt.SystemControl.time_stop = int(time_stop_s)

    # Optional: skip flux map calc if available (speed)
    try:
        mspt.HeliostatField.calc_fluxmaps = 0
    except Exception:
        pass

    # Run
    mspt.execute()

    #Design call out
    pb_cap_mw = float(P_ref)
    tes_cap_mwh = float(tshours) * pb_cap_mw

    #field power
    p_field_mw = np.array(getattr(mspt.Outputs, "q_sf_inc", []), dtype=float)
    eff_field = np.array(getattr(mspt.Outputs, "eta_field", []), dtype=float)
    defocus = np.array(getattr(mspt.Outputs, "defocus", []), dtype=float)

    # Receiver power
    eff_rec = np.array(getattr(mspt.Outputs, "eta_therm", []), dtype=float)
    p_rec_mw = p_field_mw * eff_rec * eff_field 

    # Results dframe
    p_heliostat = np.array(getattr(mspt.Outputs, "q_dot_rec_inc", []), dtype=float)  # Heliostat field power [MWt]
    p_rec = np.array(getattr(mspt.Outputs, "Q_thermal", []), dtype=float)  # Receiver thermal power [MWt]
    p_net = np.array(getattr(mspt.Outputs, "P_out_net", []), dtype=float)  # MWe
    p_tes = np.array(getattr(mspt.Outputs, "e_ch_tes", []), dtype=float)  # TES charge state [MWht]
    tank_losses = np.array(getattr(mspt.Outputs, "tank_losses", []), dtype=float)  # TES thermal losses [MWt]

    # Results summary
    annual_kwh = float(getattr(mspt.Outputs, "annual_energy", np.nansum(p_net) * 1e3))
    tower_height = float(getattr(mspt.Outputs, "h_tower_calc", float("nan")))
    rec_design = float(getattr(mspt.Outputs, "q_dot_rec_des", float("nan")))
    land_area = float(getattr(mspt.Outputs, "land_area_base_calc", float("nan"))) #Land area occupied by heliostats [acre]
    A_sf = float(getattr(mspt.Outputs, "A_sf", float("nan")))  # Solar field area [m2]
    elec_heat= np.sum(getattr(mspt.Outputs, "q_dot_elec_to_PAR_HTR", [])) / getattr(mspt.SystemControl, "time_steps_per_hour", 1)  # Electric heater power [MWt]

    try:
        cf_pct = float(mspt.Outputs.capacity_factor)  # [%]
    except Exception:
        cap = float(mspt.SystemDesign.P_ref)
        total_hours = len(p_net) / float(mspt.SystemControl.time_steps_per_hour or 1) if len(p_net) else 8760.0
        denom = cap * 1e3 * total_hours
        cf_pct = (annual_kwh / denom * 100.0) if denom > 0 else float("nan")

    df_csp = pd.DataFrame({
        "Hour": np.arange(1, len(p_net) + 1, dtype=int),
        "P_heliostat_MWt": p_heliostat,
        "P_rec_MWt": p_rec,
        "p_field_MWt": p_field_mw,
        "P_rec_MWt_calculated": p_rec_mw,
        "p_tes_state_MWht": p_tes,
        "tank_losses_MWt": tank_losses,
        "P_out_net_MWe": p_net,
    })
    
    print(f"{max(df_csp['P_rec_MWt'])} at hour {df_csp['Hour'][df_csp['P_rec_MWt'].idxmax()]}")
    print(f"{max(df_csp['P_rec_MWt_calculated'])} at hour {df_csp['Hour'][df_csp['P_rec_MWt_calculated'].idxmax()]}")

    csp_summary = {
        "NetCapacity_MWe":pb_cap_mw,
        "Annual_kWh": annual_kwh,
        "Tower_Height_m": tower_height,
        "Land_Area_acre": land_area,
        "Solar_Field_Area_m2": A_sf,
        "Receiver_Design_MWt" : rec_design,
        # "Tes_Capacity_MWh": tes_cap_mwh,
        # "Electric_Heater_Power_MWt": elec_heat,
        "CapacityFactor_%": cf_pct,
        "NetCapacity_MWe": float(mspt.SystemDesign.P_ref),
        "SolarMultiple": float(mspt.SystemDesign.solarm),
        # "TES_Hours": float(mspt.SystemDesign.tshours),
    }

    return df_csp, csp_summary, mspt
