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
decision -- see report §2.1/2.5): this file never modifies model_builder.py,
instancemanager.py, preprocessing.py, or config_definition.py; it only reuses
them as-is (InstanceManager included, for build_full_instance() below).

Also provides build_full_instance()/solve_full_instance_with_exclusion(), used
by both run_static_vss.py's static EEV_t/VSS_t chain (Definition 1) and
run_vssd.py's supplementary EDEV_2_recourse comparator: unlike build_ev_instance
(one synthetic averaged scenario), these build a genuine multi-scenario
instance over a set of real, surviving scenarios, with Gurobi-IIS-based
scenario exclusion on infeasibility (Definition 3's remedy).
"""
import copy
import logging
import os
import re

import pyomo.environ as pyo
from pyomo.environ import DataPortal, SolverFactory, Var, value
from pyomo.util.infeasible import log_infeasible_constraints

import config_definition as cfg
from instancemanager import InstanceManager

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

    # Price the FD_U-fallback eIM usage at C_FD (model_builder.py:88), the
    # model's own existing, active flexible-demand cost rate -- the same rate
    # that already prices var_afd_p/var_afd_m (model_builder.py:493-497).
    # eIM enters EECSW as pure revenue (term_im, model_builder.py:472-478); an
    # unpriced FD_U-sized cap would let the optimizer manufacture free revenue
    # at every (t,q,s) where the fallback fires, not just escape the spurious
    # infeasibility. Only the fallback branch (D<=EPS) is priced -- when
    # D>EPS, cap=maxTIM*D is the model's own real rule, untouched, no penalty.
    penalty_eIM = sum(
        value(instance.Prob[s]) * value(instance.C_FD)
        * (instance.eIM_pos[i, t, q, s] + instance.eIM_neg[i, t, q, s])
        for t in instance.T
        for q in instance.Q
        for s in instance.S
        if value(instance.eDA_p[t, q, s]) + value(instance.eDA_m[t, q, s]) <= EPS
        for i in instance.IMT[t]
    )
    new_expr = instance.EECSW.expr - penalty_eIM
    instance.del_component("EECSW")
    instance.EECSW = pyo.Objective(expr=new_expr, sense=pyo.maximize)


# Matches model_builder.py's own imbalanceSlackPenalty default (100) -- that
# Param is only ever declared in the RM/"IM" market branch (model_builder.py:850),
# never under market="DA", so it doesn't exist on any VSSD instance to read from.
_IB_SLACK_PENALTY_RATE = 100.0


def relax_ib_bounds_for_fixed_da(instance):
    """
    IM1/IM2/IM3/IB fix: reproduce model_builder.py's IB_pos_UB/IB_neg_UB "not DA"
    fallback on an EV_g instance (call only for t>=3, after apply_fixed_values()
    and alongside relax_im_bounds_for_fixed_da()) -- the same structural bug as
    that function fixes, hitting a different pair of constraints.

    IB_pos_UB/IB_neg_UB bound pIB_p/pIB_m by PIB_p/PIB_m under market="DA"
    (model_builder.py:839-846), with no slack -- vs. market in {"RM","IM*"},
    which relaxes to PIB_p/PIB_m + IB_pos_slack/IB_neg_slack (model_builder.py:
    848-857). Every EV_g here is built under market="DA" (see module docstring),
    so it always carries the hard, no-slack branch.

    Unlike eDA (a decision variable RP can choose to avoid pinching its own
    cap), PIB_p/PIB_m are pure precomputed DATA (instancemanager.py::
    compute_imbalance_bounds(): PIB_p[t,q,s] = max(0, pW[t,q,s]+pPV[t,q,s] -
    mean_pW[t,q]-mean_pPV[t,q]), i.e. the *positive part* of a scenario's
    deviation from the population-mean renewable output). PIB_p[t,q,s]=0
    whenever that scenario sits at or below the mean at that quarter -- not a
    rare edge case but the routine outcome for roughly half of all
    scenario/quarter pairs, and for a singleton group (|Omega_g|=1, as
    confirmed for the t=3 g=10 group this was diagnosed against via Gurobi
    IIS) there's no averaging to smooth it away: PIB_p for the group *is*
    PIB_p for that one scenario. RP never hits this because it solves every
    scenario's full joint recourse (eIM, battery, flexible demand) with
    nothing pre-fixed, so it always has some other way to keep pIB_p<=0 when
    PIB_p=0; an EV_g downstream in the fixing chain may not, once earlier
    stages' fixed values have already used up that recourse.

    IB_pos_slack/IB_neg_slack (bounded [0,200]) already exist on every VSSD
    instance regardless of market -- their declaration is gated on
    `self.model != "DA"` (model_builder.py:399), which compares the
    AbstractModel object itself to the string "DA" and is therefore always
    True, a latent bug that happens to work in our favour here: the slack
    variables are present, just never wired into an active constraint under
    market="DA". This reproduces the RM/IM branch's constraint formula
    directly, reusing those already-declared variables.

    Objective correction: pIB_p enters EECSW as pure revenue (Prob*lPIB*pIB_p,
    model_builder.py:481-485, added in a maximization). Relaxing its cap
    without pricing IB_pos_slack would let the optimizer manufacture up to
    200 units of free revenue whenever profitable, not just enough to escape
    a spurious infeasibility -- silently inflating Z_EV^g/EDEV_t rather than
    reporting a genuine economic estimate (IB_neg_slack is self-limiting even
    unpenalized, since pIB_m is a cost term, but both are penalized here to
    match model_builder.py's own -- currently commented-out, model_builder.py:
    499-505 -- design intent exactly). EECSW is deactivated and recreated
    under the same name (not a new one) so solve_ev_instance()'s existing
    value(instance.EECSW) call keeps working, now evaluating the penalized
    expression the instance was actually optimized against.
    """
    for name in ("IB_pos_UB", "IB_neg_UB"):
        getattr(instance, name).deactivate()

    def IB_pos_UB_relaxed_rule(m, t, q, s):
        return m.pIB_p[t, q, s] <= value(m.PIB_p[t, q, s]) + m.IB_pos_slack[t, q, s]
    instance.IB_pos_UB_relaxed = pyo.Constraint(
        instance.T, instance.Q, instance.S, rule=IB_pos_UB_relaxed_rule
    )

    def IB_neg_UB_relaxed_rule(m, t, q, s):
        return m.pIB_m[t, q, s] <= value(m.PIB_m[t, q, s]) + m.IB_neg_slack[t, q, s]
    instance.IB_neg_UB_relaxed = pyo.Constraint(
        instance.T, instance.Q, instance.S, rule=IB_neg_UB_relaxed_rule
    )

    penalty = sum(
        value(instance.Prob[s]) * _IB_SLACK_PENALTY_RATE *
        (instance.IB_pos_slack[t, q, s] + instance.IB_neg_slack[t, q, s])
        for t in instance.T for q in instance.Q for s in instance.S
    )
    new_expr = instance.EECSW.expr - penalty
    instance.del_component("EECSW")
    instance.EECSW = pyo.Objective(expr=new_expr, sense=pyo.maximize)


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


def build_full_instance(sim_ctx, abstract_model, rp_scenario_data, rp_instance,
                         surviving_scenarios, renormalize=True):
    """
    Builds a fresh full-scale instance restricted to `surviving_scenarios` (a
    set of real scenario ids) -- each scenario keeps its own real data, no
    Omega_g-conditional averaging (unlike build_ev_instance()).

    If renormalize, probabilities are rescaled to sum to 1 (a genuine
    reduced-scenario EEV_t solve, once infeasible scenarios have been
    excluded). If not, every scenario keeps its own real, absolute Prob value
    (for partitioning RP's own scenarios into disjoint groups whose
    sub-objectives sum back to RP's own total exactly, as
    run_vssd.compute_edev2_recourse() does).

    Goes through the real InstanceManager.compute_instance() pipeline (not
    build_ev_instance()'s portal shortcut), because pW/pPV/PIB_p/PIB_m must be
    genuinely recomputed from each surviving real scenario's own Scen data,
    not substituted by a conditional average.
    """
    raw = rp_scenario_data.data()
    prob = {s: value(rp_instance.Prob[s]) for s in rp_instance.S}
    surviving_scenarios = set(int(s) for s in surviving_scenarios)

    portal = DataPortal()
    for key, val in raw.items():
        portal[key] = copy.deepcopy(val)
    portal["S"] = {None: sorted(surviving_scenarios)}
    if renormalize:
        total_w = sum(prob[s] for s in surviving_scenarios)
        portal["Prob"] = {s: prob[s] / total_w for s in surviving_scenarios}
    else:
        portal["Prob"] = {s: prob[s] for s in surviving_scenarios}
    # Every S-indexed (not S0-indexed) raw param needs the same restriction as
    # S itself: Scen0/Prob0/c stay untouched (indexed over S0), but Scen and
    # the market-price params below are indexed over S and would otherwise
    # keep entries for excluded scenarios, outside S's new, smaller domain.
    portal["Scen"] = {
        (rv, s): v for (rv, s), v in raw["Scen"].items() if s in surviving_scenarios
    }
    for pname in _RAW_PARAMS_TQ + _RAW_PARAMS_ITQ:
        portal[pname] = {
            key: v for key, v in raw[pname].items() if key[-1] in surviving_scenarios
        }

    instance_wrapper = InstanceManager(portal, sim_ctx, abstract_model)
    instance_wrapper.compute_instance()
    return instance_wrapper.instance


# Matches every "name(idx)" occurrence in a Gurobi IIS .ilp file (LP format),
# both constraint names and every variable reference inside their bodies.
_NAME_IDX_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\(([\d_]+)\)")


def _parse_iis_scenarios(ilp_path):
    """
    Extracts every real-scenario index appearing in an IIS .ilp file -- scans
    every name(digits_and_underscores) occurrence (constraint names *and*
    every variable reference in their bodies, plus Bounds/Binaries) from
    "Subject To" through "End".

    DA_bid_mono (and any other "*mono*"-named constraint) encodes two scenario
    indices directly in its own name (the last two underscore-separated
    tokens, l and k) -- both are extracted even when Gurobi's presolve has
    eliminated every variable from that row (e.g. both endpoints already
    fixed), leaving nothing else in the file to name them.
    """
    scenarios = set()
    active = False
    with open(ilp_path) as f:
        for line in f:
            stripped = line.strip()
            if stripped == "Subject To":
                active = True
                continue
            if stripped == "End":
                break
            if not active:
                continue
            for name, idx in _NAME_IDX_RE.findall(line):
                tokens = idx.split("_")
                if not tokens or not tokens[-1].isdigit():
                    continue
                if "mono" in name.lower() and len(tokens) >= 2 and tokens[-2].isdigit():
                    scenarios.add(int(tokens[-2]))
                scenarios.add(int(tokens[-1]))
    return scenarios


def solve_full_instance_with_exclusion(
    sim_ctx, abstract_model, rp_scenario_data, rp_instance, fix_fn, label,
    max_rounds=10, max_excluded_weight=0.5,
):
    """
    Solves a full-scale (real, multi-scenario) instance, calling
    fix_fn(instance, surviving_scenarios) to apply whatever fixing is needed
    before each solve. On infeasibility, computes a Gurobi IIS (ResultFile=
    *.ilp), removes every scenario named in it via _parse_iis_scenarios(),
    renormalizes the survivors' weights, and retries (Escudero Definition 3's
    own remedy). Stops -- returning (None, excluded_weight) -- once a solve
    succeeds, the IIS names no new scenario (nothing left to exclude), or a
    safety cap trips (max_rounds, max_excluded_weight).

    Returns (obj_or_None, excluded_weight).
    """
    all_scenarios = set(int(s) for s in rp_instance.S)
    excluded = set()

    for round_no in range(max_rounds):
        surviving = all_scenarios - excluded
        if not surviving:
            print(f"    [{label}] all scenarios excluded -- giving up")
            return None, sum(value(rp_instance.Prob[s]) for s in all_scenarios)

        instance = build_full_instance(
            sim_ctx, abstract_model, rp_scenario_data, rp_instance, surviving, renormalize=True
        )
        fix_fn(instance, surviving)
        relax_im_bounds_for_fixed_da(instance)
        relax_ib_bounds_for_fixed_da(instance)

        ilp_path = os.path.join(cfg.PROJECT_ROOT, f"vssd_{label}_round{round_no}.ilp")
        solver = SolverFactory("gurobi")
        for k, v in cfg.SOLVER_OPTIONS.items():
            solver.options[k] = v
        solver.options["ResultFile"] = ilp_path
        results = solver.solve(instance, tee=False, symbolic_solver_labels=True)
        status = results.solver.termination_condition

        if status == pyo.TerminationCondition.optimal:
            obj = value(instance.EECSW)
            excluded_weight = sum(value(rp_instance.Prob[s]) for s in excluded)
            print(f"    [{label}] round {round_no}: status=optimal  Z={obj:.4f}"
                  + (f"  (excluded {excluded_weight:.4f} probability mass)" if excluded else ""))
            return obj, excluded_weight

        if not os.path.exists(ilp_path):
            print(f"    [{label}] round {round_no}: status={status}, no IIS written -- giving up")
            return None, sum(value(rp_instance.Prob[s]) for s in excluded)

        new_bad = _parse_iis_scenarios(ilp_path) & surviving
        if not new_bad:
            print(f"    [{label}] round {round_no}: infeasible, IIS named no new scenarios -- giving up")
            return None, sum(value(rp_instance.Prob[s]) for s in excluded)

        excluded |= new_bad
        excluded_weight = sum(value(rp_instance.Prob[s]) for s in excluded)
        print(f"    [{label}] round {round_no}: infeasible, excluding scenarios {sorted(new_bad)} "
              f"(cumulative excluded weight {excluded_weight:.4f})")
        if excluded_weight > max_excluded_weight:
            print(f"    [{label}] excluded weight exceeds {max_excluded_weight} -- giving up")
            return None, excluded_weight

    print(f"    [{label}] hit max_rounds={max_rounds} -- giving up")
    return None, sum(value(rp_instance.Prob[s]) for s in excluded)
