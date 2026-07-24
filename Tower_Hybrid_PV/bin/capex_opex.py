import pandas as pd

# --- INPUTS (from your Excel) ---
inputs = {
    "PB Installed Capacity (Gross)": 190_000,       # kW
    "Solar Field Aperture Area": 507_597.5,         # m2
    "Thermal Energy Storage Capacity": 3_271.3,     # MWh-th
    "Receiver Power": 200,                          # MW-th
    "Tower Height": 200,                            # m
    "Electric Heater Power": 200_000,               # kW-th
    "Land Area CSP": 2_000_000,                     # m2
    "PV Installed Capacity": 270_327_760,           # Wdc
    "Battery Power": 150,                           # MW
    "Battery Capacity": 300,                        # MWh
    "Battery Annual Generation": 400,               # GWh/y
    "Land Area PV": 1_000_000,                      # m2
    "CSP Annual Generation": 213.85,                # GWh/y
    "Distance to Grid": 4,                          # km
    "Distance to Road": 3,
    "Distance to Gas": 5,
    "Distance to Water": 10
}

# --- CAPEX SCALING CONSTANTS (approximate from your Excel model) ---
capex_unit = {
    "PB [$ / kW]": 800,
    "Heliostat [$ / m2]": 150,
    "TES [$ / MWh-th]": 40_000,
    "Receiver [$ / MW-th]": 1_000_000,
    "Tower [$ / m]": 20_000,
    "E-Heater [$ / kW-th]": 60,
    "CSP Land [$ / m2]": 2,
    "PV EPC [$ / Wdc]": 0.5,
    "PV Land [$ / m2]": 3,
    "BESS Power [$ / kW]": 150,
    "BESS Energy [$ / kWh]": 140,
    "Grid [$ / km]": 500_000,
    "Road [$ / km]": 200_000,
    "Gas [$ / km]": 300_000,
    "Water [$ / km]": 100_000
}

# --- OPEX RATES ---
opex_unit = {
    "CSP Fixed [$ / kW-yr]": 60,
    "CSP Var [$ / MWh]": 8,
    "PV Fixed [$ / kW-yr]": 10,
    "BESS Fixed [$ / kW-yr]": 10,
    "BESS Var [$ / MWh]": 5,
    "Infra [$ / km-yr]": 2000
}

# --- CAPEX MODEL ---
capex = {
    "PB": capex_unit["PB [$ / kW]"] * inputs["PB Installed Capacity (Gross)"],
    "Heliostat": capex_unit["Heliostat [$ / m2]"] * inputs["Solar Field Aperture Area"],
    "TES": capex_unit["TES [$ / MWh-th]"] * inputs["Thermal Energy Storage Capacity"],
    "Receiver": capex_unit["Receiver [$ / MW-th]"] * inputs["Receiver Power"],
    "Tower": capex_unit["Tower [$ / m]"] * inputs["Tower Height"],
    "E-Heater": capex_unit["E-Heater [$ / kW-th]"] * inputs["Electric Heater Power"],
    "CSP Land": capex_unit["CSP Land [$ / m2]"] * inputs["Land Area CSP"],
    "PV": capex_unit["PV EPC [$ / Wdc]"] * inputs["PV Installed Capacity"],
    "PV Land": capex_unit["PV Land [$ / m2]"] * inputs["Land Area PV"],
    "BESS Power": capex_unit["BESS Power [$ / kW]"] * (inputs["Battery Power"] * 1000),
    "BESS Energy": capex_unit["BESS Energy [$ / kWh]"] * (inputs["Battery Capacity"] * 1000),
    "Grid": capex_unit["Grid [$ / km]"] * inputs["Distance to Grid"],
    "Road": capex_unit["Road [$ / km]"] * inputs["Distance to Road"],
    "Gas": capex_unit["Gas [$ / km]"] * inputs["Distance to Gas"],
    "Water": capex_unit["Water [$ / km]"] * inputs["Distance to Water"]
}

capex_total = sum(capex.values()) / 1e6  # MUSD

# --- OPEX MODEL ---
opex = {
    "CSP Fixed": opex_unit["CSP Fixed [$ / kW-yr]"] * inputs["PB Installed Capacity (Gross)"],
    "CSP Var": opex_unit["CSP Var [$ / MWh]"] * (inputs["CSP Annual Generation"] * 1000),
    "PV Fixed": opex_unit["PV Fixed [$ / kW-yr]"] * (inputs["PV Installed Capacity"] / 1000),
    "BESS Fixed": opex_unit["BESS Fixed [$ / kW-yr]"] * (inputs["Battery Power"] * 1000),
    "BESS Var": opex_unit["BESS Var [$ / MWh]"] * (inputs["Battery Annual Generation"] * 1000),
    "Infra": opex_unit["Infra [$ / km-yr]"] * (
        inputs["Distance to Grid"] + inputs["Distance to Road"] +
        inputs["Distance to Gas"] + inputs["Distance to Water"]
    )
}

opex_total = sum(opex.values()) / 1e6  # MUSD/yr

# --- RESULTS ---
print(f"Total CAPEX : {capex_total:,.2f} MUSD")
print(f"Total OPEX  : {opex_total:,.2f} MUSD/year")



