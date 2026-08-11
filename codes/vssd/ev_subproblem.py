"""
EV_g subproblem construction and solving for VSSD.

Reference: Escudero, L.F., Garin, A., Merino, M., Perez, G. (2007). "The value of
the stochastic solution in multistage problems." TOP 15, 48-64. Section 4, Steps 1-4.

Each EV_g is built as a genuinely deterministic, single-scenario ("average
scenario") instance of the EC model: S={1}, Prob[1]=1, with every stochastic
parameter set to its Omega_g-conditional expectation, and every variable decided
at an earlier macro-stage fixed to the ancestor's solved value (Section 4 Step 2:
"the random parameters of subsequent stages are estimated by their expected
values, and all the variables of the previous stages are fixed at the optimal
solution values obtained in the chain"). See VSSD_implementation_report.md §3.4-3.5
for why this design was chosen and how PIB_p/PIB_m are handled.

The model shape is always built with sim_ctx.market == "DA" (per the user's
decision -- see report §2.1/2.5): this file never imports or modifies
model_builder.py, instancemanager.py, preprocessing.py, or config_definition.py;
it only reuses them as-is.
"""
import copy

from pyomo.environ import DataPortal, SolverFactory, Var, value

import config_definition as cfg

# Stochastic parameters loaded straight into scenario_data (before instance
# creation) as plain {(t,q,s): value} / {(i,t,q,s): value} dicts by
# preprocessing.py::allocate_market_prices -- their Omega_g-conditional
# expectation can be computed directly from that raw data.
_RAW_PARAMS_TQ = ("lD", "lR", "lPIB", "lNIB")
_RAW_PARAMS_ITQ = ("lI",)

# Parameters that only exist on the solved/instantiated RP instance (computed by
# InstanceManager after create_instance, not present in the raw scenario_data
# dict): their Omega_g-conditional expectation is read from rp_instance directly.
# PIB_p/PIB_m are included here (not recomputed as "deviation from the mean" on
# the synthetic singleton, which would trivially force them to 0 -- see report §3.5).
_INSTANCE_PARAMS_TQ = ("pW", "pPV", "PIB_p", "PIB_m")


def _cond_expectation_raw(raw_dict, prob, prefixes, omega_g, weight_g):
    """E[raw_dict(prefix, .) | Omega_g], reading straight from the pre-instance dict."""
    return {
        prefix: sum(prob[s] * raw_dict.get(prefix + (s,), 0.0) for s in omega_g) / weight_g
        for prefix in prefixes
    }


def _cond_expectation_instance(param, prob, prefixes, omega_g, weight_g):
    """E[param(prefix, .) | Omega_g], reading from a solved/assigned Pyomo Param."""
    return {
        prefix: sum(prob[s] * value(param[prefix + (s,)]) for s in omega_g) / weight_g
        for prefix in prefixes
    }


def build_ev_instance(abstract_model, rp_instance, rp_scenario_data, group):
    """
    Builds the deterministic single-scenario instance for scenario group `group`
    (Definition 4 / Section 4 Step 2 & 4). Does not fix anything yet -- call
    apply_fixed_values() afterwards for t>1.
    """
    raw = rp_scenario_data.data()
    prob = {s: value(rp_instance.Prob[s]) for s in rp_instance.S}
    omega_g, w_g = group.omega, group.weight

    nT = int(value(rp_instance.nT))
    nQ = int(value(rp_instance.nQ))
    nIM = int(value(rp_instance.nIM))

    tq_keys = [(t, q) for t in range(1, nT + 1) for q in range(1, nQ + 1)]
    itq_keys = [
        (i, t, q)
        for i in range(1, nIM + 1)
        for t in rp_instance.TIM[i]
        for q in range(1, nQ + 1)
    ]

    portal = DataPortal()
    for key, val in raw.items():
        portal[key] = copy.deepcopy(val)

    # A single deterministic scenario, probability 1. nS is deliberately left as-is
    # (not overridden to 1): it only sizes S0 = RangeSet(1, nS), the *complete*
    # scenario range that Prob0/Scen0/c's raw (copied, untouched) data is indexed
    # over -- shrinking it here would invalidate those entries. S (within S0) is
    # the actual preserved-scenario subset, so collapsing it to {1} is sufficient.
    portal["S"] = {None: [1]}
    portal["Prob"] = {1: 1.0}
    # Scen is indexed over nRV x S (not S0), so it doesn't survive S collapsing to
    # {1} the way Prob0/Scen0/c do -- its raw (copied) entries span the RP's whole
    # preserved S and would fail the same "index not valid" way Prob0 did before nS
    # was left alone. It's dead weight here regardless: preprocessing.py only ever
    # used Scen to derive lD/lR/lI/lPIB/lNIB, and this function recomputes all five
    # directly from Omega_g-conditional expectations, so nothing in vssd/ ever reads
    # instance.Scen. default=0.0 on the Param makes an empty dict valid.
    portal["Scen"] = {}

    for pname in _RAW_PARAMS_TQ:
        cond = _cond_expectation_raw(raw[pname], prob, tq_keys, omega_g, w_g)
        portal[pname] = {key + (1,): val for key, val in cond.items()}

    for pname in _RAW_PARAMS_ITQ:
        cond = _cond_expectation_raw(raw[pname], prob, itq_keys, omega_g, w_g)
        portal[pname] = {key + (1,): val for key, val in cond.items()}

    for pname in _INSTANCE_PARAMS_TQ:
        param = getattr(rp_instance, pname)
        cond = _cond_expectation_instance(param, prob, tq_keys, omega_g, w_g)
        portal[pname] = {key + (1,): val for key, val in cond.items()}

    # A single scenario has nothing to be nonanticipative with: every NAC index
    # set built from consecutive_scenarios() becomes empty automatically.
    portal["c"] = {(sg, 1): [1] for sg in rp_instance.SG0}

    instance = abstract_model.create_instance(portal)

    # Deterministic/physical parameters that do not depend on which scenario
    # realises: inherited directly from RP rather than recomputed on the
    # synthetic singleton (e.g. max_pW/max_pPV are nameplate-capacity bid bounds,
    # not forecasts).
    instance.SOCini = value(rp_instance.SOCini)
    instance.max_pW = value(rp_instance.max_pW)
    instance.max_pPV = value(rp_instance.max_pPV)

    return instance


def newly_decided_at_stage(t, rp_instance):
    """
    Variables that become fixed for stage t's children once EV_g at stage t is
    solved (Section 4 Step 2). Mirrors the x_t / elapsed-recourse mapping in
    VSSD_implementation_report.md §3.1: intraday-market bids become fixed at
    their own macro-stage, and IM3 (t=5) additionally fixes all hourly
    battery/flexible-demand/imbalance recourse for hours before IM3's own
    delivery window (TIM[3]) -- those hours have "elapsed" by the time IM3
    clears and are no longer free recourse for the IB stage.
    """
    T, Q = list(rp_instance.T), list(rp_instance.Q)
    all_tq = [(t_, q_) for t_ in T for q_ in Q]

    if t == 1:
        return [(v, all_tq) for v in ("eDA_p", "eDA_m", "ieDA_p", "ieDA_m")]

    if t == 2:
        return [(v, all_tq) for v in ("rU", "rD")]

    if t in (3, 4, 5):
        i = t - 2
        im_idx = [(i, t_, q_) for t_ in rp_instance.TIM[i] for q_ in Q]
        result = [("eIM", im_idx)]
        if t == 5:
            cutoff = min(rp_instance.TIM[3])
            elapsed_tq = [(t_, q_) for t_ in T if t_ < cutoff for q_ in Q]
            for v in (
                "var_fd", "var_afd_p", "var_afd_m", "dV", "cV", "idV",
                "rU_B", "rD_B", "rU_FD", "rD_FD", "pIB_p", "pIB_m",
            ):
                result.append((v, elapsed_tq))
            soc_idx = elapsed_tq + [(0, max(Q))]
            result.append(("socV", soc_idx))
        return result

    if t == 6:
        return []

    raise ValueError(f"Unknown macro stage {t!r}; expected 1..6.")


def apply_fixed_values(instance, ancestor_snapshot, fixed_specs):
    """Section 4 Step 2: fix decisions of stages 1..t-1 at the ancestor's solved values."""
    for var_name, idx_list in fixed_specs:
        var_obj = getattr(instance, var_name)
        for idx in idx_list:
            full_idx = idx + (1,)  # single scenario, s=1
            val = ancestor_snapshot[var_name][full_idx]
            var_obj[full_idx].set_value(val)
            var_obj[full_idx].fix()


def snapshot_solution(instance):
    """
    Records every Var's solved (or fixed) value, so this group's children can
    inherit whatever was decided by this point in the chain (Section 4 Step 2).

    Some Var indices (e.g. socV at T0=0 for quarters other than the one the
    SOCV_ini constraint actually pins) are structurally never referenced by any
    constraint or the objective, so Gurobi never assigns them a value -- skip
    those rather than let value() raise. Safe to skip: apply_fixed_values() only
    ever looks up the specific (var, idx) pairs newly_decided_at_stage() lists,
    never a full variable, so a skipped index is simply never requested.
    """
    result = {}
    for v in instance.component_objects(Var, active=True):
        vals = {}
        for idx in v:
            val = value(v[idx], exception=False)
            if val is not None:
                vals[idx] = val
        result[v.name] = vals
    return result


def solve_ev_instance(instance, label=""):
    """Solves one EV_g subproblem with the same Gurobi options as the RP model."""
    solver = SolverFactory("gurobi")
    for k, v in cfg.SOLVER_OPTIONS.items():
        solver.options[k] = v
    results = solver.solve(instance, tee=False)
    status = results.solver.termination_condition
    obj = value(instance.EECSW)
    print(f"    [{label}] status={status}  Z_EV_g={obj:.4f}")
    return obj, status
