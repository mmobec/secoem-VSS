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
import logging

import pyomo.environ as pyo
from pyomo.environ import DataPortal, SolverFactory, Var, value
from pyomo.util.infeasible import log_infeasible_constraints

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
            # pIB_p/pIB_m are deliberately NOT fixed here, even for elapsed
            # hours: they are the residual of the Imbalances balance equation
            # (which also involves pW/pPV), and pW/pPV are recomputed fresh
            # from each group's own Omega_g-conditional expectation at every
            # stage. If a child group's Omega_g strictly refines its parent's,
            # that expectation can shift slightly even for an "elapsed" hour,
            # and fixing pIB_p/pIB_m to the parent's now-stale balance makes
            # the equation infeasible. Leaving them free lets each subproblem
            # reconcile its own balance, which is the correct behaviour for a
            # computed residual rather than a genuinely memorized decision.
            for v in (
                "var_fd", "var_afd_p", "var_afd_m", "dV", "cV", "idV",
                "rU_B", "rD_B", "rU_FD", "rD_FD",
            ):
                result.append((v, elapsed_tq))
            # The day-boundary state of charge is only ever constrained at
            # (t=0, q=1) -- SOCV_ini_rule sets socV[T0.first(), 1, s] ==
            # SOCini; socV[0, q, s] for q=2,3,4 is declared (T0 x Q x S) but
            # never appears in any constraint, so it never gets a solved
            # value and must not be included here.
            soc_idx = elapsed_tq + [(0, min(Q))]
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


def relax_im_bounds_for_fixed_da(instance):
    """
    IM1/IM2/IM3/IB fix: reproduce model_builder.py's _cap20() "not DA" fallback
    on an EV_g instance whose eDA_p/eDA_m are already fixed (call only for t>=3,
    after apply_fixed_values()).

    IM_bounds_1_pos/2/3/4 bound eIM by cap = maxTIM * (eDA_p + eDA_m)
    (model_builder.py:749-781). That formula is a Python closure over
    self.sim_ctx.market, baked into the constraint expressions once when
    ModelBuilder builds the abstract model -- and every EV_g in this package is
    built from a single abstract model constructed under market="DA" (see this
    file's module docstring), so every instance permanently carries the "DA"
    branch of _cap20, with no fallback for a ~0 fixed DA position:
        cap = maxTIM * (eDA_p[t,q,s] + eDA_m[t,q,s])
    Once eDA is fixed to a real number (t>=2) and that number is ~0 at some
    (t,q) -- an entirely ordinary outcome, plenty of quarters clear nothing in
    DA -- cap collapses to exactly 0 regardless of maxTIM's value, forcing
    eIM[.,t,q,.] == 0 there. If the group's own Omega_g-conditional-average
    forecast needs any nonzero imbalance at that quarter, the subproblem is
    flatly infeasible: confirmed as the actual failure mode behind the t=3
    (IM1) infeasibilities hit in this package (eIM[1,1,1,1] uninitialized,
    Gurobi "Model was proven to be infeasible" -- reproduced identically at
    maxTIM=0.2 and maxTIM=1, ruling out the band width itself as the cause).

    The real sequential pipeline never hits this: once sim_ctx.market != "DA",
    _cap20()'s else branch falls back to FD_U[t,q] (flexible-demand upper
    bound, much larger) whenever the fixed DA position is ~0. That branch is
    unreachable from this package's single "DA"-shaped abstract model, so it's
    reproduced here directly on the instance instead: deactivate the four
    baked-in constraints and re-add them with the same D>EPS-else-FD_U formula,
    reading eDA_p/eDA_m as plain fixed numbers.

    Scope: only for macro-stages where eDA is genuinely already fixed and the
    "DA"-branch is not what the real pipeline would use at that stage. Not
    called for t=1 (eDA still free -- the original "DA"-branch constraint,
    with cap as a live expression, is already correct there) or t=2 (RM):
    empirically, RM's own group partition coincides with DA's (see
    scenario_groups.py), so its own conditional-average forecast is
    self-consistent with the eDA it inherits and this mismatch does not arise
    there (0% exclusion observed at t=1/t=2 in testing, vs. 62%+ from t=3
    onward) -- revisit if that changes.
    """
    EPS = 1e-9
    for name in ("IM_bounds_1_pos", "IM_bounds_2", "IM_bounds_3", "IM_bounds_4"):
        getattr(instance, name).deactivate()

    def _cap(m, t, q, s):
        D = value(m.eDA_p[t, q, s]) + value(m.eDA_m[t, q, s])
        return m.maxTIM * D if D > EPS else m.FD_U[t, q]

    def IM_bounds_1_pos_rule(m, t, q, s):
        return sum(
            m.eIM_pos[i, t, q, s] + m.eIM_neg[i, t, q, s] for i in m.IMT[t]
        ) <= _cap(m, t, q, s)
    instance.IM_bounds_1_pos_relaxed = pyo.Constraint(
        instance.T, instance.Q, instance.S, rule=IM_bounds_1_pos_rule
    )

    def IM_bounds_2_rule(m, t, q, s):
        return sum(
            m.eIM_pos[i, t, q, s] + m.eIM_neg[i, t, q, s] for i in m.IMT[t]
        ) >= -_cap(m, t, q, s)
    instance.IM_bounds_2_relaxed = pyo.Constraint(
        instance.T, instance.Q, instance.S, rule=IM_bounds_2_rule
    )

    def IM_bounds_3_rule(m, i, t, q, s):
        return m.eIM[i, t, q, s] >= -_cap(m, t, q, s)
    instance.IM_bounds_3_relaxed = pyo.Constraint(
        instance.IM, instance.T, instance.Q, instance.S, rule=IM_bounds_3_rule
    )

    def IM_bounds_4_rule(m, i, t, q, s):
        return m.eIM[i, t, q, s] <= _cap(m, t, q, s)
    instance.IM_bounds_4_relaxed = pyo.Constraint(
        instance.IM, instance.T, instance.Q, instance.S, rule=IM_bounds_4_rule
    )


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
    """
    Solves one EV_g subproblem with the same Gurobi options as the RP model.

    If the subproblem is infeasible, this does NOT crash: Proposition 5's own
    proof allows for EDEV_T (and by extension any EDEV_t) to have no feasible
    solution ("the result is trivial"), so an infeasible EV_g is a legitimate,
    if unwelcome, outcome to handle rather than a hard error. Diagnostics are
    logged (via pyomo's own infeasibility utilities, the same ones solver.py's
    debug_infeasibility() already uses elsewhere in this codebase) and
    (None, status) is returned so the caller can decide how to proceed.
    """
    solver = SolverFactory("gurobi")
    for k, v in cfg.SOLVER_OPTIONS.items():
        solver.options[k] = v
    results = solver.solve(instance, tee=False)
    status = results.solver.termination_condition

    if status not in (
        pyo.TerminationCondition.optimal,
        pyo.TerminationCondition.maxTimeLimit,
        pyo.TerminationCondition.locallyOptimal,
    ):
        print(f"    [{label}] status={status}  INFEASIBLE OR UNSOLVED -- diagnostics follow:")
        for v in instance.component_data_objects(Var, active=True):
            if v.value is None:
                v.set_value(0)
        # log_infeasible_constraints() logs through Python's logging module,
        # not print(); without raising the logger's level it silently emits
        # nothing (this bit me on the first diagnostic pass).
        logger = logging.getLogger("pyomo.util.infeasible")
        logger.setLevel(logging.INFO)
        log_infeasible_constraints(instance, tol=1e-6, log_expression=True, log_variables=True)
        return None, status

    obj = value(instance.EECSW)
    print(f"    [{label}] status={status}  Z_EV_g={obj:.4f}")
    return obj, status
