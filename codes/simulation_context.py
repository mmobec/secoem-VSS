import os

"""
This contains all mutable variables for a simulation run that should not be in 
run_config. Helper class to pass araound simulation parameters neatly between objects
"""

import os


class SimulationContext:

    def __init__(self, sim, famscen, probl, pathscen, pathdem, profitfile, timefile, numscenfile):
        self.sim = sim
        self.famscen = famscen
        self.probl = probl
        self.pathscen = pathscen
        self.pathdem = pathdem

        # File-specific paths
        self.pathres = f"results/{famscen}/{probl}/{sim}/"
        self.pathmarketres = f"results/{famscen}/market/{sim}/"

        self.scenfile = f"{famscen}-{sim}.dat"
        self.demfile = f"demand-{sim}.dat"

        # Ensure directories exist
        os.makedirs(os.path.join("..", self.pathres), exist_ok=True)
        os.makedirs(os.path.join("..", self.pathmarketres), exist_ok=True)

        # Mutable per-simulation data
        self.solve_time = None
        self.n_scenarios = None
        self.obj_results = {
            "obj_fun": {},
            "obj_DA_income": {},
            "obj_RM_income": {},
            "obj_IM_income": {},
            "obj_IB_income": {},
            "obj_IB_costs": {},
            "obj_IB_net": {},
            "obj_FD_costs": {},
        }

        self.profitfile = profitfile
        self.timefile = timefile
        self.numscenfile = numscenfile

