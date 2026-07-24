# run_nsga.py
import multiprocessing as mp

from nsga_v2 import run_ga   # <-- your GA function must be importable

if __name__ == "__main__":
    mp.freeze_support()                  # required on Windows
    ctx = mp.get_context("spawn")        # Windows-safe start method

    # Call your GA; n_workers=None uses all CPUs
    pareto, pop, df = run_ga(
        pop_size=24,
        ngen=8,
        n_workers=None,
        seed=42,
        results_dir="results"
    )

    # Optional: show a couple of solutions
    print(f"Found {len(pareto)} Pareto solutions.")
    for i, ind in enumerate(pareto[:3], 1):
        print(f"{i}) PPA={ind.fitness.values[0]:.6f}, CF={ind.fitness.values[1]:.4f}, "
              f"PVdc={ind[0]:.0f}, Pref={ind[1]:.1f}, TES={ind[2]:.2f}, SM={ind[3]:.2f}")
