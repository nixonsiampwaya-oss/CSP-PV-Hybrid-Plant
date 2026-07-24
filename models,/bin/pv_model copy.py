from __future__ import annotations
from typing import Dict, Tuple, Optional
import pandas as pd
import numpy as np

try:
    import PySAM.Pvsamv1 as Pvsamv1
except Exception as e:
    raise ImportError("PySAM is required: pip install NREL-PySAM") from e


def _load_cec_module_row(cec_csv: str, target_name: str) -> pd.Series:
    cec = pd.read_csv(cec_csv)
    row = cec.loc[cec["Name"] == target_name]
    if row.empty:
        raise ValueError(f"Module '{target_name}' not found in {cec_csv}")
    return row.iloc[0]


def _load_cec_inverter_row(inv_csv: str, target_name: str) -> pd.Series:
    inv_df = pd.read_csv(inv_csv)
    row = inv_df.loc[inv_df["Name"] == target_name]
    if row.empty:
        raise ValueError(f"Inverter '{target_name}' not found in {inv_csv}")
    return row.iloc[0]


def run_pvsam(weather_path: str = "input_data/tmy_38.730_-3.450_2005_2023.epw",
              module_name: str = "SunPower SPR-X22-360-C-AC",
              inverter_name: str = "Sungrow Power Supply Co - Ltd : SC2500U [550V]",
              cec_module_csv: str = "equipment_database/CEC Modules.csv",
              cec_inverter_csv: str = "equipment_database/CEC Inverters.csv",
              system_kwargs: Optional[Dict] = None) -> Tuple[pd.DataFrame, Dict, object]:
    
    system_kwargs = system_kwargs or {}

    pv = Pvsamv1.default("FlatPlatePVCommercial")
    pv.SolarResource.solar_resource_file = weather_path

    # ---- CEC MODULE ----
    r = _load_cec_module_row(cec_module_csv, module_name)
    pv.Module.module_model = 1  # 1 = CEC DB
    g = pv.CECPerformanceModelWithModuleDatabase
    g.cec_i_sc_ref = float(r["I_sc_ref"])
    g.cec_v_oc_ref = float(r["V_oc_ref"])
    g.cec_i_mp_ref = float(r["I_mp_ref"])
    g.cec_v_mp_ref = float(r["V_mp_ref"])
    g.cec_alpha_sc = float(r["alpha_sc"])
    g.cec_beta_oc  = float(r["beta_oc"])
    g.cec_a_ref    = float(r["a_ref"])
    g.cec_i_l_ref  = float(r["I_L_ref"])
    g.cec_i_o_ref  = float(r["I_o_ref"])
    g.cec_r_sh_ref = float(r["R_sh_ref"])
    g.cec_adjust   = float(r["Adjust"])
    g.cec_n_s      = int(r["N_s"])
    if "Length" in r and "Width" in r:
        try:
            g.cec_module_length = float(r["Length"])
            g.cec_module_width  = float(r["Width"])
        except Exception:
            pass

    # ---- CEC INVERTER ----
    inv = _load_cec_inverter_row(cec_inverter_csv, inverter_name)
    pv.Inverter.inverter_model = 0  # 0 = CEC (Sandia)
    iv = pv.InverterCECDatabase
    iv.inv_snl_paco = float(inv["Paco"])
    iv.inv_snl_pdco = float(inv["Pdco"])
    iv.inv_snl_vdco = float(inv["Vdco"])
    iv.inv_snl_pso  = float(inv["Pso"])
    iv.inv_snl_c0   = float(inv["C0"])
    iv.inv_snl_c1   = float(inv["C1"])
    iv.inv_snl_c2   = float(inv["C2"])
    iv.inv_snl_c3   = float(inv["C3"])
    if "CEC Weighted Efficiency" in inv:
        try:
            iv.inv_snl_eff_cec = float(inv["CEC Weighted Efficiency"])
        except Exception:
            pass

    # MPPT window (optional)
    if "mppt_low_inverter" in system_kwargs:
        pv.Inverter.mppt_low_inverter = float(system_kwargs["mppt_low_inverter"])
    if "mppt_hi_inverter" in system_kwargs:
        pv.Inverter.mppt_hi_inverter  = float(system_kwargs["mppt_hi_inverter"])

    # ---- SYSTEM DESIGN ----
    pv.SystemDesign.inverter_count = int(system_kwargs.get("inverter_count", 2))
    pv.SystemDesign.subarray1_modules_per_string = int(system_kwargs.get("subarray1_modules_per_string", 21))
    pv.SystemDesign.subarray1_nstrings = int(system_kwargs.get("subarray1_nstrings", 1000))
    pv.SystemDesign.subarray2_enable = 0
    pv.SystemDesign.subarray3_enable = 0
    pv.SystemDesign.subarray4_enable = 0
    pv.SystemDesign.subarray1_track_mode = int(system_kwargs.get("subarray1_track_mode", 0))
    pv.SystemDesign.subarray1_tilt = float(system_kwargs.get("subarray1_tilt", 20.0))
    pv.SystemDesign.subarray1_azimuth = float(system_kwargs.get("subarray1_azimuth", 180.0))
    pv.SystemDesign.subarray1_gcr = float(system_kwargs.get("subarray1_gcr", 0.4))

    # Albedo
    pv.SolarResource.use_spatial_albedos = 0
    pv.SolarResource.use_wf_albedo = 1
    pv.SolarResource.albedo = system_kwargs.get("albedo", [0.2] * 12)

    # Losses
    pv.Losses.subarray1_soiling = system_kwargs.get("soiling", [5] * 12)
    pv.Losses.subarray1_dcwiring_loss = float(system_kwargs.get("dcwiring_loss", 2.0))
    pv.Losses.subarray1_mismatch_loss = float(system_kwargs.get("mismatch_loss", 2.0))
    pv.Losses.subarray1_diodeconn_loss = float(system_kwargs.get("diodeconn_loss", 0.5))
    pv.Losses.acwiring_loss = float(system_kwargs.get("acwiring_loss", 1.0))
    pv.Losses.transformer_no_load_loss = 0.0
    pv.Losses.transformer_load_loss = 0.0
    pv.Losses.transmission_loss = 0.0

    # Single-year run
    pv.Lifetime.system_use_lifetime_output = 0
    pv.Lifetime.analysis_period = 1

    # Execute
    pv.execute()

    # Land Area calculation:
    module_area_m2 = pv.CECPerformanceModelWithModuleDatabase.cec_module_length * \
                 pv.CECPerformanceModelWithModuleDatabase.cec_module_width
    n_modules = (pv.SystemDesign.subarray1_modules_per_string *
             pv.SystemDesign.subarray1_nstrings *
             pv.SystemDesign.inverter_count)
    gcr = pv.SystemDesign.subarray1_gcr

    land_area_m2 = module_area_m2 * n_modules / gcr

    # Extract results
    name_plate_kwdc = float(pv.Outputs.nameplate_dc_rating)
    annual_energy_kwh = float(pv.Outputs.annual_energy)
    capacity_factor = float(pv.Outputs.capacity_factor_ac)
    ac_kwh = np.array(pv.Outputs.ac_gross, dtype=float)
    poa = np.array(pv.Outputs.subarray1_poa_front, dtype=float)

    df = pd.DataFrame({
        "Hour": np.arange(1, len(ac_kwh) + 1),
        "AC_kWh": ac_kwh,
        "POA_kWh/m2": poa
    })

    summary = {
        "Annual_kWh": annual_energy_kwh,
        "CapacityFactor_AC_%": capacity_factor,
        "NamePlate_kWdc": name_plate_kwdc,
        "LandArea_m2": land_area_m2,

    }

    return df, summary, pv, annual_energy_kwh, land_area_m2, name_plate_kwdc