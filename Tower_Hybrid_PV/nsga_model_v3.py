# ga_optimize_hybrid.py
from __future__ import annotations

import os
import csv
import math
import random
import argparse
from pathlib import Path
from functools import lru_cache
from datetime import datetime, timezone
from concurrent.futures import ProcessPoolExecutor

from deap import base, creator, tools  # algorithms not needed

# ------------------------------------------------------------
# Your model: must return a dict with at least:
#   "PPA", "CF_hybrid", "CF_pb", "LCOE",
#   "Annual_Revenue" (or Annual_Revenue_USD),
#   "PV_to_Grid_MWh", "CSP_to_Grid_MWh"
# ------------------------------------------------------------
from model_system import run_hybrid_summary


# =========================
# Search space & utilities
# =========================
BOUNDS = [
    (50_000.0, 300_000.0),  # desired_array_size [kWdc]
    (50.0, 200.0),          # P_ref [MWe]
    (0.0, 16.0),            # t_TES_hours [h]
    (1.0, 5.0),             # solarm [-]
]
RESOLUTION = [500.0, 1.0, 0.5, 0.1]  # snap-to-grid steps

def clamp(val, lo, hi):
    return max(lo, min(hi, val))

def repair(ind):
    """Clamp to bounds and snap to a grid for stability & cache hits."""
    for i, (lo, hi) in enumerate(BOUNDS):
        step = RESOLUTION[i]
        ind[i] = clamp(round(ind[i] / step) * step, lo, hi)
    return ind

def _round_to_grid(vals):
    das, pref, th, sm = vals
    das = round(das / RESOLUTION[0]) * RESOLUTION[0]
    pref = round(pref / RESOLUTION[1]) * RESOLUTION[1]
    th   = round(th   / RESOLUTION[2]) * RESOLUTION[2]
    sm   = round(sm   / RESOLUTION[3]) * RESOLUTION[3]
    return (das, pref, th, sm)

def _get_num(d: dict, *cand_keys, default=None):
    """Robust numeric extractor (accepts numeric strings; rejects NaN/inf)."""
    for k in cand_keys:
        if k in d and d[k] is not None:
            try:
                x = float(d[k])
                if math.isfinite(x):
                    return x
            except Exception:
                pass
    return default


# -------------------------
# Trial logging (ALL calls)
# -------------------------
_TRIAL_LOG = []
_CURRENT_GEN = -1
_SEEN_PARAMS = set()

def _log_trial(gen, das, pref, th, sm,
               ppa, cf, fit_ppa, fit_cf,
               status, note="",
               lcoe=None, annual_rev=None, cf_pb=None,
               pv_mwh=None, csp_mwh=None):
    _TRIAL_LOG.append({
        "gen": gen,
        "desired_array_size": das,
        "P_ref": pref,
        "t_TES_hours": th,
        "solarm": sm,
        "PPA_USD_per_MWh": ppa,
        "CF_hybrid": cf,
        "CF_pb": cf_pb,
        "LCOE": lcoe,
        "Annual_Revenue_USD": annual_rev,
        "PV_to_Grid_MWh": pv_mwh,
        "CSP_to_Grid_MWh": csp_mwh,
        "fitness_PPA": fit_ppa,   # same as PPA unless penalized
        "fitness_CF": fit_cf,     # same as CF unless penalized
        "status": status,
        "note": note,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })

def _write_trials_csv(path: str | Path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = [
        "gen","desired_array_size","P_ref","t_TES_hours","solarm",
        "PPA_USD_per_MWh","CF_hybrid","CF_pb","LCOE",
        "Annual_Revenue_USD","PV_to_Grid_MWh","CSP_to_Grid_MWh",
        "fitness_PPA","fitness_CF","status","note","timestamp"
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for row in _TRIAL_LOG:
            writer.writerow(row)


# =========================
# Evaluators
# =========================
@lru_cache(maxsize=2048)
def _evaluate_cached(desired_array_size, P_ref, t_TES_hours, solarm):
    """
    Single-process (cached) evaluator.
    Returns: (fitness_PPA, fitness_CF, result_dict, status)
    """
    try:
        res = run_hybrid_summary(
            desired_array_size=desired_array_size,
            P_ref=P_ref,
            t_TES_hours=t_TES_hours,
            solarm=solarm,
        )

        # Normalize legacy shapes like (dict,) or (dict, extras...)
        if isinstance(res, tuple) and len(res) >= 1 and isinstance(res[0], dict):
            res = res[0]

        if not isinstance(res, dict):
            return (1e9, -1e9, {}, "penalty_bad_return")

        ppa = _get_num(res, "PPA", "PPA_USD_per_MWh", "ppa_usd_per_mwh")
        cf  = _get_num(res, "CF_hybrid", "CF", "CapacityFactor")

        if ppa is None:
            return (1e9, -1e9, res, "penalty_missing_ppa")
        if cf is None:
            return (ppa, -1e9, res, "penalty_missing_cf")

        return (ppa, cf, res, "ok")

    except Exception as e:
        return (1e9, -1e9, {}, f"exception:{type(e).__name__}")

def _eval_worker(args):
    """
    Process-safe worker for parallel evaluation.
    Returns: (fit_ppa, fit_cf, res_dict, status, das, pref, th, sm)
    """
    das, pref, th, sm = args
    try:
        res = run_hybrid_summary(
            desired_array_size=das,
            P_ref=pref,
            t_TES_hours=th,
            solarm=sm,
        )

        if isinstance(res, tuple) and len(res) >= 1 and isinstance(res[0], dict):
            res = res[0]
        if not isinstance(res, dict):
            return (1e9, -1e9, {}, "penalty_bad_return", das, pref, th, sm)

        ppa = _get_num(res, "PPA", "PPA_USD_per_MWh", "ppa_usd_per_mwh")
        cf  = _get_num(res, "CF_hybrid", "CF", "CapacityFactor")

        if ppa is None:
            return (1e9, -1e9, res, "penalty_missing_ppa", das, pref, th, sm)
        if cf is None:
            return (ppa, -1e9, res, "penalty_missing_cf", das, pref, th, sm)

        return (ppa, cf, res, "ok", das, pref, th, sm)

    except Exception as e:
        return (1e9, -1e9, {}, f"exception:{type(e).__name__}", das, pref, th, sm)

def evaluate(individual):
    """
    Sequential evaluation (used when n_jobs == 1): rounds, caches, logs.
    """
    global _CURRENT_GEN
    repair(individual)
    das, pref, th, sm = _round_to_grid(tuple(individual))

    key = (das, pref, th, sm)
    note = "repeat" if key in _SEEN_PARAMS else "new"
    _SEEN_PARAMS.add(key)

    fit_ppa, fit_cf, res_dict, status = _evaluate_cached(das, pref, th, sm)

    ppa   = res_dict.get("PPA", res_dict.get("PPA_USD_per_MWh"))
    cf    = res_dict.get("CF_hybrid", res_dict.get("CF"))
    lcoe  = res_dict.get("LCOE")
    rev   = res_dict.get("Annual_Revenue", res_dict.get("Annual_Revenue_USD"))
    pv_mw = res_dict.get("PV_to_Grid_MWh")
    csp_mw= res_dict.get("CSP_to_Grid_MWh")
    cf_pb = res_dict.get("CF_pb")

    _log_trial(
        gen=_CURRENT_GEN,
        das=das, pref=pref, th=th, sm=sm,
        ppa=ppa, cf=cf,
        fit_ppa=fit_ppa, fit_cf=fit_cf,
        status=status, note=note,
        lcoe=lcoe, annual_rev=rev, cf_pb=cf_pb,
        pv_mwh=pv_mw, csp_mwh=csp_mw
    )
    return (fit_ppa, fit_cf)


# ================
# DEAP boilerplate
# ================
try:
    creator.FitnessMin2
except AttributeError:
    # weights: (-1 for PPA minimization, +1 for CF maximization)
    creator.create("FitnessMin2", base.Fitness, weights=(-1.0, 1.0))
try:
    creator.Individual
except AttributeError:
    creator.create("Individual", list, fitness=creator.FitnessMin2)

toolbox = base.Toolbox()

def _rand_between(lo, hi):
    return random.uniform(lo, hi)

for i, (lo, hi) in enumerate(BOUNDS):
    toolbox.register(f"attr_{i}", _rand_between, lo, hi)

toolbox.register(
    "individual",
    tools.initCycle,
    creator.Individual,
    (toolbox.attr_0, toolbox.attr_1, toolbox.attr_2, toolbox.attr_3),
    n=1,
)
toolbox.register("population", tools.initRepeat, list, toolbox.individual)
toolbox.register("evaluate", evaluate)

# SBX crossover + polynomial mutation for bounded reals
toolbox.register("mate", tools.cxSimulatedBinaryBounded,
                 low=[b[0] for b in BOUNDS], up=[b[1] for b in BOUNDS], eta=15.0)
toolbox.register("mutate", tools.mutPolynomialBounded,
                 low=[b[0] for b in BOUNDS], up=[b[1] for b in BOUNDS], eta=20.0, indpb=0.25)
toolbox.register("select", tools.selNSGA2)


# =========================
# Main (with parallel eval)
# =========================
def main(seed: int = 42,
         pop_size: int = 24,
         ngen: int = 30,
         cxpb: float = 0.85,
         mutpb: float = 0.25,
         log_csv: str | Path = "ga_trials.csv",
         n_jobs: int | None = None):
    global _CURRENT_GEN
    random.seed(seed)

    # decide parallelism
    if n_jobs is None or n_jobs == 0:
        n_jobs = os.cpu_count() or 2
    elif n_jobs < 0:
        n_jobs = 1

    pop = toolbox.population(n=pop_size)
    hof = tools.ParetoFront()

    stats = tools.Statistics(lambda ind: ind.fitness.values)
    stats.register("min_PPA", lambda fits: min(f[0] for f in fits))
    stats.register("best_CF", lambda fits: max(f[1] for f in fits))

    # ---- Initial evaluation (parallel if n_jobs > 1) ----
    _CURRENT_GEN = 0
    for ind in pop:
        repair(ind)

    if n_jobs == 1:
        # sequential path (evaluate handles logging)
        for ind in pop:
            ind.fitness.values = toolbox.evaluate(ind)
    else:
        params0 = [_round_to_grid(tuple(ind)) for ind in pop]
        with ProcessPoolExecutor(max_workers=n_jobs) as ex:
            results0 = list(ex.map(_eval_worker, params0))

        for ind, (fit_ppa, fit_cf, res_dict, status, das, pref, th, sm) in zip(pop, results0):
            ind.fitness.values = (fit_ppa, fit_cf)

            key = (das, pref, th, sm)
            note = "repeat" if key in _SEEN_PARAMS else "new"
            _SEEN_PARAMS.add(key)

            ppa   = res_dict.get("PPA", res_dict.get("PPA_USD_per_MWh"))
            cf    = res_dict.get("CF_hybrid", res_dict.get("CF"))
            lcoe  = res_dict.get("LCOE")
            rev   = res_dict.get("Annual_Revenue", res_dict.get("Annual_Revenue_USD"))
            pv_mw = res_dict.get("PV_to_Grid_MWh")
            csp_mw= res_dict.get("CSP_to_Grid_MWh")
            cf_pb = res_dict.get("CF_pb")

            _log_trial(
                gen=_CURRENT_GEN,
                das=das, pref=pref, th=th, sm=sm,
                ppa=ppa, cf=cf,
                fit_ppa=fit_ppa, fit_cf=fit_cf,
                status=status, note=f"init; n_jobs={n_jobs}",
                lcoe=lcoe, annual_rev=rev, cf_pb=cf_pb,
                pv_mwh=pv_mw, csp_mwh=csp_mw
            )

    # NSGA-II requires sorting before evolve
    pop = toolbox.select(pop, len(pop))
    hof.update(pop)

    # ---- Generations ----
    for gen in range(1, ngen + 1):
        _CURRENT_GEN = gen

        # Variation
        offspring = tools.selTournamentDCD(pop, len(pop))
        offspring = [toolbox.clone(ind) for ind in offspring]

        # Crossover
        for i in range(0, len(offspring), 2):
            if random.random() < cxpb and i + 1 < len(offspring):
                toolbox.mate(offspring[i], offspring[i + 1])
                repair(offspring[i]); repair(offspring[i + 1])
                if hasattr(offspring[i].fitness, "values"):
                    del offspring[i].fitness.values
                if hasattr(offspring[i + 1].fitness, "values"):
                    del offspring[i + 1].fitness.values

        # Mutation
        for i in range(len(offspring)):
            if random.random() < mutpb:
                toolbox.mutate(offspring[i])
                repair(offspring[i])
                if hasattr(offspring[i].fitness, "values"):
                    del offspring[i].fitness.values

        # Evaluate invalid
        invalid = [ind for ind in offspring if not ind.fitness.valid]
        if invalid:
            if n_jobs == 1:
                for ind in invalid:
                    ind.fitness.values = toolbox.evaluate(ind)
            else:
                params = [_round_to_grid(tuple(ind)) for ind in invalid]
                with ProcessPoolExecutor(max_workers=n_jobs) as ex:
                    results = list(ex.map(_eval_worker, params))

                for ind, (fit_ppa, fit_cf, res_dict, status, das, pref, th, sm) in zip(invalid, results):
                    ind.fitness.values = (fit_ppa, fit_cf)

                    key = (das, pref, th, sm)
                    note = "repeat" if key in _SEEN_PARAMS else "new"
                    _SEEN_PARAMS.add(key)

                    ppa   = res_dict.get("PPA", res_dict.get("PPA_USD_per_MWh"))
                    cf    = res_dict.get("CF_hybrid", res_dict.get("CF"))
                    lcoe  = res_dict.get("LCOE")
                    rev   = res_dict.get("Annual_Revenue", res_dict.get("Annual_Revenue_USD"))
                    pv_mw = res_dict.get("PV_to_Grid_MWh")
                    csp_mw= res_dict.get("CSP_to_Grid_MWh")
                    cf_pb = res_dict.get("CF_pb")

                    _log_trial(
                        gen=_CURRENT_GEN,
                        das=das, pref=pref, th=th, sm=sm,
                        ppa=ppa, cf=cf,
                        fit_ppa=fit_ppa, fit_cf=fit_cf,
                        status=status, note=f"offspring; n_jobs={n_jobs}",
                        lcoe=lcoe, annual_rev=rev, cf_pb=cf_pb,
                        pv_mwh=pv_mw, csp_mwh=csp_mw
                    )

        # Environmental selection
        pop = toolbox.select(pop + offspring, len(pop))
        hof.update(pop)

        # Stats
        fits = [ind.fitness.values for ind in pop]
        min_ppa = min(f[0] for f in fits)
        best_cf = max(f[1] for f in fits)
        print(f"Gen {gen:>3}/{ngen} | min PPA: {min_ppa:.3f} USD/MWh | best CF: {best_cf:.4f}")

    # Report Pareto
    print("\n=== Pareto front (PPA, CF) ===")
    for ind in hof:
        ppa, cf = ind.fitness.values
        print(
            f"das={ind[0]:.0f} kWdc | P_ref={ind[1]:.1f} MWe | TES={ind[2]:.1f} h | SM={ind[3]:.1f} "
            f"| PPA={ppa:.2f} USD/MWh | CF={cf:.4f}"
        )

    # Convenience: best-by-PPA
    best_by_ppa = min(hof, key=lambda x: x.fitness.values[0])
    ppa, cf = best_by_ppa.fitness.values
    print("\nBest-by-PPA candidate:")
    print(
        f"das={best_by_ppa[0]:.0f} kWdc | P_ref={best_by_ppa[1]:.1f} MWe | TES={best_by_ppa[2]:.1f} h | SM={best_by_ppa[3]:.1f} "
        f"| PPA={ppa:.2f} USD/MWh | CF={cf:.4f}"
    )

    # Save trials
    _write_trials_csv(log_csv)
    print(f"\nSaved ALL trials to: {Path(log_csv).resolve()}")

    return pop, hof


# =========================
# CLI
# =========================
def _parse_args():
    p = argparse.ArgumentParser(description="NSGA-II optimization of hybrid PV–CSP–TES (parallel).")
    p.add_argument("--seed", type=int, default=123, help="Random seed.")
    p.add_argument("--pop", type=int, default=24, help="Population size.")
    p.add_argument("--gens", type=int, default=20, help="Number of generations.")
    p.add_argument("--cxpb", type=float, default=0.9, help="Crossover probability.")
    p.add_argument("--mutpb", type=float, default=0.3, help="Mutation probability.")
    p.add_argument("--jobs", type=int, default=os.cpu_count() or 2, help="Parallel processes (>=1).")
    p.add_argument("--csv", default="ga_trials.csv", help="CSV path for trial logs.")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    main(seed=args.seed,
         pop_size=args.pop,
         ngen=args.gens,
         cxpb=args.cxpb,
         mutpb=args.mutpb,
         log_csv=args.csv,
         n_jobs=max(1, args.jobs))
