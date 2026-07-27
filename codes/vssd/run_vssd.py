"""
VSSD orchestrator (Escudero, Garin, Merino & Perez 2007, Section 4).

Computes RP, the EV_g chain, EDEV_t, VSSD and VSSD_t for the EC model's 6
market-clearing macro-stages (DA, RM, IM1, IM2, IM3, IB), and validates
Propositions 4-7. See VSSD_implementation_report.md for the full methodology
and every adaptation decision.

This script is fully decoupled from the normal pipeline: it imports
config_definition / simulation_context / preprocessing / instancemanager /
solver exactly as modular_ec_run.py does, but is never called from it, and
never modifies any of those files. Running `python modular_ec_run.py` is
completely unaffected by this script's existence.

Usage (from the codes/ directory, or anywhere -- this script fixes up sys.path):
    python vssd/run_vssd.py [sim]
"""
import os
import sys

_CODES_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CODES_DIR not in sys.path:
    sys.path.insert(0, _CODES_DIR)

import csv

from pyomo.environ import value

import config_definition as cfg
from simulation_context import SimulationContext
from preprocessing import PreProcessor
from instancemanager import InstanceManager
from solver import Solver

from vssd.scenario_groups import build_macro_stage_groups, MACRO_STAGES
from vssd.ev_subproblem import (
    build_ev_instance,
    apply_fixed_values,
    snapshot_solution,
    newly_decided_at_stage,
    solve_ev_instance,
)
from vssd.edev_vssd import compute_edev_t, compute_vssd, compute_vssd_t
from vssd.validation import validate_propositions, print_report


def solve_rp(sim):
    """RP = one solve of the market="DA" model (see report §2.1): every variable
    across all 6 macro-stages is free, only DA-cluster nonanticipativity is
    imposed -- this is model (3) in Escudero et al. (2007)."""
    sim_ctx = SimulationContext(sim=sim, market="DA")
    scenario_data, abstract_model = PreProcessor(sim_ctx).run_preprocessing()
    instance_wrapper = InstanceManager(scenario_data, sim_ctx, abstract_model)
    instance_wrapper.compute_instance()
    Solver(instance_wrapper, sim_ctx).solve()
    return instance_wrapper.instance, scenario_data, abstract_model, sim_ctx


def compute_vssd_chain(sim):
    print(f"=== VSSD (Escudero et al. 2007, Section 4) -- sim {sim} ===")

    print("\n-- Solving RP (market='DA') --")
    rp_instance, rp_scenario_data, abstract_model, sim_ctx = solve_rp(sim)
    rp_value = value(rp_instance.EECSW)
    print(f"RP = {rp_value:.4f}")

    print("\n-- Building scenario groups G_t (Definition 4) --")
    groups_by_stage = build_macro_stage_groups(rp_instance)
    for t in range(1, 7):
        print(f"  G_{t} ({MACRO_STAGES[t - 1]}): {len(groups_by_stage[t])} group(s)")

    solution_cache = {}   # (t, group_id) -> snapshot dict
    z_ev_by_stage = {}    # t -> {group_id: Z_EV^g}
    edev_by_stage = {}    # t -> EDEV_t

    for t in range(1, 7):
        print(f"\n-- Stage t={t} ({MACRO_STAGES[t - 1]}) --")
        groups = groups_by_stage[t]

        fixed_specs = []
        for tau in range(1, t):
            fixed_specs += newly_decided_at_stage(tau, rp_instance)

        z_by_group = {}
        for g in groups:
            instance = build_ev_instance(abstract_model, rp_instance, rp_scenario_data, g)

            if t > 1:
                ancestor_snapshot = solution_cache[(t - 1, g.parent_id)]
                apply_fixed_values(instance, ancestor_snapshot, fixed_specs)

            label = f"t={t} g={g.group_id} |Omega_g|={len(g.omega)} w={g.weight:.4f}"
            z_g, status = solve_ev_instance(instance, label=label)

            z_by_group[g.group_id] = z_g
            solution_cache[(t, g.group_id)] = snapshot_solution(instance)

        z_ev_by_stage[t] = z_by_group
        edev_t = compute_edev_t(groups, z_by_group)
        edev_by_stage[t] = edev_t
        print(f"EDEV_{t} = {edev_t:.4f}")

    vssd = compute_vssd(rp_value, edev_by_stage)
    vssd_by_stage = compute_vssd_t(rp_value, edev_by_stage)

    print(f"\nVSSD = RP - EDEV_6 = {rp_value:.4f} - {edev_by_stage[6]:.4f} = {vssd:.4f}")
    for t in range(1, 7):
        print(f"VSSD_{t} = {vssd_by_stage[t]:.4f}")

    report = validate_propositions(rp_value, edev_by_stage, vssd_by_stage)
    print_report(report)

    _write_results_csv(sim_ctx, rp_value, edev_by_stage, vssd, vssd_by_stage)

    return {
        "rp_value": rp_value,
        "edev_by_stage": edev_by_stage,
        "vssd": vssd,
        "vssd_by_stage": vssd_by_stage,
        "validation": report,
    }


def _write_results_csv(sim_ctx, rp_value, edev_by_stage, vssd, vssd_by_stage):
    out_path = os.path.join(cfg.PROJECT_ROOT, sim_ctx.pathres, "edev_vssd_results.csv")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["stage_t", "market", "EDEV_t", "VSSD_t"])
        for t in range(1, 7):
            writer.writerow([t, MACRO_STAGES[t - 1], edev_by_stage[t], vssd_by_stage[t]])
        writer.writerow([])
        writer.writerow(["RP", rp_value])
        writer.writerow(["VSSD", vssd])
    print(f"\nResults written to {out_path}")


if __name__ == "__main__":
    sim_arg = sys.argv[1] if len(sys.argv) > 1 else cfg.SIMS[0]
    compute_vssd_chain(sim_arg)
