"""
VSSD orchestrator (Escudero, Garin, Merino & Perez 2007, Section 4).

Computes RP, the EV_g chain, EDEV_t, VSSD and VSSD_t for the EC model's 6
market-clearing macro-stages (DA, RM, IM1, IM2, IM3, IB), and validates
Propositions 4-7. Ported from the HG (15min_ren_same) branch's
codes/vssd/run_vssd.py -- same orchestration, same macro-stage loop; the only
adaptation is the time-indexing convention (see ev_subproblem.py's module
docstring).

This script is fully decoupled from the normal pipeline: it imports
config_definition / simulation_context / preprocessing / instancemanager /
solver exactly as modular_ec_run.py does, but is never called from it, and
never modifies any of those files. Running `python modular_ec_run.py` is
completely unaffected by this script's existence.

Usage (from the codes/ directory, or anywhere -- this script fixes up sys.path):
    python vssd/run_vssd.py        # runs every sim in cfg.SIMS (parallel), writes
                                    # the cross-day summary (tables/vssd_t.txt,
                                    # vssd_<famscen>_summary.out) alongside each
                                    # day's own edev_vssd_results.csv
    python vssd/run_vssd.py <sim>  # runs a single sim only (e.g. "001"), no
                                    # cross-day summary
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
from simulation_context import SimulationContext
from preprocessing import PreProcessor
from instancemanager import InstanceManager
from solver import Solver

from vssd.scenario_groups import build_macro_stage_groups, MACRO_STAGES
from vssd.ev_subproblem import (
    build_ev_instance,
    build_full_instance,
    apply_fixed_values,
    relax_im_bounds_for_fixed_da,
    relax_ib_bounds_for_fixed_da,
    snapshot_solution,
    newly_decided_at_stage,
    solve_ev_instance,
)
from vssd.edev_vssd import compute_edev_t, compute_vssd, compute_vssd_t
from vssd.validation import validate_propositions, print_report


def solve_rp(sim):
    """RP = one solve of the market="DA" model: every variable across all 6
    macro-stages is free, only DA-cluster nonanticipativity is imposed -- this
    is model (3) in Escudero et al. (2007). Confirmed valid for QHS the same
    way it is for HG: model_builder.py, built with market=="DA", keeps rU/rD
    and eIM as free Vars (not Params) and includes the full NAC structure
    across all 6 macro-stages, so this single solve already is the paper's RP
    -- no multi-market sequential chain execution needed (and QHS's own
    RM/IM1/IM2/IM3/EMS chain is not currently runnable end-to-end regardless,
    since it depends on a config.base_result_dir attribute that is not
    defined in this branch's config_definition.py)."""
    sim_ctx = SimulationContext(sim=sim, market="DA")
    scenario_data, abstract_model = PreProcessor(sim_ctx).run_preprocessing()
    instance_wrapper = InstanceManager(scenario_data, sim_ctx, abstract_model)
    instance_wrapper.compute_instance()
    Solver(instance_wrapper, sim_ctx).solve()
    return instance_wrapper.instance, scenario_data, abstract_model, sim_ctx


def compute_edev2_recourse(sim_ctx, rp_instance, rp_scenario_data, abstract_model,
                            groups_by_stage, solution_cache):
    """
    Supplementary dynamic-family comparator -- not part of Escudero's own
    Definition 4 chain. For each of G_1's groups, fixes eDA at that group's
    own EV_1 solved value (identical for every real member scenario, so
    DA_bid_mono is trivially satisfied within the group -- it only ever
    compares members against each other, and cross-group pairs never coexist
    in the same instance), then solves RM through IB with genuine,
    non-averaged recourse for that group's real member scenarios jointly
    (instead of the dynamic chain's further group-averaging).

    Tighter than EDEV_2 (which keeps averaging RM..IB too as well), but --
    unlike the static EEV_2 (run_static_vss.py) -- does NOT carry
    Proposition 1's <= RP guarantee: it silently accepts that the G_1 groups'
    independently-solved DA values are not jointly consistent with each other
    (each EV_1 subproblem is a single-scenario deterministic solve, blind to
    every other group) rather than fixing that inconsistency at the source, as
    the static chain's classical single-EV fixing does.

    Infeasible groups are excluded and the remaining groups' weights are
    renormalized, mirroring compute_edev_t()'s own group-level exclusion
    policy (Proposition 5's "trivial" case) -- not the static chain's finer
    grained, IIS-based per-scenario exclusion (Definition 3).
    """
    print("\n-- Computing EDEV_2_recourse (fix DA-stage per-group at EV_1's own "
          "value, solve RM..IB with real per-scenario recourse within each group) --")

    fixed_specs_1 = newly_decided_at_stage(1, rp_instance)
    z_sum = 0.0
    excluded_weight = 0.0

    for g in groups_by_stage[1]:
        snap = solution_cache[(1, g.group_id)]
        instance = build_full_instance(
            sim_ctx, abstract_model, rp_scenario_data, rp_instance, set(g.omega), renormalize=False
        )
        for var_name, idx_list in fixed_specs_1:
            var_obj = getattr(instance, var_name)
            for idx in idx_list:
                val = snap[var_name][idx + (1,)]
                for s in g.omega:
                    var_obj[idx + (s,)].set_value(val)
                    var_obj[idx + (s,)].fix()

        relax_im_bounds_for_fixed_da(instance)
        relax_ib_bounds_for_fixed_da(instance)

        label = f"EDEV_2_recourse g={g.group_id} |Omega_g|={len(g.omega)} w={g.weight:.4f}"
        z_g, status = solve_ev_instance(instance, label=label)
        if z_g is None:
            excluded_weight += g.weight
            continue
        z_sum += z_g

    survived_weight = 1.0 - excluded_weight
    if survived_weight <= 0:
        raise RuntimeError(
            "compute_edev2_recourse: every group is infeasible; EDEV_2_recourse is undefined."
        )
    edev2_recourse = z_sum / survived_weight
    print(f"EDEV_2_recourse = {edev2_recourse:.4f}"
          + (f"  (excluded {excluded_weight:.4f} infeasible probability mass, renormalized)"
             if excluded_weight > 0 else ""))
    return edev2_recourse, excluded_weight


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

    solution_cache = {}      # (t, group_id) -> snapshot dict
    z_ev_by_stage = {}       # t -> {group_id: Z_EV^g}
    edev_by_stage = {}       # t -> EDEV_t
    excluded_weight_by_stage = {}  # t -> probability mass excluded as infeasible
    infeasible_ids = set()   # group_ids infeasible (or descended from infeasible) at t-1

    for t in range(1, 7):
        print(f"\n-- Stage t={t} ({MACRO_STAGES[t - 1]}) --")
        groups = groups_by_stage[t]

        fixed_specs = []
        for tau in range(1, t):
            fixed_specs += newly_decided_at_stage(tau, rp_instance)

        z_by_group = {}
        next_infeasible_ids = set()
        for g in groups:
            # Proposition 5 anticipates infeasible EV_g as a legitimate outcome
            # (see edev_vssd.compute_edev_t); a group whose ancestor was
            # infeasible has no fixed-value chain to inherit and must be
            # skipped too, cascading down the tree.
            if t > 1 and g.parent_id in infeasible_ids:
                print(f"    [t={t} g={g.group_id}] SKIPPED: ancestor (t={t - 1}, "
                      f"g={g.parent_id}) was infeasible")
                next_infeasible_ids.add(g.group_id)
                continue

            instance = build_ev_instance(abstract_model, rp_instance, rp_scenario_data, g)

            if t > 1:
                ancestor_snapshot = solution_cache[(t - 1, g.parent_id)]
                apply_fixed_values(instance, ancestor_snapshot, fixed_specs)

            if t >= 3:
                # IM1/IM2/IM3/IB: eDA is now fixed (from t=1) and may be ~0 at
                # some t -- reproduce the real pipeline's FD_U fallback instead
                # of the "DA"-branch cap collapsing to 0 (see
                # ev_subproblem.relax_im_bounds_for_fixed_da's docstring).
                relax_im_bounds_for_fixed_da(instance)
                # Same structural bug, different constraint pair: PIB_p/PIB_m
                # are precomputed data (routinely 0 for ~half of scenario/
                # quarter-hour pairs), and the "DA"-branch IB_pos_UB/IB_neg_UB
                # has no slack fallback either. Reproduce the RM/IM branch's
                # slack-relaxed formula, priced to avoid manufacturing free
                # pIB_p revenue (see ev_subproblem.relax_ib_bounds_for_fixed_da's
                # docstring).
                relax_ib_bounds_for_fixed_da(instance)

            label = f"t={t} g={g.group_id} |Omega_g|={len(g.omega)} w={g.weight:.4f}"
            z_g, status = solve_ev_instance(instance, label=label)

            if z_g is None:
                next_infeasible_ids.add(g.group_id)
                continue

            z_by_group[g.group_id] = z_g
            solution_cache[(t, g.group_id)] = snapshot_solution(instance)

        infeasible_ids = next_infeasible_ids
        z_ev_by_stage[t] = z_by_group
        edev_t, excluded_weight = compute_edev_t(groups, z_by_group)
        edev_by_stage[t] = edev_t
        excluded_weight_by_stage[t] = excluded_weight
        print(f"EDEV_{t} = {edev_t:.4f}"
              + (f"  (excluded {excluded_weight:.4f} infeasible probability mass, renormalized)"
                 if excluded_weight > 0 else ""))

    vssd = compute_vssd(rp_value, edev_by_stage)
    vssd_by_stage = compute_vssd_t(rp_value, edev_by_stage)

    print(f"\nVSSD = RP - EDEV_6 = {rp_value:.4f} - {edev_by_stage[6]:.4f} = {vssd:.4f}")
    for t in range(1, 7):
        print(f"VSSD_{t} = {vssd_by_stage[t]:.4f}")

    report = validate_propositions(rp_value, edev_by_stage, vssd_by_stage)
    print_report(report)

    edev2_recourse, edev2_recourse_excluded_weight = compute_edev2_recourse(
        sim_ctx, rp_instance, rp_scenario_data, abstract_model, groups_by_stage, solution_cache
    )
    vssd2_recourse = rp_value - edev2_recourse
    print(f"VSSD_2_recourse = RP - EDEV_2_recourse = {rp_value:.4f} - {edev2_recourse:.4f} "
          f"= {vssd2_recourse:.4f}")

    _write_results_csv(sim_ctx, rp_value, edev_by_stage, vssd, vssd_by_stage, excluded_weight_by_stage,
                        edev2_recourse, vssd2_recourse, edev2_recourse_excluded_weight)

    return {
        "sim": sim,
        "rp_value": rp_value,
        "edev_by_stage": edev_by_stage,
        "vssd": vssd,
        "vssd_by_stage": vssd_by_stage,
        "excluded_weight_by_stage": excluded_weight_by_stage,
        "validation": report,
        "edev2_recourse": edev2_recourse,
        "vssd2_recourse": vssd2_recourse,
        "edev2_recourse_excluded_weight": edev2_recourse_excluded_weight,
    }


def _write_results_csv(sim_ctx, rp_value, edev_by_stage, vssd, vssd_by_stage, excluded_weight_by_stage,
                        edev2_recourse, vssd2_recourse, edev2_recourse_excluded_weight):
    out_path = os.path.join(cfg.PROJECT_ROOT, sim_ctx.pathres, "edev_vssd_results.csv")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["stage_t", "market", "EDEV_t", "VSSD_t", "excluded_infeasible_weight"])
        for t in range(1, 7):
            writer.writerow([t, MACRO_STAGES[t - 1], edev_by_stage[t], vssd_by_stage[t],
                              excluded_weight_by_stage[t]])
        writer.writerow([])
        writer.writerow(["RP", rp_value])
        writer.writerow(["VSSD", vssd])
        writer.writerow([])
        writer.writerow(["EDEV_2_recourse", edev2_recourse, "excluded_infeasible_weight",
                          edev2_recourse_excluded_weight])
        writer.writerow(["VSSD_2_recourse", vssd2_recourse])
    print(f"\nResults written to {out_path}")


def _write_summary(chain_results):
    """Aggregates one compute_vssd_chain() result per sim into cross-day tables,
    mirroring SimulationSummaryWriter's tables/*.txt + *_summary.out pattern for
    the main EC pipeline (results/<famscen>/DA/tables/, results/<famscen>/DA/)."""
    table_dir = os.path.join(cfg.PROJECT_ROOT, "results", cfg.famscen_all, "DA", "tables")
    os.makedirs(table_dir, exist_ok=True)

    vssd_t_path = os.path.join(table_dir, "vssd_t.txt")
    with open(vssd_t_path, "w") as f:
        f.write("stage    " + " ".join(f"{r['sim']:>7s}" for r in chain_results) + "\n")
        for t in range(1, 7):
            f.write(
                f"VSSD_{t}  "
                + " ".join(f"{r['vssd_by_stage'][t]:7.2f}" for r in chain_results)
                + "\n"
            )

    summary_path = os.path.join(
        cfg.PROJECT_ROOT, "results", cfg.famscen_all, "DA", f"vssd_{cfg.famscen_all}_summary.out"
    )
    with open(summary_path, "w") as f:
        f.write("############################################################\n")
        f.write(f"VSSD summary ({len(chain_results)} days)\n")
        f.write("           " + " ".join(f"{r['sim']:>10s}" for r in chain_results) + "\n")
        f.write("RP         " + " ".join(f"{r['rp_value']:10.2f}" for r in chain_results) + "\n")
        f.write("VSSD       " + " ".join(f"{r['vssd']:10.2f}" for r in chain_results) + "\n")
        f.write(
            "valid      "
            + " ".join(f"{'OK' if r['validation']['ok'] else 'FAIL':>10s}" for r in chain_results)
            + "\n"
        )
        f.write("############################################################\n")

    print(f"\nVSSD_t table written to {vssd_t_path}")
    print(f"VSSD summary written to {summary_path}")


def main():
    """Runs compute_vssd_chain for every sim in cfg.SIMS (parallel, mirrors
    modular_ec_run.py's mp.Pool loop), then writes the cross-day summary."""
    with mp.Pool(processes=mp.cpu_count()) as pool:
        chain_results = pool.map(compute_vssd_chain, cfg.SIMS)
    _write_summary(chain_results)
    return chain_results


if __name__ == "__main__":
    if len(sys.argv) > 1:
        compute_vssd_chain(sys.argv[1])
    else:
        main()
