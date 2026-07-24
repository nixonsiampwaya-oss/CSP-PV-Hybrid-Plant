import pandas as pd
import numpy as np

coeff_data = [
    ["CSP Power Block", 0.8],
    ["CSP BOP", 0.8],
    ["CSP SF", 1],
    ["CSP TES", 0.8],
    ["CSP Receiver", 0.2],
    ["CSP Tower", 0.8],
    ["CSP Site Preparations / Civil works", 0.9],
    ["Electric Heater", 1],
    ["Grid Connection Costs", 1],
    ["Road Costs", 1],
    ["Gas Pipeline Costs", 1],
    ["Water Pipeline Costs", 1],
    ["Battery Pack - Power", 1],
    ["Battery Pack - Capacity", 1],
    ["Other Component", 1],
    ["PV Modules", 1],
    ["PV Inverters", 1],
    ["PV BOS (except Inverters)", 1],
    ["PV additional rack (SA tracking)", 1],
    ["PV Site Preperations / Civil works", 1]
]

ref_params = [
    ["CSP Power Block", "kW", 190000],
    ["CSP BOP", "kW", 110000],
    ["CSP SF", "m2", 1000000],
    ["CSP TES", "MWh-th", 3271],
    ["CSP Receiver", "MW-th", 565],
    ["CSP Tower", "m", 200],
    ["CSP Site Preparations / Civil works", "m2", 5000000],
    ["Electric Heater", "kW", 1000000],
    ["Grid Connection Costs", "km", 1],
    ["Road Costs", "km", 1],
    ["Gas Pipeline Costs", "km", 1],
    ["Water Pipeline Costs", "km", 1],
    ["Battery Pack - Power", "MW", 1],
    ["Battery Pack - Capacity", "MWh-e", 1],
    ["Other Component", "-", 1],
    ["PV Modules", "Wdc-peak", 1000000],
    ["PV Inverters", "Wdc-peak", 1000000],
    ["PV BOS (except Inverters)", "Wdc-peak", 1000000],
    ["PV additional rack (SA tracking)", "Wdc-peak", 1000000],
    ["PV Site Preperations / Civil works", "m2", 5000]
]

ref_cost_data = [
    ["CSP Power Block", "kW", 190000, 87.50, "MUSD"],
    ["CSP BOP", "kW", 110000, 74.8, "MUSD"],
    ["CSP SF", "m2", 1000000, 125.00, "MUSD"],
    ["CSP TES", "MWh-th", 3271, 66.00, "MUSD"],
    ["CSP Receiver", "MW-th", 565, 55.00, "MUSD"],
    ["CSP Tower", "m", 200, 30.00, "MUSD"],
    ["CSP Site Preparations / Civil works", "m2", 5000000, 10.00, "MUSD"],
    ["Electric Heater", "kW", 1000000, 70.00, "MUSD"],
    ["Grid Connection Costs", "km", 1, 1.50, "MUSD"],
    ["Road Costs", "km", 1, 1.20, "MUSD"],
    ["Gas Pipeline Costs", "km", 1, 1.00, "MUSD"],
    ["Water Pipeline Costs", "km", 1, 1.00, "MUSD"],
    ["Battery Pack - Power", "MW", 1, 0.23, "MUSD"],
    ["Battery Pack - Capacity", "MWh-e", 1, 0.30, "MUSD"],
    ["Other Component", "-", 1, 0.00, "MUSD"],
    ["PV Modules", "Wdc-peak", 1000000, 0.33, "MUSD"],
    ["PV Inverters", "Wdc-peak", 1000000, 0.10, "MUSD"],
    ["PV BOS (except Inverters)", "Wdc-peak", 1000000, 0.30, "MUSD"],
    ["PV additional rack (SA tracking)", "Wdc-peak", 1000000, 0.20, "MUSD"],
    ["PV Site Preperations / Civil works", "m2", 5000, 0.01, "MUSD"]
]

# scaling_data = [
#     ["CSP Power Block", 100000],
#     ["CSP BOP",  100000],
#     ["CSP SF", 507597.5],
#     ["CSP TES", 3271.3],
#     ["CSP Receiver", 200],
#     ["CSP Tower", 200],
#     ["CSP Site Preparations / Civil works", 2000000],
#     ["Electric Heater", 200000],
#     ["Grid Connection Costs", 4],
#     ["Road Costs", 2],
#     ["Gas Pipeline Costs", 5],
#     ["Water Pipeline Costs", 10],
#     ["Battery Pack - Power", 150],
#     ["Battery Pack - Capacity", 300],
#     ["Other Component", 0],
#     ["PV Modules", 270327760],
#     ["PV Inverters", 270327760],
#     ["PV BOS (except Inverters)", 270327760],
#     ["PV additional rack (SA tracking)", 270327760],
#     ["PV Site Preperations / Civil works", 1000000]
# ]

coeff_df = pd.DataFrame(coeff_data, columns=["Component", "COEFF"])
ref_df = pd.DataFrame(ref_params, columns=["Component", "Unit", "Value"])
ref_cost_df = pd.DataFrame(ref_cost_data, columns=["Component", "Unit", "Reference Value", "Specific Cost", "Cost Unit"])
# scaling_df = pd.DataFrame(scaling_data, columns=["Component", "Scaling Param"])

def calculate_capex(
    scaling_df: pd.DataFrame,    # Only this needs to be passed in
    ref_cost_df: pd.DataFrame = ref_cost_df,  
    ref_df: pd.DataFrame = ref_df,      
    coeff_df: pd.DataFrame = coeff_df,    
    contingency_frac: float = 0.10,
    pct_developer: float = 0.07,
    pct_financial: float = 0.00,
    pct_engineering: float = 0.14,
    return_breakdown: bool = True,
) -> pd.DataFrame:
    # Merge all base data
    df = (
        ref_cost_df
        .merge(ref_df, on="Component", how="left", suffixes=("_cost", "_ref"))
        .merge(scaling_df, on="Component", how="left")
        .merge(coeff_df, on="Component", how="left")
    )

    for c in ["Reference Value", "Specific Cost", "Scaling Param", "COEFF"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["Scaled Cost (MUSD)"] = df["Specific Cost"] * (df["Scaling Param"]/df["Reference Value"])**df["COEFF"]

    # Direct CAPEX subtotal + contingency
    direct_subtotal = df["Scaled Cost (MUSD)"].sum()
    direct_with_cont = direct_subtotal * (1 + contingency_frac)

    # Indirect CAPEX
    developer_cost   = direct_with_cont * pct_developer
    financial_cost   = direct_with_cont * pct_financial
    engineering_cost = direct_with_cont * pct_engineering
    indirect_total   = developer_cost + financial_cost + engineering_cost

    # Total CAPEX
    total_capex = direct_with_cont + indirect_total

    # Prepare output
    df_out = df[[
        "Component",
        "Reference Value",
        "Scaling Param",
        "COEFF",
        "Specific Cost",
        "Scaled Cost (MUSD)",
        "Cost Unit"
    ]].copy()

    if return_breakdown:
        summary_rows = [
            {"Component": "DIRECT CAPEX Sub-Total", "Scaled Cost (MUSD)": round(direct_subtotal, 2)},
            {"Component": f"Contingency ({contingency_frac:.0%})", "Scaled Cost (MUSD)": round(direct_with_cont - direct_subtotal, 2)},
            {"Component": f"Developer ({pct_developer:.0%})", "Scaled Cost (MUSD)": round(developer_cost, 2)},
            {"Component": f"Financial ({pct_financial:.0%})", "Scaled Cost (MUSD)": round(financial_cost, 2)},
            {"Component": f"Engineering ({pct_engineering:.0%})", "Scaled Cost (MUSD)": round(engineering_cost, 2)},
            {"Component": "INDIRECT CAPEX Sub-Total", "Scaled Cost (MUSD)": round(indirect_total, 2)},
            {"Component": "TOTAL CAPEX", "Scaled Cost (MUSD)": round(total_capex, 2)},
        ]
        df_out = pd.concat([df_out, pd.DataFrame(summary_rows)], ignore_index=True)

    pv_components = [
    "PV Modules",
    "PV Inverters",
    "PV BOS (except Inverters)",
    "PV additional rack (SA tracking)",
    "PV Site Preperations / Civil works",
]
    # print(f"✅ Total DIRECT CAPEX    : {direct_with_cont:.2f} MUSD")
    # print(f"✅ Total INDIRECT CAPEX  : {indirect_total:.2f} MUSD")
    print(f"✅ Total CAPEX           : {total_capex:.2f} MUSD")
    return total_capex, df_out, pv_components

