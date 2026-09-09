"""
Scenario-group construction for the dynamic value of the stochastic solution (VSSD).

Reference: Escudero, L.F., Garin, A., Merino, M., Perez, G. (2007). "The value of
the stochastic solution in multistage problems." TOP 15, 48-64. Section 4.

This module builds G_t (Definition 4) for the 6 market-clearing macro-stages of the
EC model (DA, RM, IM1, IM2, IM3, IB) directly from an already-solved RP instance's
own scenario clustering (c, SSG) and scenario probabilities (Prob) -- no separate
tree object is built. See VSSD_implementation_report.md, sections 3.1-3.3, for the rationale behind
this stage mapping (why the ~29 intermediate hourly recourse stages do not need
their own groups, why G_1 is not a trivial single root group here, and why G_2
coincides with G_1).

Nothing in this module modifies the RP model files (model_builder.py,
instancemanager.py, preprocessing.py, config_definition.py).
"""
from dataclasses import dataclass
from pyomo.environ import value

# The 6 macro-stages, in order. Index t=1..6 below always refers to this ordering.
MACRO_STAGES = ["DA", "RM", "IM1", "IM2", "IM3", "IB"]


@dataclass(frozen=True)
class ScenarioGroup:
    """One node g of the scenario tree at macro-stage t (Escudero et al., Def. 4)."""
    stage: int              # macro-stage t (1..6)
    sg: int                 # underlying fine SG index used for this macro-stage's NAC
    group_id: int            # representative scenario id: the key into c[sg, group_id]
    omega: tuple             # Omega_g: preserved scenarios sharing this cluster
    weight: float             # w^g = sum_{s in Omega_g} Prob[s] (computed directly from
                              # Prob -- instance.probc is never populated by
                              # instancemanager.py's compute_representative_scenarios(),
                              # so it cannot be relied on here)
    parent_id: object        # pi(g): group_id of the ancestor cluster at stage t-1
                              # (None for t=1, which has no ancestor)


def macro_stage_sg(instance, t):
    """
    Maps macro-stage t=1..6 (DA, RM, IM1, IM2, IM3, IB) onto the fine-grained SG
    index whose cluster c[sg, .] the model's own nonanticipativity constraints use
    to enforce that stage's headline decision.

    t=1 (DA):  sg=1            -- eDA_p/eDA_m/ieDA_p/ieDA_m NAC'd at c[1,.]
                                   (model_builder.py::_build_stage1_nac_index, stage=1)
    t=2 (RM):  sg=1            -- rU/rD are NAC'd at the SAME c[1,.] as DA in the
                                   market="DA" configuration (RM bids are submitted
                                   alongside DA bids, before DA clears -- confirmed
                                   intentional, not a coarsening bug). Consequence:
                                   G_2 == G_1 as a partition, so EDEV_2 == EDEV_1
                                   exactly (see report §3.3).
    t=3,4,5 (IM1,IM2,IM3): sg = sgim[i]-1, i = t-2
                                   (model_builder.py::_add_im_nac, market_no=-1 branch,
                                   always uses sgim[i]-1 for every i when market="DA")
    t=6 (IB):  sg=nSG           -- the last stage; preprocessing.py::allocate_market_prices
                                   confirms lPIB/lNIB occupy the nSG-th stage's random
                                   variable block, i.e. IB is settled at the final stage.
    """
    if t == 1:
        return 1
    if t == 2:
        return 1
    if t in (3, 4, 5):
        i = t - 2
        return int(value(instance.sgim[i])) - 1
    if t == 6:
        return int(value(instance.nSG))
    raise ValueError(f"Unknown macro stage {t!r}; expected 1..6.")


def build_macro_stage_groups(instance):
    """
    Definition 4 / Section 4 Steps 1-4 (Escudero et al. 2007): builds G_t for
    t=1..6 from the RP instance's own scenario clustering (c[sg,s], SSG[sg]),
    already computed by InstanceManager.compute_representative_scenarios(), with
    each group's weight w^g computed directly from Prob[s] here rather than read
    from instance.probc (that Param is declared in model_builder.py but never
    populated -- compute_representative_scenarios() builds an equivalent
    probc_dict and discards it instead of storing it on the instance, so
    instance.probc stays at its default=0.0 / can raise KeyError for
    representatives outside instance.S).

    Returns {t: [ScenarioGroup, ...]} for t=1..6.
    """
    groups_by_stage = {}
    prev_membership = None  # dict: scenario -> group_id at the previous macro-stage

    for t in range(1, 7):
        sg = macro_stage_sg(instance, t)
        representatives = sorted(int(r) for r in instance.SSG[sg])

        stage_groups = []
        membership = {}
        for r in representatives:
            omega = tuple(sorted(s for s in instance.c[sg, r] if s in instance.S))
            if not omega:
                continue
            w = sum(float(value(instance.Prob[s])) for s in omega)

            parent_id = None
            if prev_membership is not None:
                parents = {prev_membership.get(s) for s in omega}
                parents.discard(None)
                if len(parents) > 1:
                    raise RuntimeError(
                        f"Scenario group (t={t}, sg={sg}, g={r}) spans more than one "
                        f"stage-{t - 1} cluster: {parents}. The scenario tree's own "
                        f"clustering data (c[sg,.]) is not properly nested across "
                        f"stages -- check the scenario .dat file."
                    )
                parent_id = parents.pop() if parents else None

            stage_groups.append(
                ScenarioGroup(stage=t, sg=sg, group_id=r, omega=omega, weight=w, parent_id=parent_id)
            )
            for s in omega:
                membership[s] = r

        groups_by_stage[t] = stage_groups
        prev_membership = membership

    return groups_by_stage
