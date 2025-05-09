# simulation_context.py
from pathlib import Path
import os
import config_definition as cfg   # your run_config module

class SimulationContext:
    """Holds all per-simulation data and runtime results."""

    __slots__ = (
        "sim", "pathres", "pathmarketres",
        "scenfile", "demfile",
        "solve_time", "n_scenarios",
        "obj_results", "scenario_data",
    )

    def __init__(self, sim: int):
        self.sim = sim

        # -------- derive paths / filenames -------------------------
        self.pathres       = Path("results") / cfg.famscen / cfg.probl  / str(sim)
        self.pathmarketres = Path("results") / cfg.famscen / "market"   / str(sim)
        self.scenfile      = f"{cfg.famscen}-{sim}.dat"
        self.demfile       = f"demand-{sim}.dat"

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

    # optional convenience --------------------------------------------------
    def __repr__(self) -> str:            # nice printing
        return f"SimulationContext(sim={self.sim}, pathres='{self.pathres}')"
