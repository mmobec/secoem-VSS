"""
EDEV_t, VSSD and VSSD_t computation.

Reference: Escudero, L.F., Garin, A., Merino, M., Perez, G. (2007). "The value of
the stochastic solution in multistage problems." TOP 15, 48-64.
"""


def compute_edev_t(groups, z_ev_by_group):
    """
    Definition 4: EDEV_t = sum_{g in G_t} w^g * Z_EV^g.

    `groups` is the list of ScenarioGroup for macro-stage t (scenario_groups.py).
    `z_ev_by_group` maps group_id -> Z_EV^g (the solved EV_g objective value).
    """
    return sum(g.weight * z_ev_by_group[g.group_id] for g in groups)


def compute_vssd(rp_value, edev_by_stage):
    """Definition 5: VSSD = RP - EDEV_T (T = last macro-stage, here t=6, IB)."""
    T = max(edev_by_stage)
    return rp_value - edev_by_stage[T]


def compute_vssd_t(rp_value, edev_by_stage):
    """
    Definition 6: VSSD_t = RP - EDEV_t.

    Reported for the full t=1..6 range rather than the paper's narrower
    t=S,...,T (see VSSD_implementation_report.md §3.6): that restriction
    appeared tied to specifics of the paper's illustrative tree, and the fuller
    sequence mirrors how the static VSS_t is reported (all t) in the same paper.
    """
    return {t: rp_value - edev for t, edev in edev_by_stage.items()}
