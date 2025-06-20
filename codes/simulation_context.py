# simulation_context.py
from pathlib import Path
import os
import config_definition as cfg   # your run_config module


def prev_market(market: str) -> str | None:
    """Return the market that immediately precedes *market* in the chain."""
    chain = cfg.MARKET_CHAIN
    try:
        idx = chain.index(market.upper())
    except ValueError:                    # unknown market
        raise KeyError(f"Unknown market {market!r}")
    return None if idx == 0 else chain[idx-1]

class SimulationContext:
    """Holds all per-simulation data and runtime results."""

    __slots__ = (
        "sim", "pathres", "pathmarketres",
        "scenfile", "demfile",
        "solve_time", "n_scenarios",
        "obj_results", "scenario_data",
        "market", "famscen","pathscen",
        "previous_results_path",
    )

    def __init__(self, sim: int, market):
        self.sim = sim
        self.market = market
        # -------- derive paths / filenames -------------------------
        self.pathres       = Path("results")  / cfg.famscen_all / self.market / cfg.probl  / str(sim)
        self.pathmarketres = Path("results") /cfg.famscen_all / self.market / "market"   / str(sim)
        self.scenfile      = f"{cfg.famscen_all}-{sim}_{self.market}.dat"
        self.demfile       = f"demand-{sim}.dat"
        self.famscen = cfg.famscen_all+"_"+self.market
        self.pathscen = cfg.pathscen_all+"_"+self.market
        self.previous_results_path = self.get_previous_results_dir()

        # make sure resultfolders exist (relative to parent directory)
        for p in (self.pathres, self.pathmarketres):
            full_path = os.path.join("..", str(p))  # adjust path relative to parent dir
            os.makedirs(full_path, exist_ok=True)

        # -------- runtime-mutable fields ---------------------------
        self.solve_time   = None
        self.n_scenarios  = None
        self.obj_results  = {
            "obj_fun":       {},
            "obj_DA_income": {},
            "obj_RM_income": {},
            "obj_IM_income": {},
            "obj_IB_income": {},
            "obj_IB_costs":  {},
            "obj_IB_net":    {},
            "obj_FD_costs":  {},
        }
        self.scenario_data = None

    def get_previous_results_dir(self):
        if self.market != "DA":
            res = cfg.base_result_dir / cfg.famscen_all / prev_market(self.market) / "market" / self.sim / prev_market(self.market)
            return res
        else:
            return None
    # optional convenience --------------------------------------------------
    def __repr__(self) -> str:            # nice printing
        return f"SimulationContext(sim={self.sim}, pathres='{self.pathres}')"
