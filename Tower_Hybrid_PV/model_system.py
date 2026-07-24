from models.pv_model import run_pvsam
from models.lcoe import calculate_lcoe_constant
import pandas as pd
from models.csp_model import run_basic_mspt
import sys
sys.path.append(".")
from models.dispatch_opt import (optimize_dispatch,calculate_firm_bonus,)
from capex_opex.capex import calculate_capex
from capex_opex.opex import calculate_opex

def run_hybrid_summary(desired_array_size: float, P_ref: float, t_TES_hours: float, solarm: float):
    # excel_file = Path("capex_opex/CAPEX OPEX model CSP-PV MJ2500.xlsx")
    # == PV ===
    desired_array_size = desired_array_size         # kWdc
    dc_to_ac_ratio=1.2                             # DC to AC ratio for PV system
    # == CSP ===
    P_ref = P_ref                                   # CSP plant size in MWe
    # solarm = 3                                      # Solar Multiple
    eta_PB=0.412 * 0.98                                    # PB efficiency
    # == TES ===
    t_TES_hours = t_TES_hours                       # hours of thermal energy storage capacity
    max_to_grid = 100                               # MWe limit
    # == ECONOMIC MODEL ===
    x_price = 1                     
    debt = 0.8
    equity = 0.2
    debt_rate = 0.05
    equity_rate = 0.08
    tax_rate = 0.25
    lifetime_years = 30
    construction_years = 2
    # == MISC ===
    dist_to_grid = 1                # km
    dist_to_road = 0.5              # km
    dist_to_gas = 2.1               # km
    dist_to_water = 2.1             # km
    other_comp = 0                  # dummy variable for other component size
    
    df_pv, pv_summary, pv_obj, annual_energy_kwh, land_area_m2, name_plate_kwdc = run_pvsam(
        system_kwargs=dict(
            desired_array_size=desired_array_size,  
            dc_to_ac_ratio=dc_to_ac_ratio,
        )
    )
    
    df_csp, csp_summary, mspt = run_basic_mspt(
        P_ref=P_ref,
        solarm=solarm,
    )
    
    q_csp = df_csp['P_rec_MWt'].tolist()  
    e_pv  = (df_pv['AC_kWh'] / 1000).tolist() 
    
    res, model, E_cap, PV_to_heater_max,CF_hybrid,CF_pb, E_hybrid,E_pv_grid,E_pb_elec = optimize_dispatch(
        q_csp,e_pv,eta_PB=eta_PB,x_price=x_price,max_to_grid=max_to_grid,allow_spill=True,     
        objective_mode="revenue",                                   # <---: "revenue" or "cf_hybrid" or "cf_pb" (optional)                       
        PB_e_max=csp_summary.get("NetCapacity_MWe"),
        E_cap=(csp_summary.get("NetCapacity_MWe")*t_TES_hours)/eta_PB,
        solarm=solarm,
        )  
    
    bonus = calculate_firm_bonus(res, base_price=1, bonus_rate=0.2, margin=0.05, min_hours=3)
    
    inputs = {
        "PB Installed Capacity (Gross)":            csp_summary.get("NetCapacity_MWe")*1000,                # kW
        "Solar Field Aperture Area (Mirror Area)":  csp_summary.get("Solar_Field_Area_m2"),                 # m2
        "Thermal Energy Storage Capacity ":         E_cap,
        "Receiver Power (Max Rated)":               csp_summary.get("Receiver_Design_MWt"),                 # MW 0 if Parabolic Trough
        "Tower Height (w/o Receiver)":              csp_summary.get("Tower_Height_m"),                      # m
        # "Electric Heater Thermal Power (Max Rated)":csp_summary.get("Electric_Heater_Power_MWt"),         # MWt
        "Electric Heater Thermal Power (Max Rated)":PV_to_heater_max*1000,
        "Land Area CSP":                            csp_summary.get("Land_Area_acre") * 4046.86,            # m2
        "PV Installed Capacity":                    name_plate_kwdc *1000,                                  # Wdc 
        "Battery Pack Power (Max Rated)":           0,                                                    # MW bess_energy_mwh or 
        "Battery Pack Capacity":                    0,                                                      # MWh-e bess_energy_mwh or 
        "Battery Annual Generation (for OPEX)":     0,                                                    # GWh/y
        "Land Area PV":                             land_area_m2,                                           # m2
        "CSP Annual Generation (for OPEX)":         csp_summary.get("Annual_kWh") / 1000000,                # GWh/y
        "Distance to Grid ":                        dist_to_grid,
        "Distance to Road":                         dist_to_road,
        "Distance to Gas":                          dist_to_gas,
        "Distance to Water":                        dist_to_water,
        "Other Component Size":                     other_comp,
    }
    
    scaling_data = [
        ["CSP Power Block", csp_summary.get("NetCapacity_MWe")*1000],
        ["CSP BOP",  csp_summary.get("NetCapacity_MWe")*1000],
        ["CSP SF", csp_summary.get("Solar_Field_Area_m2")],
        ["CSP TES", E_cap],
        ["CSP Receiver", csp_summary.get("Receiver_Design_MWt")],
        ["CSP Tower", csp_summary.get("Tower_Height_m")],
        ["CSP Site Preparations / Civil works", csp_summary.get("Land_Area_acre") * 4046.86],
        ["Electric Heater", PV_to_heater_max*1000],
        ["Grid Connection Costs", dist_to_grid],
        ["Road Costs", dist_to_road],
        ["Gas Pipeline Costs", dist_to_gas],
        ["Water Pipeline Costs", dist_to_water],
        ["Battery Pack - Power", 0],
        ["Battery Pack - Capacity", 0],
        ["Other Component", other_comp],
        ["PV Modules", name_plate_kwdc *1000],
        ["PV Inverters", name_plate_kwdc *1000],
        ["PV BOS (except Inverters)", name_plate_kwdc *1000],
        ["PV additional rack (SA tracking)", name_plate_kwdc *1000],
        ["PV Site Preperations / Civil works", land_area_m2]
    ]
    
    opex_scaling_data = [
        ["CSP Admin/Finance & Management", csp_summary.get("NetCapacity_MWe")*1000],
        ["CSP Plant Operations Labor", csp_summary.get("NetCapacity_MWe")*1000],
        ["CSP Plant Maintenance Labor", csp_summary.get("NetCapacity_MWe")*1000],
        ["CSP Solar Field Maintenance Labor", csp_summary.get("Solar_Field_Area_m2")],
        ["CSP Subcontracted Services", csp_summary.get("Annual_kWh") / 1000000],
        ["CSP Electricity Use", csp_summary.get("NetCapacity_MWe")*1000],
        ["CSP Water Use", csp_summary.get("NetCapacity_MWe")*1000],
        ["CSP Machinery", csp_summary.get("NetCapacity_MWe")*1000],
        ["CSP Spare Parts", csp_summary.get("Annual_kWh") / 1000000],
        ["Battery Pack - Fixed OPEX", 0],
        ["Battery Pack - Variable OPEX", 0],
        ["Other OPEX", 0],
    ]
    
    scaling_df = pd.DataFrame(scaling_data, columns=["Component", "Scaling Param"])
    opex_scaling_df = pd.DataFrame(opex_scaling_data, columns=["Component", "Scaling Param"])
    capex_musd, df_capex, pv_components = calculate_capex(scaling_df)
    capex_musd =float(capex_musd)
    pv_capex = df_capex.loc[df_capex["Component"].isin(pv_components), "Scaled Cost (MUSD)"].sum()
    opex_musd, df = calculate_opex(opex_scaling_df, pv_capex)
    opex_musd = float(opex_musd)
    
    wacc = (debt * debt_rate * (1 - tax_rate)) + (equity * equity_rate)
    lcoe = calculate_lcoe_constant(capex_musd, opex_musd, E_hybrid,lifetime_years,wacc)
    
    sigma_capex = sum((capex_musd*10**6) / (construction_years*(1 + wacc)**t) for t in range(0, construction_years - 1))
    sigma_opex = sum(1 / (1 + wacc)**t for t in range(1,lifetime_years + construction_years -1))
    A = sigma_capex / sigma_opex
    PPA = (A+opex_musd*10**6) / bonus['total_revenue_with_bonus']
    annual_tot_revenue = PPA * bonus['total_revenue_with_bonus']

  
    results = {
        "desired_array_size": desired_array_size,
        "P_ref": P_ref,
        "solarm": solarm,
        "t_TES_hours": t_TES_hours,
        "PPA": PPA,
        "CF_hybrid": CF_hybrid,       
        "CF_pb": CF_pb,               
        "LCOE": lcoe,
        "Annual_Revenue": annual_tot_revenue, 
        "PV_to_Grid_MWh": E_pv_grid,
        "CSP_to_Grid_MWh": E_pb_elec
    }
    
    print("\n--- Hybrid System Summary ---")
    for key, val in results.items():
           try:
               print(f"{key:25s}: {val:,.4f}")
           except (TypeError, ValueError):
               print(f"{key:25s}: {val}")

    print("\n--- Details Summary ---")
    for key, val in inputs.items():
           try:
               print(f"{key:25s}: {val:,.4f}")
           except (TypeError, ValueError):
               print(f"{key:25s}: {val}")           
    
    return results, res, bonus, E_cap, capex_musd, opex_musd