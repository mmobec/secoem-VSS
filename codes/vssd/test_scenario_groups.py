"""
Lightweight, dependency-free regression test for scenario_groups.py.

Exercises build_macro_stage_groups() against a small hand-built mock of the
Pyomo instance attributes it reads (sgim, nSG, SSG, c, Prob, S) -- no Pyomo or
Gurobi required, so this can run anywhere. Run directly:

    python vssd/test_scenario_groups.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vssd.scenario_groups import build_macro_stage_groups, macro_stage_sg


class _Mock:
    """Minimal stand-in for the RP Pyomo instance attributes scenario_groups.py reads."""

    def __init__(self, sgim, nSG, S, SSG, c, prob):
        self._sgim = sgim
        self._nSG = nSG
        self.S = S
        self._SSG = SSG
        self._c = c
        self._prob = prob

    class _Indexed:
        def __init__(self, data):
            self._data = data

        def __getitem__(self, key):
            return self._data[key]

    @property
    def sgim(self):
        return self._Indexed(self._sgim)

    @property
    def nSG(self):
        return self._nSG

    @property
    def SSG(self):
        return self._Indexed(self._SSG)

    @property
    def c(self):
        return self._Indexed(self._c)

    @property
    def Prob(self):
        return self._Indexed(self._prob)


def build_mock():
    # 4 scenarios, equal probability. sgim: IM1 at fine-stage sgim=3 (-> sg=2),
    # IM2 at sgim=4 (-> sg=3), IM3 at sgim=5 (-> sg=4). nSG=5 (IB at the last stage).
    sgim = {1: 3, 2: 4, 3: 5}
    nSG = 5
    S = [1, 2, 3, 4]

    # sg=1 (DA, RM):        {1,2} | {3,4}
    # sg=2 (IM1):           {1,2} | {3} | {4}
    # sg=3 (IM2):           {1} | {2} | {3} | {4}
    # sg=4 (IM3):           {1} | {2} | {3} | {4}   (no further split)
    # sg=5 (IB, = nSG):     {1} | {2} | {3} | {4}   (no further split)
    SSG = {
        1: [1, 3],
        2: [1, 3, 4],
        3: [1, 2, 3, 4],
        4: [1, 2, 3, 4],
        5: [1, 2, 3, 4],
    }
    c = {
        (1, 1): [1, 2], (1, 3): [3, 4],
        (2, 1): [1, 2], (2, 3): [3], (2, 4): [4],
        (3, 1): [1], (3, 2): [2], (3, 3): [3], (3, 4): [4],
        (4, 1): [1], (4, 2): [2], (4, 3): [3], (4, 4): [4],
        (5, 1): [1], (5, 2): [2], (5, 3): [3], (5, 4): [4],
    }
    # 4 equal-probability scenarios (0.25 each); group weights below are derived by
    # summing these, matching what scenario_groups.py now computes directly from Prob.
    prob = {1: 0.25, 2: 0.25, 3: 0.25, 4: 0.25}
    return _Mock(sgim, nSG, S, SSG, c, prob)


def run():
    instance = build_mock()

    # macro_stage_sg mapping
    assert macro_stage_sg(instance, 1) == 1
    assert macro_stage_sg(instance, 2) == 1
    assert macro_stage_sg(instance, 3) == 2   # sgim[1]-1 = 3-1
    assert macro_stage_sg(instance, 4) == 3   # sgim[2]-1 = 4-1
    assert macro_stage_sg(instance, 5) == 4   # sgim[3]-1 = 5-1
    assert macro_stage_sg(instance, 6) == 5   # nSG
    print("macro_stage_sg mapping: OK")

    groups = build_macro_stage_groups(instance)

    # t=1 (DA): 2 groups, {1,2} and {3,4}
    g1 = groups[1]
    assert len(g1) == 2
    omegas1 = sorted(g.omega for g in g1)
    assert omegas1 == [(1, 2), (3, 4)]
    assert all(g.parent_id is None for g in g1)

    # t=2 (RM): must be identical partition to t=1 (G_2 == G_1, report §3.3)
    g2 = groups[2]
    omegas2 = sorted(g.omega for g in g2)
    assert omegas2 == omegas1, "G_2 must equal G_1 (RM shares DA's information set)"
    print("G_2 == G_1: OK (expected, RM bids submitted before DA clears)")

    # t=3 (IM1): 3 groups, {1,2} | {3} | {4}; ancestor of {1,2} is DA/RM's {1,2} group
    g3 = groups[3]
    assert len(g3) == 3
    omegas3 = sorted(g.omega for g in g3)
    assert omegas3 == [(1, 2), (3,), (4,)]
    parent_of_12 = next(g for g in g3 if g.omega == (1, 2)).parent_id
    dc_group_12 = next(g for g in g1 if g.omega == (1, 2)).group_id
    assert parent_of_12 == dc_group_12
    parent_of_3 = next(g for g in g3 if g.omega == (3,)).parent_id
    dc_group_34 = next(g for g in g1 if g.omega == (3, 4)).group_id
    assert parent_of_3 == dc_group_34
    print("Refinement t=1 -> t=3 and ancestor resolution: OK")

    # t=4, t=5, t=6: fully refined, 4 singleton groups each, weights sum to 1
    for t in (4, 5, 6):
        gt = groups[t]
        assert len(gt) == 4
        assert abs(sum(g.weight for g in gt) - 1.0) < 1e-12
        assert sorted(g.omega for g in gt) == [(1,), (2,), (3,), (4,)]
    print("Full refinement at t=4,5,6 and probability mass conservation: OK")

    # Weights sum to 1 at every stage
    for t in range(1, 7):
        total_w = sum(g.weight for g in groups[t])
        assert abs(total_w - 1.0) < 1e-12, f"weights at t={t} sum to {total_w}, expected 1.0"
    print("Weight conservation at every stage: OK")

    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    run()
