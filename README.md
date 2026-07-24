# Hybrid CSP–PV Plant with Thermal Energy Storage — Techno-Economic Design & Dispatch Optimisation (Spain)

Full design and optimisation of a **142 MW PV + 50 MW CSP trough hybrid plant with 8-hour thermal energy storage** in Ciudad Real, Spain. The work combines site selection, subsystem design in **NREL SAM / PySAM**, a **Mixed-Integer Linear Programming (MILP)** dispatch model, and a **Genetic Algorithm** sizing optimisation in Python to minimise the required electricity bid price under a time-of-day tariff structure.

> Developed for *MJ2500 Large Scale Solar Power* at KTH Royal Institute of Technology (2025), in a five-person team.

📄 **[Full technical report (PDF)](docs/Large_Scale_Solar_Project.pdf)**

---

## Objective

Minimise **X**, the base electricity bid price (USD/MWh), for a hybrid solar plant that must satisfy a minimum CSP capacity share, deliver firm evening-hour generation, and respect a 100 MW grid export limit — while remaining financeable under realistic debt and equity assumptions.

## Site selection

Candidate sites across the EU (Spain, Greece, Cyprus) were screened on solar resource, climate, infrastructure proximity, and topography. **Spain II (38.7311° N, 3.4508° W)** was selected: 1,804 kWh/m² GHI and 2,104 kWh/m² DNI, flat terrain, and under 1 km to a 400 kV transmission line. Higher-irradiance sites in Cyprus and Greece were rejected on infrastructure and grid-connection grounds — a reminder that resource quality alone does not determine project viability.

## Method

1. **Subsystem modelling (PySAM / NREL SAM)** — hourly simulation of the PV array and CSP collector field and receiver over a full meteorological year, with technology and performance data from SAM databases.
2. **PV design optimisation** — module and inverter selection, mounting system comparison, tilt and ground cover ratio optimisation, DC/AC ratio trade-off against LCOE.
3. **CSP design** — trough vs tower comparison across collector and receiver types; solar multiple and TES sizing.
4. **Dispatch optimisation (MILP, Python)** — hourly scheduling of PV-to-grid, PV-to-electric-heater, CSP-to-TES, CSP-to-power-block, and TES charge/discharge to maximise annual revenue under tariff, storage, and export constraints.
5. **Sizing optimisation (Genetic Algorithm)** — search over PV capacity, CSP capacity, TES size, and solar multiple for the lowest feasible X price.

## Selected design

| Parameter | Value |
|---|---|
| PV installed capacity | 142 MW (12,642 strings × 34 modules, Suntech STP330) |
| CSP power block | 50 MW (SkyFuel SkyTrough, Royal Tech receiver) |
| Solar multiple | 2.0 |
| TES capacity | 8 hours / 892 MWh<sub>th</sub> |
| Electric heater | 111 MW<sub>th</sub> |
| Total land area | ~3.4 km² |
| CSP share of capacity | 35% |

## Results

| Metric | Value |
|---|---|
| **X price (bid)** | **52.59 USD/MWh** |
| LCOE | 75.70 USD/MWh |
| CAPEX | 339.7 MUSD |
| OPEX | 3.70 MUSD/year |
| Annual export to grid | 361,075 MWh (PV 234,378 / CSP 126,698) |
| Firm hours delivered | 3,234 h |

**Key findings**

- **Hybridisation pays.** Removing the PV-to-TES link (i.e. two co-located plants instead of an integrated hybrid) cuts CAPEX only marginally — the electric heater is just 3% of CAPEX — but raises the required X price by nearly 5% through lost evening-tariff revenue and bonus.
- **Capital structure outweighs technical tuning.** Sensitivity analysis shows X rises with debt interest rate and required equity return, and falls with higher leverage. The financing structure moves the bid price more than marginal engineering optimisation does.
- **TES shifts generation into the high-tariff evening window.** In summer, CSP heat is stored during the day while PV exports directly; the TES then discharges to the power block through the evening tariff period up to the export limit. Winter operation follows the same logic but requires multi-day storage cycles.
- **Cost concentration:** the CSP solar field dominates CAPEX, followed by balance of plant and engineering; OPEX is led by parasitic electricity consumption and labour.

## Sustainability and community integration

Site layout respects existing agricultural boundaries with low-impact ground cover between rows; environmental impact assessment precedes construction. The design aligns with Spain's 2050 climate neutrality target and includes municipal collaboration and local employment provisions.

## Repository contents

```
├── models/        # PySAM PV and CSP subsystem models
├── optimisation/  # MILP dispatch model and Genetic Algorithm sizing search
├── results/       # Figures: dispatch profiles, CAPEX/OPEX breakdown, sensitivity
├── docs/          # Full report
└── README.md
```

## Team

Alex Blandón · Sze Ching Ma · Ardian Candra Pratama · **Boysonn Siampwaya** · Maghfira Risang Khairiza — KTH Royal Institute of Technology.
