import numpy as np
import pandas as pd

def calc_ppa_price(energy_timeseries_mwh,   # e.g., array of MWh for each period (e.g. year)  
                   capex,                   # upfront cost (same currency as price)  
                   opex_per_year,           # annual OPEX (constant)  
                   lifetime_years,          # project lifetime (years)  
                   discount_rate,           # real discount rate (fraction, e.g. 0.07 for 7%)  
                   degradation_rate=0.0,    # yearly degradation fraction (e.g. 0.005 for 0.5%)  
                   inflation_rate=0.0       # inflation rate if modelling nominal terms  
                  ):
    """
    Returns the break-even PPA price (price per MWh) such that NPV = 0.
    energy_timeseries_mwh: array or list of annual MWh production for each year 1..lifetime
    capex: upfront cost at year 0
    opex_per_year: annual O&M cost (year 1..lifetime)
    lifetime_years: number of years
    discount_rate: real discount rate
    degradation_rate: annual production degradation fraction
    inflation_rate: annual inflation (if modelling nominal)
    """
    # Make sure energy_timeseries length is >= lifetime_years or generate it
    if len(energy_timeseries_mwh) < lifetime_years:
        # generate by applying degradation:
        energies = []
        base = energy_timeseries_mwh[0]
        for y in range(lifetime_years):
            energies.append(base * ((1 - degradation_rate) ** y))
    else:
        energies = energy_timeseries_mwh[:lifetime_years]
    
    # We’ll solve for price P so that NPV = 0:
    # NPV = - capex + sum_{t=1..T} [(P * energy_t) - opex] / (1+discount_rate)^t = 0
    # => P = ( capex + sum_{t=1..T} [ opex / (1+dr)^t ] ) / ( sum_{t=1..T}[ energy_t / (1+dr)^t ] )
    
    discount_factors = [(1 + discount_rate) ** t for t in range(1, lifetime_years + 1)]
    
    # present value of OPEX costs
    pv_opex = sum( opex_per_year / df for df in discount_factors )
    
    # present value of energy production
    pv_energy = sum( e / df for e, df in zip(energies, discount_factors) )
    
    # price per MWh needed
    price_per_mwh = ( capex + pv_opex ) / pv_energy
    
    return price_per_mwh

