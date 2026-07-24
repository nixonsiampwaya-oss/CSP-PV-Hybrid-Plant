import os
import numpy as np
import pandas as pd
import PySAM.Pvwattsv8 as pv

def run_pvwatts(weather_path: str,
                out_dir: str = "output_data",
                system_capacity_kwdc: float = 10_000,
                dc_ac_ratio: float = 1.2,
                array_type: int = 1,
                tilt: float = 25.0,
                azimuth: float = 180.0,
                gcr: float = 0.4,
                losses_percent: float = 14.0,
                lifetime_output: bool = False):

    # Ensure output directory exists
    os.makedirs(out_dir, exist_ok=True)

    # Instantiate the model
    m = pv.default("PVWattsNone")

    # Weather
    m.SolarResource.solar_resource_file = weather_path

    # System Design
    m.SystemDesign.system_capacity = system_capacity_kwdc
    m.SystemDesign.dc_ac_ratio = dc_ac_ratio
    m.SystemDesign.array_type = array_type
    m.SystemDesign.tilt = tilt
    m.SystemDesign.azimuth = azimuth
    m.SystemDesign.gcr = gcr
    m.SystemDesign.losses = losses_percent

    # Lifetime output control
    m.Lifetime.system_use_lifetime_output = int(lifetime_output)

    # Run the model
    m.execute()

    # Extract results
    annual_energy_kwh = m.Outputs.annual_energy
    capacity_factor = m.Outputs.capacity_factor
    ac_kw = np.array(m.Outputs.ac)
    poa = np.array(m.Outputs.poa)

    # Build DataFrame
    df = pd.DataFrame({
        "Hour": np.arange(1, len(ac_kw) + 1),
        "AC_kW": ac_kw,
        "POA_kWh/m2": poa
    })

    # Save timeseries to CSV
    output_file = os.path.join(out_dir, "pv_ac_timeseries.csv")
    df.to_csv(output_file, index=False)

    print("=== PySAM PVWatts Run ===")
    print(f"Annual Energy: {annual_energy_kwh:,.0f} kWh")
    print(f"Capacity Factor: {capacity_factor:.2f} %")
    print(f"Saved hourly AC power to {output_file}")

    # Return results in a dictionary
    return {
        "annual_energy_kwh": annual_energy_kwh,
        "capacity_factor": capacity_factor,
        "timeseries_df": df
    }
