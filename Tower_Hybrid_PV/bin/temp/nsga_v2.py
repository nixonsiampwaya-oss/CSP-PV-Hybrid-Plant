from __future__ import annotations
import os
import random
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from deap import base, creator, tools, algorithms
from multiprocessing import Pool, cpu_count

# Your model
from model_system import run_hybrid_summary

# ============================================
# Decision variables & bounds
# ============================================
# Tune these bounds to your design space
PV_MIN,   PV_MAX   = 50_000.0, 300_000.0   # kWdc (50–300 MWdc)
PREF_MIN, PREF_MAX = 20.0,     200.0       # MWe  (CSP PB rating)
TESH_MIN, TESH_MAX = 2.0,      18.0        # hours
SMIN,     SMAX     = 1.5,      4.0         # Solar multiple

# ============================================
# Fitness: minimize PPA, maximize CF_hybrid
# ============================================
try:
    creator.create("FitnessMinMax", base.Fitness, weights=(-1.0, 1.0))
except Exception:
    pass

try:
    creator.create("Individual", list, fitness=creator.FitnessMinMax)
except Exception:
    pass

toolbox = base.Toolbox()

# Genes
toolbox.register("attr_pv",   random.uniform, PV_MIN,   PV_MAX)
toolbox.register("attr_pref", random.uniform, PREF_MIN, PREF_MAX)
toolbox.register("attr_tesh", random.uniform, TESH_MIN, TESH_MAX)
toolbox.register("attr_sm",   random.uniform, SMIN,     SMAX)

# Individual: [desired_array_size, P_ref, t_TES_hours, solarm]
toolbox.register(
    "individual",
    tools.initCycle,
    creator.Individual,
    (toolbox.attr_pv, toolbox.attr_pref, toolbox.attr_tesh, toolbox.attr_sm),
    n=1
)
toolbox.register("population", tools.initRepeat, list, toolbox.individual)

# ============================================
# Evaluation wrapper
# ============================================
def eval_individual(ind):
    desired_array_size = float(ind[0])
    P_ref              = float(ind[1])
    t_TES_hours        = float(ind[2])
    solarm             = float(ind[3])

    # Soft bounds check (shouldn't trigger often with bounded mutation)
    penalty = 0.0
    if not (PV_MIN <= desired_array_size <= PV_MAX): penalty += 1e6
    if not (PREF_MIN <= P_ref <= PREF_MAX):         penalty += 1e6
    if not (TESH_MIN <= t_TES_hours <= TESH_MAX):   penalty += 1e6
    if not (SMIN <= solarm <= SMAX):                penalty += 1e6

    try:
        out = run_hybrid_summary(
            desired_array_size=desired_array_size,
            P_ref=P_ref,
            t_TES_hours=t_TES_hours,
            solarm=solarm,
        )
        # Objectives
        ppa = float(out["PPA"]) + penalty                 # minimize
        cfh = float(out["CF_hybrid"])                     # maximize

        # Attach the full result for logging via a side channel on the individual
        ind._last_result = out
        return (ppa, cfh)

    except Exception as e:
        # On failure, return terrible fitness to discard
        ind._last_result = {"error": str(e)}
        return (1e12, -1e12)

toolbox.register("evaluate", eval_individual)

# Operators (NSGA-II)
toolbox.register("mate", tools.cxBlend, alpha=0.5)
toolbox.register(
    "mutate",
    tools.mutPolynomialBounded,
    eta=20.0,
    low=[PV_MIN, PREF_MIN, TESH_MIN, SMIN],
    up=[PV_MAX, PREF_MAX, TESH_MAX, SMAX],
    indpb=0.5,
)
toolbox.register("select", tools.selNSGA2)

# ============================================
# GA runner
# ============================================
def run_ga(
    pop_size: int = 60,
    ngen: int = 40,
    cxpb: float = 0.8,
    mutpb: float = 0.2,
    seed: int = 42,
    results_dir: str = "results",
    trials_csv: str = "ga_trials.csv",
    n_workers: int | None = None,          # <--- NEW
):
    random.seed(seed)
    np.random.seed(seed)
    os.makedirs(results_dir, exist_ok=True)

    if n_workers is None:
        n_workers = cpu_count()

    # Trial logger
    trial_log = []

    def log_trial(ind, gen_idx: int):
        ppa = float(ind.fitness.values[0])
        cfh = float(ind.fitness.values[1])
        payload = getattr(ind, "_last_result", {}) or {}
        trial_log.append({
            "generation": gen_idx,
            "desired_array_size": float(ind[0]),
            "P_ref": float(ind[1]),
            "t_TES_hours": float(ind[2]),
            "solarm": float(ind[3]),
            "PPA": ppa,
            "CF_hybrid": cfh,
            "desired_array_size_ret": payload.get("desired_array_size", float(ind[0])),
            "P_ref_ret": payload.get("P_ref", float(ind[1])),
            "t_TES_hours_ret": payload.get("t_TES_hours", float(ind[2])),
            "PPA_ret": payload.get("PPA", ppa),
            "CF_hybrid_dup": payload.get("CF_hybrid_dup", cfh),
            "CF_pb_dup": payload.get("CF_pb_dup", np.nan),
            "LCOE": payload.get("LCOE", np.nan),
            "Annual_Revenue": payload.get("Annual_Revenue", np.nan),
            "PV_to_Grid_MWh": payload.get("PV_to_Grid_MWh", np.nan),
            "CSP_to_Grid_MWh": payload.get("CSP_to_Grid_MWh", np.nan),
        })

    # Init population
    pop = toolbox.population(n=pop_size)

    # Use a process pool for parallel evals
    with Pool(processes=n_workers) as pool:
        toolbox.register("map", pool.map)

        # ---------- Initial population (parallel) ----------
        fitnesses = list(toolbox.map(toolbox.evaluate, pop))
        for ind, fit in zip(pop, fitnesses):
            ind.fitness.values = fit
            log_trial(ind, gen_idx=0)

        # NSGA-II bookkeeping
        pop = toolbox.select(pop, k=len(pop))
        pareto = tools.ParetoFront()

        # Simple stats
        def _ppa_vals(inds): return [ind.fitness.values[0] for ind in inds]
        def _cf_vals(inds):  return [ind.fitness.values[1] for ind in inds]

        stats = tools.Statistics(lambda ind: ind)
        stats.register("ppa_min", lambda inds: min(_ppa_vals(inds)) if inds else float("nan"))
        stats.register("ppa_avg", lambda inds: (sum(_ppa_vals(inds))/len(inds)) if inds else float("nan"))
        stats.register("cf_max",  lambda inds: max(_cf_vals(inds)) if inds else float("nan"))
        stats.register("cf_avg",  lambda inds: (sum(_cf_vals(inds))/len(inds)) if inds else float("nan"))

        # ---------- Evolution loop ----------
        for gen in range(1, ngen + 1):
            offspring = algorithms.varAnd(pop, toolbox, cxpb=cxpb, mutpb=mutpb)

            # Evaluate only invalid offspring (parallel)
            invalid = [ind for ind in offspring if not ind.fitness.valid]
            if invalid:
                fitnesses = list(toolbox.map(toolbox.evaluate, invalid))
                for ind, fit in zip(invalid, fitnesses):
                    ind.fitness.values = fit

            # Log all offspring for this generation
            for ind in offspring:
                log_trial(ind, gen_idx=gen)

            # Environmental selection
            pop = toolbox.select(pop + offspring, k=pop_size)

            # Update Pareto
            pareto.update(pop)

            # Progress
            rec = stats.compile(pop)
            print(
                f"Gen {gen:03d} | "
                f"PPA[min/avg]: {rec['ppa_min']:.6f}/{rec['ppa_avg']:.6f} | "
                f"CF[max/avg]: {rec['cf_max']:.4f}/{rec['cf_avg']:.4f}"
            )

        # pool is auto-closed by the context manager

    # Save trials
    df_trials = pd.DataFrame(trial_log)
    csv_path = os.path.join(results_dir, trials_csv)
    df_trials.to_csv(csv_path, index=False)
    print(f"\nSaved trials to: {csv_path}")

    print("\n=== Pareto Front (non-dominated) ===")
    for i, ind in enumerate(pareto):
        print(
            f"{i+1:02d}) PPA={ind.fitness.values[0]:.6f}, "
            f"CF_hybrid={ind.fitness.values[1]:.4f}, "
            f"PVdc={ind[0]:,.0f} kWdc, P_ref={ind[1]:.1f} MWe, "
            f"TES={ind[2]:.2f} h, SM={ind[3]:.2f}"
        )

    return pareto, pop, df_trials


def choose_compromise(pareto) -> creator.Individual:
    """
    Knee-ish compromise: minimize (w1*PPA - w2*CF).
    Tune weights per your preferences.
    """
    def score(ind, w1=1.0, w2=1.0):
        return w1 * ind.fitness.values[0] - w2 * ind.fitness.values[1]
    return min(pareto, key=score)


def plot_pareto_ppa_vs_cf(
    df_trials: pd.DataFrame,
    pareto: tools.ParetoFront,
    out_path: str = "results/pareto_ppa_vs_cf.png",
):
    """Scatter all trials (x = CF_hybrid, y = PPA) and highlight Pareto."""
    plt.figure(figsize=(8, 6), dpi=150)

    plt.scatter(
        df_trials["CF_hybrid"],
        df_trials["PPA"],
        s=18, alpha=0.5, label="All trials", edgecolors="none"
    )

    pf_x = [ind.fitness.values[1] for ind in pareto]  # CF
    pf_y = [ind.fitness.values[0] for ind in pareto]  # PPA

    if len(pf_x) > 1:
        order = np.argsort(pf_x)
        pf_x = np.array(pf_x)[order]
        pf_y = np.array(pf_y)[order]

    plt.plot(pf_x, pf_y, linewidth=2.0, alpha=0.9, label="Pareto front")
    plt.scatter(pf_x, pf_y, s=60, alpha=1.0, label="Non-dominated", zorder=3)

    plt.xlabel("CF_hybrid [-]")
    plt.ylabel("PPA [USD per (same unit as model)]")
    plt.title("Pareto Front: PPA vs CF_hybrid")
    plt.grid(True, linestyle="--", alpha=0.4)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()
    print(f"Saved Pareto plot to: {out_path}")