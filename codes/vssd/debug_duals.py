"""
Standalone diagnostic: solve RP, fix every binary variable at its solved
value (turning the remaining problem into a pure LP), re-solve to recover
duals, and check whether IM_bounds_3/4 or IB_pos_UB/IB_neg_UB are actually
binding at any (t,q,s) where RP's own optimal eDA_p+eDA_m is ~0.

Purpose: before applying the FD_U/slack relaxation to RP's own model (risky,
since eDA is a live decision variable there -- unlike in EV_g, where it's
already fixed, a relaxation could change what eDA RP finds optimal, not just
what eIM/pIB_p it allows), check directly whether RP's true optimum ever
needed more eIM/pIB_p than the cap=0-at-eDA=0 case allows. A zero dual means
the constraint never actually restricted RP there -- relaxing would be inert.
A nonzero dual means it is genuinely binding, and RP's own value would change.

Not part of the vssd/ package's normal flow. Usage:
    python vssd/debug_duals.py [sim]
Defaults to sim="001".
"""
import os
import sys

_CODES_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CODES_DIR not in sys.path:
    sys.path.insert(0, _CODES_DIR)

from pyomo.environ import SolverFactory, Suffix, Var, Binary, value

import config_definition as cfg
from vssd.run_vssd import solve_rp

EPS = 1e-6


def main():
    sim = sys.argv[1] if len(sys.argv) > 1 else "001"

    print(f"=== Dual extraction: sim={sim} ===")
    print("\n-- Solving RP (MIP) --")
    rp_instance, rp_scenario_data, abstract_model, sim_ctx = solve_rp(sim)
    rp_value = value(rp_instance.EECSW)
    print(f"RP (MIP) = {rp_value:.4f}")

    print("\n-- Fixing all binary variables at their solved values --")
    n_fixed = 0
    for v in rp_instance.component_objects(Var, active=True):
        for idx in v:
            vd = v[idx]
            if vd.domain is Binary and vd.value is not None:
                vd.fix(vd.value)
                n_fixed += 1
    print(f"Fixed {n_fixed} binary variable instances")

    rp_instance.dual = Suffix(direction=Suffix.IMPORT)

    print("\n-- Re-solving as LP (integers fixed) to recover duals --")
    solver = SolverFactory("gurobi")
    for k, v in cfg.SOLVER_OPTIONS.items():
        solver.options[k] = v
    results = solver.solve(rp_instance, tee=False)
    status = results.solver.termination_condition
    lp_value = value(rp_instance.EECSW)
    print(f"LP-with-fixed-integers status={status}  objective={lp_value:.4f} "
          f"(vs MIP {rp_value:.4f}, diff={lp_value - rp_value:.6f})")

    print("\n-- Locating (t,q,s) points where eDA_p+eDA_m ~= 0 --")
    near_zero = []
    for t in rp_instance.T:
        for q in rp_instance.Q:
            for s in rp_instance.S:
                D = value(rp_instance.eDA_p[t, q, s]) + value(rp_instance.eDA_m[t, q, s])
                if D < EPS:
                    near_zero.append((t, q, s))
    total = len(list(rp_instance.T)) * len(list(rp_instance.Q)) * len(list(rp_instance.S))
    print(f"{len(near_zero)} / {total} (t,q,s) points have eDA~=0")

    print("\n-- Checking duals of IM_bounds_3/4 and IB_pos_UB/IB_neg_UB at those points --")
    binding = []
    checked = 0
    for (t, q, s) in near_zero:
        for i in rp_instance.IMT[t]:
            for cname in ("IM_bounds_3", "IM_bounds_4"):
                comp = getattr(rp_instance, cname, None)
                if comp is None:
                    continue
                c = comp[i, t, q, s]
                checked += 1
                d = rp_instance.dual.get(c, 0.0)
                if abs(d) > EPS:
                    binding.append((cname, i, t, q, s, d))
        for cname in ("IB_pos_UB", "IB_neg_UB"):
            comp = getattr(rp_instance, cname, None)
            if comp is None:
                continue
            c = comp[t, q, s]
            checked += 1
            d = rp_instance.dual.get(c, 0.0)
            if abs(d) > EPS:
                binding.append((cname, None, t, q, s, d))

    print(f"Checked {checked} constraint instances at eDA~=0 points")
    if binding:
        print(f"\n{len(binding)} BINDING (nonzero dual) constraints found:")
        for row in binding[:100]:
            print(" ", row)
        print("\n=> RP's true optimum WOULD benefit from relaxing these -- "
              "adding the fallback to RP would change RP's own value, not just be inert.")
    else:
        print("\nNo binding IM_bounds/IB_bounds constraints found at any eDA~=0 point.")
        print("=> The cap is never actually restricting RP's own optimum there -- "
              "relaxing it in RP (once DA is already fixed) should be inert.")


if __name__ == "__main__":
    main()
