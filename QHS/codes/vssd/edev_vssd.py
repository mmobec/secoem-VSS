"""
EDEV_t, VSSD and VSSD_t computation.

Reference: Escudero, L.F., Garin, A., Merino, M., Perez, G. (2007). "The value of
the stochastic solution in multistage problems." TOP 15, 48-64.

Ported unchanged from the HG (15min_ren_same) branch: this module is pure
arithmetic over ScenarioGroup/weight dicts and has no dependency on the model's
time-indexing convention (QHS's flat T vs. HG's (T,Q) pair), so nothing here
differs between the two branches.
"""


def compute_edev_t(groups, z_ev_by_group):
    """
    Definition 4: EDEV_t = sum_{g in G_t} w^g * Z_EV^g.

    `groups` is the list of ScenarioGroup for macro-stage t (scenario_groups.py).
    `z_ev_by_group` maps group_id -> Z_EV^g for every group that solved to
    optimality; a group missing from this dict is one whose EV_g subproblem
    was infeasible (see ev_subproblem.solve_ev_instance) -- Proposition 5's own
    proof treats this as a legitimate outcome ("if EDEV_T has no feasible
    solution... the result is trivial"), not an error condition.

    Policy: infeasible groups are excluded and the remaining groups' weights
    are renormalized to sum to 1, rather than propagating -inf or silently
    under-weighting EDEV_t. Returns (EDEV_t, excluded_weight) so the caller
    can report how much probability mass was infeasible at this stage.
    Raises if every group at this stage is infeasible (EDEV_t is then
    genuinely undefined, matching Prop. 5's "trivial" case).
    """
    solved = [g for g in groups if g.group_id in z_ev_by_group]
    excluded_weight = sum(g.weight for g in groups if g.group_id not in z_ev_by_group)
    total_weight = sum(g.weight for g in solved)
    if total_weight <= 0:
        raise RuntimeError(
            "compute_edev_t: every group at this stage is infeasible; "
            "EDEV_t is undefined (Proposition 5's 'trivial' case)."
        )
    edev_t = sum((g.weight / total_weight) * z_ev_by_group[g.group_id] for g in solved)
    return edev_t, excluded_weight


def compute_vssd(rp_value, edev_by_stage):
    """Definition 5: VSSD = RP - EDEV_T (T = last macro-stage, here t=6, IB)."""
    T = max(edev_by_stage)
    return rp_value - edev_by_stage[T]


def compute_vssd_t(rp_value, edev_by_stage):
    """
    Definition 6: VSSD_t = RP - EDEV_t.

    Reported for the full t=1..6 range rather than the paper's narrower
    t=S,...,T: that restriction appeared tied to specifics of the paper's
    illustrative tree, and the fuller sequence mirrors how the static VSS_t is
    reported (all t) in the same paper. See VSSD_implementation_report.md §3.6
    (HG branch) for the full rationale, which applies unchanged here.
    """
    return {t: rp_value - edev for t, edev in edev_by_stage.items()}
