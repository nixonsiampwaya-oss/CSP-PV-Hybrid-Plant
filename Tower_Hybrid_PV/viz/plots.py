"""
viz/plots.py
Plot weekly PV, Grid, and SoC%. SoC is shown as a red dashed line.
"""
import pandas as pd
import matplotlib.pyplot as plt

def plot_week(df: pd.DataFrame,
              bess_energy_mwh: float,
              week_index: int = 0,
              title: str = "PV Production, Grid Export, and BESS SoC (Week)") -> None:
    """
    Plot a single week (168 hours) of AC_kWh, Grid_kWh, and SOC_% (red dashed).

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing columns: Hour, AC_kWh, Grid_kWh, SOC_MWh
    bess_energy_mwh : float
        Battery capacity to convert SoC to %
    week_index : int
        0-based week selector: 0=first week, 1=second, ...
    title : str
        Plot title
    """
    start = 168 * week_index
    end = start + 168
    df_week = df.iloc[start:end].copy()

    if not {"AC_kWh", "Grid_kWh", "SOC_MWh"}.issubset(df_week.columns):
        raise ValueError("df must contain columns: 'AC_kWh', 'Grid_kWh', 'SOC_MWh'")

    # convert SoC to %
    df_week["SOC_%"] = (df_week["SOC_MWh"] / float(bess_energy_mwh)) * 100.0

    # Create figure
    fig, ax1 = plt.subplots(figsize=(12, 5))

    # Left axis: PV & Grid
    l1, = ax1.plot(df_week["Hour"], df_week["AC_kWh"],  label="PV Production (kWh)", color="orange", linewidth=1.8)
    l2, = ax1.plot(df_week["Hour"], df_week["Grid_kWh"], label="Grid Export (kWh)", color="blue", linewidth=1.8)
    ax1.set_xlabel("Hour of Week")
    ax1.set_ylabel("Energy (kWh)")
    ax1.grid(True, alpha=0.3)

    # Right axis: SoC (%)
    ax2 = ax1.twinx()
    l3, = ax2.plot(df_week["Hour"], df_week["SOC_%"], color="red", linestyle="--", linewidth=1.0, label="BESS SoC (%)")
    ax2.set_ylabel("State of Charge (%)", color="red")
    ax2.set_ylim(0, 100)

    # --- Single combined legend ---
    lines = [l1, l2, l3]
    labels = [line.get_label() for line in lines]
    ax1.legend(lines, labels, loc="upper right")

    plt.title(title)
    plt.tight_layout()
    plt.show()

