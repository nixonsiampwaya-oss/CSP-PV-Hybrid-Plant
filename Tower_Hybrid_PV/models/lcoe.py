def calculate_lcoe_constant(
    capex_million: float,
    opex_million: float,
    annual_yield: float,
    lifetime: int,
    wacc: float,
    degradation_rate: float = 0.0
) -> float:
    capex = capex_million * 1_000_000
    opex = opex_million * 1_000_000
    pv_opex = sum( opex / (1 + wacc)**n for n in range(1, lifetime+1) )
    pv_energy = sum( (annual_yield * (1 - degradation_rate)**n) / (1 + wacc)**n
                     for n in range(1, lifetime+1) )
    return (capex + pv_opex) / pv_energy
