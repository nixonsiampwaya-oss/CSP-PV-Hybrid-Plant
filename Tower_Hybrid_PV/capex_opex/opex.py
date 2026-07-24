import pandas as pd

opex_ref_cost_data = [
    ["CSP Admin/Finance & Management", "kW", 110000, 196100.000],
    ["CSP Plant Operations Labor", "kW", 110000, 1335600.000],
    ["CSP Plant Maintenance Labor", "kW", 110000, 286200.000],
    ["CSP Solar Field Maintenance Labor", "m2", 977628, 212000.000],
    ["CSP Subcontracted Services", "GWh/y", 516, 227900.000],
    ["CSP Electricity Use", "kW", 110000, 1431000.000],
    ["CSP Water Use", "kW", 110000, 1025232.000],
    ["CSP Machinery", "kW", 110000, 216240.000],
    ["CSP Spare Parts", "kW", 516, 1331360.000],
    ["Battery Pack - Fixed OPEX", "MW", 0.001, 6.900],
    ["Battery Pack - Variable OPEX", "GWh/y", 0.001, 2.100],
    ["Other OPEX", "-", 1, 0.000],
]

opex_ref_cost_df = pd.DataFrame(opex_ref_cost_data,columns=["Component", "Unit", "Reference Value", "Reference Cost (USD)"])

opex_coeff_data = [
    ["CSP Admin/Finance & Management", 1],
    ["CSP Plant Operations Labor", 0.7],
    ["CSP Plant Maintenance Labor", 0.7],
    ["CSP Solar Field Maintenance Labor", 1],
    ["CSP Subcontracted Services", 0.7],
    ["CSP Electricity Use", 1],
    ["CSP Water Use", 1],
    ["CSP Machinery", 0.7],
    ["CSP Spare Parts", 0.7],
    ["Battery Pack - Fixed OPEX", 1],
    ["Battery Pack - Variable OPEX", 1],
    ["Other OPEX", 1],
]

opex_coeff_df = pd.DataFrame(opex_coeff_data,columns=["Component", "COEFF"])

def calculate_opex(
    scaling_df: pd.DataFrame,
    pv_capex,
    opex_ref_cost_df: pd.DataFrame = opex_ref_cost_df,
    opex_coeff_df: pd.DataFrame = opex_coeff_df
) -> pd.DataFrame:
    if isinstance(scaling_df, dict):
        scaling_df = pd.DataFrame(list(scaling_df.items()), columns=["Component", "Scaling Param"])
    elif isinstance(scaling_df, pd.Series):
        scaling_df = scaling_df.reset_index()
        scaling_df.columns = ["Component", "Scaling Param"]
    df = (
        opex_ref_cost_df
        .merge(opex_coeff_df, on="Component", how="left")
        .merge(scaling_df, on="Component", how="left")
    )
    df["COEFF"] = df["COEFF"].fillna(1.0)
    df["Scaling Param"] = df["Scaling Param"].fillna(df["Reference Value"])

    df["Scaled OPEX (USD/y)"] = df["Reference Cost (USD)"] * (
        (df["Scaling Param"] / df["Reference Value"]) ** df["COEFF"]
    )
    total_opex = df["Scaled OPEX (USD/y)"].sum()/1000000
    total_opex = total_opex + pv_capex*0.01
    print(f"✅ Total OPEX            : {total_opex:,.2f} MUSD/year")

    return total_opex,df[[
        "Component",
        "Unit",
        "Reference Value",
        "Reference Cost (USD)",
        "Scaling Param",
        "COEFF",
        "Scaled OPEX (USD/y)"
    ]]

