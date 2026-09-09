"""
Static EEV_t / VSS_t chain (Escudero, Garin, Merino & Perez 2007, Definition 1).

Unlike the dynamic EDEV_t chain (run_vssd.py, Definition 4), this chain's
fixing source is the classical, single, ungrouped EV problem: every random
parameter replaced by its one overall (unconditional) expectation across all
300 real scenarios, solved once for the whole horizon. Every stage's fixed
decisions (x_1, ..., x_{t-1}) come from that ONE solve, broadcast identically
to every real scenario -- not from the dynamic chain's 30 independently-solved
G_1 groups. This distinction matters concretely: an earlier attempt at a
"EEV_2" comparator reused the dynamic chain's already-computed, per-group EV_1
values (30 independent single-scenario solves, one per DA offer-curve point)
as the fixing source, which produced a genuine, non-converging infeasibility --
DA_bid_mono requires the 300 real scenarios' DA quantities to be monotonic in
their own real prices, but nothing ties 30 independently-optimal group values
to any common ordering (each EV_g subproblem is single-scenario, blind to
every other group). A single classical EV value, applied identically to every
real scenario, trivially satisfies DA_bid_mono (equal values satisfy both
<= and >=), so no per-group construction or curve-consistency remedy is
needed here.

Each EEV_t (t=2..6) is solved once as a genuine joint multi-scenario problem
over all 300 real scenarios (RP's own model plus one extra fixing constraint
-- Proposition 1's subset argument, hence EEV_t <= RP by construction), with
Gurobi-IIS-based scenario exclusion (Definition 3's own remedy) as the safety
net for any other, unrelated infeasibility.

This script is fully decoupled from the normal pipeline and from run_vssd.py's
own dynamic chain, though it reuses solve_rp() (identical RP solve, same
market="DA" model) rather than duplicating it. Never modifies model_builder.py,
instancemanager.py, preprocessing.py, config_definition.py, or run_vssd.py.

Usage (from the codes/ directory, or anywhere -- this script fixes up sys.path):
    python vssd/run_static_vss.py        # runs every sim in cfg.SIMS (parallel),
                                          # writes the cross-day summary
                                          # (tables/vss_t.txt, vss_static_<famscen>
                                          # _summary.out) alongside each day's own
                                          # static_vss_results.csv
    python vssd/run_static_vss.py <sim>  # runs a single sim only (e.g. "001"),
                                          # no cross-day summary
"""
import os
import sys

_CODES_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CODES_DIR not in sys.path:
    sys.path.insert(0, _CODES_DIR)

import csv
import multiprocessing as mp

from pyomo.environ import value

import config_definition as cfg
from vssd.scenario_groups import ScenarioGroup, MACRO_STAGES
from vssd.ev_subproblem import (
    build_ev_instance,
    snapshot_solution,
    newly_decided_at_stage,
    solve_ev_instance,
    solve_full_instance_with_exclusion,
)
from vssd.run_vssd import solve_rp


def solve_classical_ev(rp_instance, rp_scenario_data, abstract_model):
    """
    Definition 1's fixing source: ONE deterministic solve, every random
    parameter replaced by its overall (unconditional) expectation over all 300
    real scenarios -- not the dynamic chain's per-group conditional averages.
    Implemented by reusing build_ev_instance() with a single synthetic "group"
    whose omega spans every real scenario (weight = total probability).
    """
    all_scenarios = tuple(sorted(int(s) for s in rp_instance.S))
    total_weight = sum(value(rp_instance.Prob[s]) for s in all_scenarios)
    universal_group = ScenarioGroup(
        stage=0, sg=0, group_id=0, omega=all_scenarios, weight=total_weight, parent_id=None,
    )
    instance = build_ev_instance(abstract_model, rp_instance, rp_scenario_data, universal_group)
    z_ev, status = solve_ev_instance(instance, label="classical EV")
    if z_ev is None:
        raise RuntimeError(
            f"Classical EV problem is infeasible (status={status}) -- the static "
            f"EEV_t/VSS_t chain has no fixing source."
        )
    return z_ev, snapshot_solution(instance)


def compute_static_chain(sim):
    print(f"=== Static EEV_t/VSS_t (Escudero et al. 2007, Definition 1) -- sim {sim} ===")

    print("\n-- Solving RP (market='DA') --")
    rp_instance, rp_scenario_data, abstract_model, sim_ctx = solve_rp(sim)
    rp_value = value(rp_instance.EECSW)
    print(f"RP = {rp_value:.4f}")

    print("\n-- Solving the classical EV problem (single scenario, overall expectation) --")
    z_ev, ev_snapshot = solve_classical_ev(rp_instance, rp_scenario_data, abstract_model)
    print(f"EV = {z_ev:.4f}")

    eev_by_stage = {1: rp_value}
    excluded_weight_by_stage = {1: 0.0}

    for t in range(2, 7):
        print(f"\n-- Computing EEV_{t} (fix x_1..x_{t - 1} at the classical EV's "
              f"solved values, re-solve the rest for all {len(rp_instance.S)} real "
              f"scenarios) --")
        fixed_specs = []
        for tau in range(1, t):
            fixed_specs += newly_decided_at_stage(tau, rp_instance)

        def fix_fn(instance, surviving_scenarios, fixed_specs=fixed_specs):
            for var_name, idx_list in fixed_specs:
                var_obj = getattr(instance, var_name)
                for idx in idx_list:
                    val = ev_snapshot[var_name][idx + (1,)]
                    for s in surviving_scenarios:
                        var_obj[idx + (s,)].set_value(val)
                        var_obj[idx + (s,)].fix()

        z_eev, excluded_weight = solve_full_instance_with_exclusion(
            sim_ctx, abstract_model, rp_scenario_data, rp_instance, fix_fn, label=f"EEV_{t}"
        )
        eev_by_stage[t] = z_eev
        excluded_weight_by_stage[t] = excluded_weight
        if z_eev is None:
            print(f"EEV_{t}: infeasible even after exclusion "
                  f"(excluded {excluded_weight:.4f} probability mass)")
        else:
            print(f"EEV_{t} = {z_eev:.4f}"
                  + (f"  (excluded {excluded_weight:.4f} infeasible probability mass, renormalized)"
                     if excluded_weight > 0 else ""))

    vss_by_stage = {
        t: (rp_value - eev_by_stage[t] if eev_by_stage[t] is not None else None)
        for t in range(1, 7)
    }
    print(f"\nVSS_1 = RP - EEV_1 = {vss_by_stage[1]:.4f}")
    for t in range(2, 7):
        if vss_by_stage[t] is not None:
            print(f"VSS_{t} = RP - EEV_{t} = {rp_value:.4f} - {eev_by_stage[t]:.4f} = {vss_by_stage[t]:.4f}")
        else:
            print(f"VSS_{t} = undefined (EEV_{t} infeasible)")

    _write_results_csv(sim_ctx, rp_value, z_ev, eev_by_stage, vss_by_stage, excluded_weight_by_stage)

    return {
        "sim": sim,
        "rp_value": rp_value,
        "ev_value": z_ev,
        "eev_by_stage": eev_by_stage,
        "vss_by_stage": vss_by_stage,
        "excluded_weight_by_stage": excluded_weight_by_stage,
    }


def _write_results_csv(sim_ctx, rp_value, z_ev, eev_by_stage, vss_by_stage, excluded_weight_by_stage):
    out_path = os.path.join(cfg.PROJECT_ROOT, sim_ctx.pathres, "static_vss_results.csv")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["stage_t", "market", "EEV_t", "VSS_t", "excluded_infeasible_weight"])
        for t in range(1, 7):
            writer.writerow([t, MACRO_STAGES[t - 1], eev_by_stage[t], vss_by_stage[t],
                              excluded_weight_by_stage[t]])
        writer.writerow([])
        writer.writerow(["RP", rp_value])
        writer.writerow(["EV", z_ev])
    print(f"\nResults written to {out_path}")


def _write_summary(chain_results):
    """Aggregates one compute_static_chain() result per sim into cross-day
    tables, mirroring run_vssd.py's _write_summary() pattern for the dynamic
    chain (results/<famscen>/DA/tables/, results/<famscen>/DA/)."""
    table_dir = os.path.join(cfg.PROJECT_ROOT, "results", cfg.famscen_all, "DA", "tables")
    os.makedirs(table_dir, exist_ok=True)

    vss_t_path = os.path.join(table_dir, "vss_t.txt")
    with open(vss_t_path, "w") as f:
        f.write("stage    " + " ".join(f"{r['sim']:>7s}" for r in chain_results) + "\n")
        for t in range(1, 7):
            f.write(
                f"VSS_{t}   "
                + " ".join(
                    (f"{r['vss_by_stage'][t]:7.2f}" if r["vss_by_stage"][t] is not None else "    n/a")
                    for r in chain_results
                )
                + "\n"
            )

    summary_path = os.path.join(
        cfg.PROJECT_ROOT, "results", cfg.famscen_all, "DA", f"vss_static_{cfg.famscen_all}_summary.out"
    )
    with open(summary_path, "w") as f:
        f.write("############################################################\n")
        f.write(f"Static VSS summary ({len(chain_results)} days)\n")
        f.write("           " + " ".join(f"{r['sim']:>10s}" for r in chain_results) + "\n")
        f.write("RP         " + " ".join(f"{r['rp_value']:10.2f}" for r in chain_results) + "\n")
        f.write("EV         " + " ".join(f"{r['ev_value']:10.2f}" for r in chain_results) + "\n")
        f.write("############################################################\n")

    print(f"\nVSS_t table written to {vss_t_path}")
    print(f"VSS summary written to {summary_path}")


def main():
    """Runs compute_static_chain for every sim in cfg.SIMS (parallel, mirrors
    run_vssd.py's mp.Pool loop), then writes the cross-day summary."""
    with mp.Pool(processes=mp.cpu_count()) as pool:
        chain_results = pool.map(compute_static_chain, cfg.SIMS)
    _write_summary(chain_results)
    return chain_results


if __name__ == "__main__":
    if len(sys.argv) > 1:
        compute_static_chain(sys.argv[1])
    else:
        main()
