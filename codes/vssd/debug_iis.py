"""
Standalone diagnostic: rebuild one specific EV_g chain down to a known-infeasible
group and ask Gurobi for its IIS (irreducible infeasible subsystem) directly,
instead of guessing at causes from log_infeasible_constraints() (which only
checks constraint bodies, not variable-bound violations, and was found to be
silent on HG's own diagnostic pass -- see VSSD_implementation_report.md §3.8).

Ported from the HG (15min_ren_same) branch's codes/vssd/debug_iis.py. Not part
of the vssd/ package's normal flow (run_vssd.py never imports this): a one-off
debugging tool. Usage:
    python vssd/debug_iis.py [sim] [t] [group_id]
Defaults to sim="001", t=3, group_id=1 -- adjust group_id after inspecting a
real run's "SKIPPED"/"INFEASIBLE" log lines for this branch's own scenario tree
(HG's own default of group_id=10 was specific to its 300-scenario dataset and
has no reason to be meaningful here).
"""
import os
import sys

_CODES_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CODES_DIR not in sys.path:
    sys.path.insert(0, _CODES_DIR)

from pyomo.environ import SolverFactory, value
import pyomo.environ as pyo

import config_definition as cfg
from vssd.run_vssd import solve_rp
from vssd.scenario_groups import build_macro_stage_groups
from vssd.ev_subproblem import (
    build_ev_instance,
    apply_fixed_values,
    snapshot_solution,
    newly_decided_at_stage,
    relax_im_bounds_for_fixed_da,
    relax_ib_bounds_for_fixed_da,
)


def find_group(groups, group_id):
    for g in groups:
        if g.group_id == group_id:
            return g
    raise KeyError(f"group_id={group_id} not found among {[g.group_id for g in groups]}")


def solve_and_check(instance, label):
    solver = SolverFactory("gurobi")
    for k, v in cfg.SOLVER_OPTIONS.items():
        solver.options[k] = v
    results = solver.solve(instance, tee=False)
    status = results.solver.termination_condition
    print(f"  [{label}] status={status}")
    if status != pyo.TerminationCondition.optimal:
        raise RuntimeError(f"{label} instance did not solve to optimality: {status}")
    return instance


def main():
    sim = sys.argv[1] if len(sys.argv) > 1 else "001"
    target_t = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    target_group_id = int(sys.argv[3]) if len(sys.argv) > 3 else 1

    print(f"=== IIS debug: sim={sim}, target t={target_t}, group_id={target_group_id} ===")

    print("\n-- Solving RP --")
    rp_instance, rp_scenario_data, abstract_model, sim_ctx = solve_rp(sim)
    print(f"RP = {value(rp_instance.EECSW):.4f}")

    groups_by_stage = build_macro_stage_groups(rp_instance)

    # Walk the ancestor chain from the target group back to t=1.
    chain = [find_group(groups_by_stage[target_t], target_group_id)]
    for t in range(target_t - 1, 0, -1):
        chain.append(find_group(groups_by_stage[t], chain[-1].parent_id))
    chain.reverse()  # now t=1 .. target_t

    print("Chain: " + " -> ".join(f"t={g.stage} g={g.group_id}" for g in chain))

    solution_cache = {}
    prev_snapshot = None

    for idx, g in enumerate(chain):
        t = g.stage
        is_target = (t == target_t)

        instance = build_ev_instance(abstract_model, rp_instance, rp_scenario_data, g)

        if t > 1:
            fixed_specs = []
            for tau in range(1, t):
                fixed_specs += newly_decided_at_stage(tau, rp_instance)
            apply_fixed_values(instance, prev_snapshot, fixed_specs)

        if t >= 3:
            relax_im_bounds_for_fixed_da(instance)
            relax_ib_bounds_for_fixed_da(instance)

        if not is_target:
            solve_and_check(instance, f"t={t} g={g.group_id}")
            prev_snapshot = snapshot_solution(instance)
            continue

        # Target group: solve with ResultFile pointed at a .ilp so Gurobi
        # computes and writes the IIS automatically if infeasible.
        ilp_path = os.path.join(
            cfg.PROJECT_ROOT, f"vssd_debug_t{t}_g{g.group_id}.ilp"
        )
        print(f"\n-- Solving target instance t={t} g={g.group_id} "
              f"(IIS -> {ilp_path} if infeasible) --")
        solver = SolverFactory("gurobi")
        for k, v in cfg.SOLVER_OPTIONS.items():
            solver.options[k] = v
        solver.options["ResultFile"] = ilp_path
        results = solver.solve(instance, tee=True, symbolic_solver_labels=True)
        status = results.solver.termination_condition
        print(f"\nTarget status: {status}")

        if os.path.exists(ilp_path):
            print(f"\n=== IIS ({ilp_path}) ===\n")
            print(open(ilp_path).read())
        else:
            print("\nNo .ilp written -- either the model solved (not infeasible after "
                  "all), or this solver interface didn't honor ResultFile.")
        return

    print("Target group was never reached (chain shorter than expected?).")


if __name__ == "__main__":
    main()
