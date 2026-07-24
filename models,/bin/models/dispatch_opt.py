import math, os, sys
from pathlib import Path
import pandas as pd
import numpy as np
import pyomo.environ as pyo
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

GLPK_PATH = r"C:\glpk-4.65\w64"

def optimize_dispatch(
    q_csp, e_pv,
    x_price=1.0,
    price_series=None,
    dt=1.0,
    eta_e2h=0.98, eta_ch=0.99, eta_dis=0.99, eta_PB=0.40,
    E_cap=1150, E0_frac=0.50, lambda_loss=0.001,
    PB_e_max=100.0,
    allow_spill=True,
    final_soc_mode=">=E0",
    max_to_grid=100.0,
    objective_mode="revenue",   # <---: "revenue" or "cf_hybrid" or "cf_pb" (optional)
    solarm=3,
):
    assert len(q_csp) == len(e_pv) > 0, "Length mismatch"
    P_ch_max = (PB_e_max/eta_PB)*solarm
    P_dis_max = (PB_e_max/eta_PB)*solarm
    PV_to_heater_max = PB_e_max/eta_PB

    T = range(len(q_csp))
    if price_series is not None:
        assert len(price_series) == len(q_csp)
        price = {t: float(price_series[t]) for t in T}
    else:
        price = {}
        for t in T:
            h = t % 24
            if 0 <= h < 5:
                price[t] = 0.5 * x_price
            elif 17 <= h < 24:
                price[t] = 2.0 * x_price
            else:
                price[t] = 1.0 * x_price

    m = pyo.ConcreteModel()
    m.T = pyo.Set(initialize=T, ordered=True)
    m.Qcsp  = pyo.Param(m.T, initialize={t: float(q_csp[t]) for t in T})
    m.Epv   = pyo.Param(m.T, initialize={t: float(e_pv[t]) for t in T})
    m.price = pyo.Param(m.T, initialize=price)

    m.pv_to_grid   = pyo.Var(m.T, domain=pyo.NonNegativeReals)
    m.pv_to_heater = pyo.Var(m.T, domain=pyo.NonNegativeReals)
    m.csp_to_tes   = pyo.Var(m.T, domain=pyo.NonNegativeReals)
    m.csp_to_pb    = pyo.Var(m.T, domain=pyo.NonNegativeReals)
    m.tes_ch       = pyo.Var(m.T, domain=pyo.NonNegativeReals)
    m.tes_dis      = pyo.Var(m.T, domain=pyo.NonNegativeReals)
    m.E            = pyo.Var(m.T, bounds=(0, E_cap))
    if allow_spill:
        m.spill_pv  = pyo.Var(m.T, domain=pyo.NonNegativeReals)
        m.spill_csp = pyo.Var(m.T, domain=pyo.NonNegativeReals)

    def pv_split(mod, t):
        return mod.pv_to_grid[t] + mod.pv_to_heater[t] + (mod.spill_pv[t] if allow_spill else 0) == mod.Epv[t]
    m.pv_split = pyo.Constraint(m.T, rule=pv_split)

    def csp_split(mod, t):
        return mod.csp_to_pb[t] + mod.csp_to_tes[t] + (mod.spill_csp[t] if allow_spill else 0) == mod.Qcsp[t]
    m.csp_split = pyo.Constraint(m.T, rule=csp_split)

    def grid_export_limit(mod, t):
        return mod.pv_to_grid[t] + eta_PB * (mod.csp_to_pb[t] + mod.tes_dis[t]) <= max_to_grid
    m.grid_limit = pyo.Constraint(m.T, rule=grid_export_limit)

    def tes_charge_eq(mod, t):
        return mod.tes_ch[t] == eta_ch * (eta_e2h*mod.pv_to_heater[t] + mod.csp_to_tes[t])
    m.tes_charge = pyo.Constraint(m.T, rule=tes_charge_eq)

    m.tes_ch_lim  = pyo.Constraint(m.T, rule=lambda mod,t: mod.tes_ch[t]  <= P_ch_max)
    m.tes_dis_lim = pyo.Constraint(m.T, rule=lambda mod,t: mod.tes_dis[t] <= P_dis_max)
    m.pv_heater_lim = pyo.Constraint(m.T, rule=lambda mod, t: mod.pv_to_heater[t] <= PV_to_heater_max)

    def pb_elec_limit(mod, t):
        return eta_PB * (mod.csp_to_pb[t] + mod.tes_dis[t]) <= PB_e_max
    m.pb_limit = pyo.Constraint(m.T, rule=pb_elec_limit)

    # --- Peak-hour share constraint (17:00–23:59 >= 30% of total)
    evening_hours = [t for t in m.T if (t % 24) >= 17]  # hours 17–23 inclusive
    def evening_share_rule(mod):
        total_export = sum(mod.pv_to_grid[t] + eta_PB*(mod.csp_to_pb[t] + mod.tes_dis[t]) for t in mod.T)
        evening_export = sum(mod.pv_to_grid[t] + eta_PB*(mod.csp_to_pb[t] + mod.tes_dis[t]) for t in evening_hours)
        return evening_export >= 0.3 * total_export
    m.evening_share = pyo.Constraint(rule=evening_share_rule)

    E0 = E0_frac * E_cap
    Ts = list(m.T)
    def tes_state(mod, t):
        i = Ts.index(t)
        if i == 0:
            return mod.E[t] == (1 - lambda_loss*dt)*E0 + dt*(mod.tes_ch[t] - mod.tes_dis[t]/eta_dis)
        tprev = Ts[i-1]
        return mod.E[t] == (1 - lambda_loss*dt)*mod.E[tprev] + dt*(mod.tes_ch[t] - mod.tes_dis[t]/eta_dis)
    m.tes_state = pyo.Constraint(m.T, rule=tes_state)

    if final_soc_mode == ">=E0":
        m.final_soc = pyo.Constraint(expr=m.E[Ts[-1]] >= E0)
    elif final_soc_mode == "==E0":
        m.final_soc = pyo.Constraint(expr=m.E[Ts[-1]] == E0)

    # def obj(mod):
    #     pb_elec = {t: eta_PB*(mod.csp_to_pb[t] + mod.tes_dis[t]) for t in mod.T}
    #     return sum(mod.price[t] * (mod.pv_to_grid[t] + pb_elec[t]) * dt for t in mod.T)
    # m.obj = pyo.Objective(rule=obj, sense=pyo.maximize)

    # --- Objective selection ---
    # PB electrical power (symbolic) for each t
    def pb_elec_expr(mod, t):
        return eta_PB * (mod.csp_to_pb[t] + mod.tes_dis[t])

    if objective_mode == "revenue":
        # Your original revenue objective
        def obj(mod):
            return sum(mod.price[t] * (mod.pv_to_grid[t] + pb_elec_expr(mod, t)) * dt for t in mod.T)
    elif objective_mode == "cf_hybrid":
        # Maximize total export energy -> numerator of CF_hybrid
        def obj(mod):
            return sum((mod.pv_to_grid[t] + pb_elec_expr(mod, t)) * dt for t in mod.T)
    elif objective_mode == "cf_pb":
        # Optional: Maximize PB capacity factor (PB output only)
        def obj(mod):
            return sum(pb_elec_expr(mod, t) * dt for t in mod.T)
    else:
        raise ValueError(f"Unknown objective_mode: {objective_mode}")

    m.obj = pyo.Objective(rule=obj, sense=pyo.maximize)



    glpsol_path = str(Path(GLPK_PATH) / "glpsol.exe")
    solver = pyo.SolverFactory("glpk", executable=glpsol_path)
    results = solver.solve(m, tee=False)


    tc = getattr(results.solver, "termination_condition", None)
    st = getattr(results.solver, "status", None)
    if tc != pyo.TerminationCondition.optimal:
        raise RuntimeError(f"Solver not optimal: {st}, {tc}")

    # Build outputs (add CFs so you can inspect them)
    def vget(var): return [pyo.value(var[t]) for t in m.T]
    pb_electric = [eta_PB*(pyo.value(m.csp_to_pb[t]) + pyo.value(m.tes_dis[t])) for t in m.T]
    out = {
        "revenue_total": pyo.value(m.obj) if objective_mode=="revenue" else None,
        "objective_mode": objective_mode,
        "pv_to_grid_MWe": vget(m.pv_to_grid),
        "pv_to_heater_MWe": vget(m.pv_to_heater),
        "csp_to_pb_MWt": vget(m.csp_to_pb),
        "csp_to_tes_MWt": vget(m.csp_to_tes),
        "tes_charge_MWt": vget(m.tes_ch),
        "tes_discharge_MWt": vget(m.tes_dis),
        "tes_energy_MWht": vget(m.E),
        "pb_electric_MWe": pb_electric,
        "price_profile": [pyo.value(m.price[t]) for t in m.T],
        "solver_status": str(st), "termination": str(tc),
    }
    if allow_spill:
        out["spill_pv_MWe"]  = vget(m.spill_pv)
        out["spill_csp_MWt"] = vget(m.spill_csp)

    # ---- Add CFs to outputs for convenience ----
    N = len(out["pb_electric_MWe"])
    E_pv_grid = sum(out["pv_to_grid_MWe"]) * dt
    E_pb_elec = sum(out["pb_electric_MWe"]) * dt
    E_hybrid  = E_pv_grid + E_pb_elec

    CF_hybrid = (E_hybrid / (max_to_grid * N * dt)) if max_to_grid > 0 else float("nan")
    CF_pb = (E_pb_elec / (PB_e_max * N * dt)) if PB_e_max > 0 else float("nan")
    


    return out, m, E_cap, PV_to_heater_max,CF_hybrid,CF_pb,E_hybrid,E_pv_grid,E_pb_elec

def calculate_firm_bonus(res, base_price=1.0, bonus_rate=0.2, margin=0.05, min_hours=3, dt=1.0):
    """
    Compute additional revenue (20%) for periods of ≥3 consecutive hours where
    power export is constant within ±5%.
    """
    # total exported power to grid each hour (MWe)
    P_exp = np.array(res["pv_to_grid_MWe"]) + 0.40 * (np.array(res["csp_to_pb_MWt"]) + np.array(res["tes_discharge_MWt"]))

    # identify firm segments
    firm_hours = np.zeros(len(P_exp), dtype=bool)
    for t in range(1, len(P_exp)):
        if P_exp[t-1] == 0:
            continue
        diff = abs(P_exp[t] - P_exp[t-1]) / max(P_exp[t-1], 1e-6)
        firm_hours[t] = diff <= margin

    # find consecutive runs
    runs = []
    start = None
    for t in range(len(firm_hours)):
        if firm_hours[t]:
            if start is None:
                start = t-1
        else:
            if start is not None:
                runs.append((start, t-1))
                start = None
    if start is not None:
        runs.append((start, len(firm_hours)-1))

    # filter only runs of 3+ hours
    qualified = []
    for s, e in runs:
        if (e - s + 1) >= min_hours:
            qualified.extend(list(range(s, e+1)))

    # compute bonus revenue
    base_prices = np.array(res["price_profile"])
    energy = P_exp * dt  # MWh each step
    base_rev = (base_prices * energy).sum()
    bonus_rev = (base_prices * energy * bonus_rate * np.isin(range(len(P_exp)), qualified)).sum()

    total_rev = base_rev + bonus_rev

    # results summary
    df_bonus = pd.DataFrame({
        "hour": np.arange(len(P_exp)),
        "export_MWe": P_exp,
        "base_price": base_prices,
        "is_firm": np.isin(range(len(P_exp)), qualified),
        "bonus_price": np.where(np.isin(range(len(P_exp)), qualified), base_prices*(1+bonus_rate), base_prices),
    })

    return {
        "bonus_revenue": bonus_rev,
        "total_revenue_with_bonus": total_rev,
        "firm_hours": len(qualified),
        "df_bonus": df_bonus
    }

def export_dispatch_to_csv(out, folder="outputs"):
    """Save timeseries and summary as CSV files."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame({
        "price_EUR_per_MWh": out["price_profile"],
        "pv_to_grid_MWe": out["pv_to_grid_MWe"],
        "pv_to_heater_MWe": out["pv_to_heater_MWe"],
        "csp_to_pb_MWt": out["csp_to_pb_MWt"],
        "csp_to_tes_MWt": out["csp_to_tes_MWt"],
        "tes_charge_MWt": out["tes_charge_MWt"],
        "tes_discharge_MWt": out["tes_discharge_MWt"],
        "tes_energy_MWht": out["tes_energy_MWht"],
        "pb_electric_MWe": out["pb_electric_MWe"],
    })
    if "spill_pv_MWe" in out:
        df["spill_pv_MWe"] = out["spill_pv_MWe"]
    if "spill_csp_MWt" in out:
        df["spill_csp_MWt"] = out["spill_csp_MWt"]

    df.to_csv(folder / "dispatch_timeseries.csv", index_label="timestep")

    # pd.DataFrame({
    #     "metric": ["revenue_total_eur", "solver_status", "termination"],
    #     "value": [out["revenue_total_eur"], out["solver_status"], out["termination"]],
    # }).to_csv(folder / "summary.csv", index=False)

    # print(f"✅ CSV results saved to: {folder.resolve()}")

def plot_week_dispatch(out, week_start_hour=0, hours=168, dt=1.0, save_as=None):
    
    # Convert to DataFrame
    df = pd.DataFrame({
        "pv_to_grid": out["pv_to_grid_MWe"],
        "pb_electric": out["pb_electric_MWe"],
        "price": out["price_profile"],
        # add others you want: tes_energy, spill_pv, etc.
    })
    
    # Create time axis (hours)
    idx = np.arange(len(df)) * dt
    df["hour"] = idx
    
    # Select the week
    mask = (df["hour"] >= week_start_hour) & (df["hour"] < week_start_hour + hours)
    dfw = df.loc[mask].copy()
    
    # Plotting
    fig, ax1 = plt.subplots(figsize=(12,6))
    
    ax1.plot(dfw["hour"], dfw["pv_to_grid"], label="PV to Grid (MWe)", color="tab:blue")
    ax1.plot(dfw["hour"], dfw["pb_electric"], label="PB Electric (MWe)", color="tab:orange")
    ax1.set_xlabel("Hour since start")
    ax1.set_ylabel("Power (MWe)")
    ax1.legend(loc="upper left")
    ax1.grid(True)
    
    # Create second axis for price
    ax2 = ax1.twinx()
    ax2.plot(dfw["hour"], dfw["price"], label="Price (€/MWh)", color="tab:green", linestyle="--")
    ax2.set_ylabel("Price (€/MWh)")
    ax2.legend(loc="upper right")
    
    plt.title(f"Dispatch & Price: hours {week_start_hour}-{week_start_hour+hours}")
    
    if save_as:
        plt.savefig(save_as, dpi=300, bbox_inches="tight")
    else:
        plt.show()
    
    plt.close(fig)

def plot_stack_flows(out, start_hour=4104, hours=4248, dt=1.0, save_as=None):

    # Build DataFrame
    df = pd.DataFrame({
        "pv_to_heater": out["pv_to_heater_MWe"],
        "csp_to_tes":   out["csp_to_tes_MWt"],
        "csp_to_pb":    out["csp_to_pb_MWt"],
        # note: ensure “spill_csp_MWt” key exists when allow_spill=True
        "spill_csp":    out.get("spill_csp_MWt", [0]*len(out["pv_to_heater_MWe"]))
    })
    
    # time axis
    df["hour"] = np.arange(len(df)) * dt
    mask = (df["hour"] >= start_hour) & (df["hour"] < start_hour + hours)
    dfw = df.loc[mask].copy().reset_index(drop=True)
    
    x = dfw["hour"]
    y1 = dfw["pv_to_heater"]
    y2 = dfw["csp_to_tes"]
    y3 = dfw["csp_to_pb"]
    y4 = dfw["spill_csp"]
    
    fig, ax = plt.subplots(figsize=(12,6))
    ax.stackplot(x, y1, y2, y3, y4,
                 labels=['PV→Heater','CSP→TES','CSP→PB','Spill CSP'],
                 colors=['tab:cyan','tab:orange','tab:blue','tab:red'],
                 alpha=0.8)
    
    ax.set_xlabel("Hour since start")
    ax.set_ylabel("Power (MW-th or MW-e) depending on units")
    ax.legend(loc='upper left')
    ax.grid(True)
    plt.title(f"Stacked flows from hour {start_hour} to {start_hour+hours}")
    
    if save_as:
        plt.savefig(save_as, dpi=300, bbox_inches="tight")
    else:
        plt.show()
    plt.close(fig)

def plot_shares_price(out,
                      base_price=1.0,
                      bins=[0, 0.5, 1.0, np.inf],
                      bin_labels=None,
                      dt=1.0,
                      save_as=None):
    """
    Computes the share of exported energy in each price bin and plots as a pie chart.
    
    Parameters:
      out         : dict with keys "price_profile", "pv_to_grid_MWe", "pb_electric_MWe"
      base_price  : float, reference price (€/MWh) to normalise/compare against
      bins        : list of floats defining bin edges as multiples of base_price
      bin_labels  : list of strings for the bins. If None, generated automatically
      dt          : float, hours per timestep (default 1.0)
      save_as     : str or None, filename to save figure. If None, just show
    """
    # Build DataFrame
    df = pd.DataFrame({
        "price": out["price_profile"],
        "pv_to_grid": out["pv_to_grid_MWe"],
        "pb_electric": out["pb_electric_MWe"]
    })
    # Total export power (MWe) each timestep
    df["export_MWe"] = df["pv_to_grid"] + df["pb_electric"]
    # Energy exported each timestep (MWh) = power * dt
    df["export_MWh"] = df["export_MWe"] * dt
    # Normalised price factor
    df["price_factor"] = df["price"] / base_price

    # Define bin labels if not provided
    if bin_labels is None:
        bin_labels = [f"{bins[i]:.1f}-{bins[i+1]:.1f}×" for i in range(len(bins)-1)]
        bin_labels[-1] = f">{bins[-2]:.1f}×"

    # Categorise into bins
    df["price_bin"] = pd.cut(df["price_factor"], bins=bins, labels=bin_labels, include_lowest=True)

    # Compute total exported energy
    total_export = df["export_MWh"].sum()
    if total_export == 0:
        raise ValueError("Total exported energy is zero — nothing to plot.")

    # Compute share of energy per bin
    share = df.groupby("price_bin", observed=False)["export_MWh"].sum() / total_export
    share = share.dropna()  # drop any bins with no data if desired

    # Prepare the pie chart data
    sizes = share.values
    labels = share.index.astype(str).tolist()

    # Define the custom colormap (blue → cyan → green → yellow → red)
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "blue_cyan_green_yellow_red",
        ["blue", "cyan", "green", "yellow", "red"]
    )
    # Map each bin index to a colour
    # Using the number of bins for spacing
    colours = cmap(np.linspace(0, 1, len(sizes)))

    # Plot
    fig, ax = plt.subplots(figsize=(8, 8))
    wedges, texts, autotexts = ax.pie(
        sizes,
        labels=labels,
        colors=colours,
        autopct='%1.1f%%',
        startangle=90,
        textprops={'fontsize': 10}
    )
    ax.axis('equal')  # Equal aspect ratio ensures a circular pie chart.
    ax.set_title("Energy export share by price bin", pad=20)

    # (Optional) adjust label distance, etc
    # e.g., place labels slightly outwards, etc:
    for text in texts:
        text.set_fontsize(9)
    for autotext in autotexts:
        autotext.set_fontsize(8)
        autotext.set_color('white')  # or choose a contrasting colour

    plt.tight_layout()
    if save_as:
        plt.savefig(save_as, dpi=300, bbox_inches='tight')
    else:
        plt.show()
    plt.close(fig)




