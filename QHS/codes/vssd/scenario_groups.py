"""
Scenario-group construction for the dynamic value of the stochastic solution (VSSD).

Reference: Escudero, L.F., Garin, A., Merino, M., Perez, G. (2007). "The value of
the stochastic solution in multistage problems." TOP 15, 48-64. Section 4.

This module builds G_t (Definition 4) for the 6 market-clearing macro-stages of the
QHS (15min_different_ren) EC model (DA, RM, IM1, IM2, IM3, IB) directly from an
already-solved RP instance's own scenario clustering (c, SSG) and scenario
probabilities (Prob) -- no separate tree object is built. Ported from the HG
(15min_ren_same) branch's codes/vssd/scenario_groups.py: the macro-stage -> sg
mapping and grouping algorithm are unchanged, since QHS's nSG/sgim/SSG/c
machinery (model_builder.py::add_fundamentals) is structurally identical to
HG's -- QHS just instantiates it at a finer temporal granularity (nSG=102, one
fine stage per quarter-hour for the wind/PV RVs, vs. HG's nSG=30, one per hour).

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
    index whose cluster c[sg, .] should be used as that stage's *information set*
    for Definition 4's grouping -- i.e. what's actually known when that stage's
    decision is committed, not necessarily whatever index the model's own NAC
    happens to use.

    t=1 (DA), t=2 (RM): sg=0   -- the true tree root (c[0,1] = every preserved
                                   scenario, undifferentiated). model_builder.py's
                                   own _build_stage1_nac_index NAC's eDA_p/eDA_m/
                                   rU/rD at c[1,.] instead (confirmed via
                                   preprocessing.py::allocate_market_prices():
                                   sg=1's random variables ARE lD, the realized
                                   DA price itself) -- but c[1,.] cannot be the
                                   right information set for a decision that is
                                   submitted *into* that same DA auction: the bid
                                   (or bid-curve breakpoints) is chosen before the
                                   price is known, not conditioned on its outcome.
                                   Using sg=0 here makes G_1 (and G_2, since RM is
                                   submitted alongside DA, same real-world timing)
                                   a single group spanning every scenario --
                                   consequently Z_EV^{g in G_1} degenerates to
                                   exactly the classical EV problem (Definition 1),
                                   so EDEV_1 == EV and EDEV_2 == EDEV_1 hold by
                                   construction, not by coincidence.
    t=3,4,5 (IM1,IM2,IM3): sg = sgim[i]-1, i = t-2
                                   (model_builder.py's IM-NAC branch always uses
                                   sgim[i]-1 for a market="DA"-built instance) --
                                   one stage *before* that IM's own price is
                                   revealed, the same "not yet known" logic as
                                   sg=0 above, just applied at IM's own later point
                                   in the tree instead of at the true root.
    t=6 (IB):  sg=nSG           -- the last stage (nSG=102 for QHS, vs. 30 for HG);
                                   preprocessing.py::allocate_market_prices()
                                   confirms lPIB/lNIB occupy the nSG-th stage's
                                   random variable block, i.e. IB is settled at the
                                   final stage.
    """
    if t == 1:
        return 0
    if t == 2:
        return 0
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
