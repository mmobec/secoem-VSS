"""
Validation checks for VSSD (Propositions 4, 5, 6, 7).

Reference: Escudero, L.F., Garin, A., Merino, M., Perez, G. (2007). "The value of
the stochastic solution in multistage problems." TOP 15, 48-64.

Ported unchanged from the HG (15min_ren_same) branch. Proposition 4 is checked
informationally only for the same reason as HG: this model has stochastic
objective coefficients (lD, lR, lI, lPIB, lNIB -- all market prices), so Prop.
4's "deterministic objective coefficients" hypothesis does not hold on either
branch. EDEV_2 == EDEV_1 is an *expected* outcome here too (RM bids submitted
alongside DA bids, before DA clears -- confirmed independently for QHS via
model_builder.py's _build_stage1_nac_index, see scenario_groups.py's
macro_stage_sg() docstring), not a validation failure.
"""

DEFAULT_TOL = 1e-6


def validate_propositions(rp_value, edev_by_stage, vssd_by_stage, tol=DEFAULT_TOL):
    """
    Runs Propositions 5, 6, 7 as pass/fail checks (within `tol`), and Proposition 4
    informationally. Returns a report dict: {"ok": bool, "checks": [ {...}, ... ]}.
    """
    checks = []
    ok = True
    T = max(edev_by_stage)

    # Proposition 5: VSSD >= 0.
    vssd = rp_value - edev_by_stage[T]
    check5_ok = vssd >= -tol
    ok &= check5_ok
    checks.append({
        "prop": "5", "statement": "VSSD >= 0",
        "VSSD": vssd, "ok": check5_ok,
    })

    # Proposition 6: EDEV_{t+1} <= EDEV_t, for t=1..T-1.
    for t in range(1, T):
        lhs, rhs = edev_by_stage[t + 1], edev_by_stage[t]
        check_ok = lhs <= rhs + tol
        note = None
        if t == 1:
            note = "EDEV_2 == EDEV_1 expected (RM shares DA's information set)"
        ok &= check_ok
        checks.append({
            "prop": "6", "t": t, "statement": f"EDEV_{t + 1} <= EDEV_{t}",
            f"EDEV_{t}": rhs, f"EDEV_{t + 1}": lhs, "ok": check_ok, "note": note,
        })

    # Proposition 7: 0 <= VSSD_t <= VSSD_{t+1}.
    for t in range(1, T + 1):
        nonneg_ok = vssd_by_stage[t] >= -tol
        ok &= nonneg_ok
        checks.append({
            "prop": "7", "t": t, "statement": f"VSSD_{t} >= 0",
            f"VSSD_{t}": vssd_by_stage[t], "ok": nonneg_ok,
        })
    for t in range(1, T):
        mono_ok = vssd_by_stage[t + 1] >= vssd_by_stage[t] - tol
        ok &= mono_ok
        checks.append({
            "prop": "7", "t": t, "statement": f"VSSD_{t} <= VSSD_{t + 1}",
            f"VSSD_{t}": vssd_by_stage[t], f"VSSD_{t + 1}": vssd_by_stage[t + 1], "ok": mono_ok,
        })

    # Proposition 4 (Jensen-based EDEV_{t+1} <= EDEV_t): informational only, since
    # this model has stochastic objective coefficients (market prices), violating
    # the proposition's hypothesis. Not counted towards `ok`.
    for t in range(1, T):
        lhs, rhs = edev_by_stage[t + 1], edev_by_stage[t]
        holds = lhs <= rhs + tol
        checks.append({
            "prop": "4-informational", "t": t,
            "statement": f"EDEV_{t + 1} <= EDEV_{t} (Jensen; hypothesis violated by design)",
            "holds": holds,
        })

    return {"ok": ok, "checks": checks}


def print_report(report):
    print("\n=== VSSD validation ===")
    for c in report["checks"]:
        mark = "OK" if c.get("ok", c.get("holds")) else "**FAIL**"
        extra = f"  ({c['note']})" if c.get("note") else ""
        print(f"  [{mark}] Prop.{c['prop']}: {c['statement']}{extra}")
    print(f"Overall: {'ALL CHECKS PASSED' if report['ok'] else 'SOME CHECKS FAILED'}")
