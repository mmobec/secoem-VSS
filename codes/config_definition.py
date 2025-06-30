# ---------------------------------------------------------------------
# 1) Basic "AMPL param" equivalents
# ---------------------------------------------------------------------
from pathlib import Path
"""
All static parameters for a simulation
"""

MARKET_CHAIN = ["DA", "RM", "IM1", "IM2", "IM3", "IB"]

# For PreviousResultsLoader:

DA_PARAMS = {
    "e_da_m_from_DAM_run": "eDA_m",
    "e_da_p_from_DAM_run": "eDA_p",
    "ld_from_DAM_run": "lD",
    "ieDA_m_from_DAM_run": "ieDA_m",
    "ieDA_p_from_DAM_run": "ieDA_p"
}

RM_PARAMS = ["lR", "rU", "rD", "rU_B", "rD_B", "rU_FD", "rD_FD" ]


BESS_datfile     = "ec_BESS.dat"
wind_datfile     = "ec_wind.dat"
market_datfile   = "market.dat"

# In AMPL: set PROB default {'ec'}; param probl symbolic default 'ec';
PROB  = ['ec']
probl = 'ec'

# Suppose we define a scenario family (famscen) & set of SIMS in Python:
#famscen = "FTC_10_2023_12"
famscen_all = "FTC_100_202410_202012"
#famscen_all = "FTC_100_202410_202012_all_random_DA"

# Suppose we have SIMS = [001..031]
n_days = 5
SIMS = [f"{i:03d}" for i in range(1, n_days+1)]  # Example with just few days for brevity

pathscen_all = f"scenarios/{famscen_all}"
pathdem  = "data/demand/"
base_result_dir = Path("results")

# Some log-file placeholders
resfile      = "results_log.res"
profitfile   = {p: f"profit_{p}.txt" for p in PROB}
timefile     = {p: f"time_{p}.txt"   for p in PROB}
timefileFull = "time.txt"
numscenfile  = "numscen.txt"

### Solver options ###
SOLVER_OPTIONS = {
    # --- MILP tolerances & strategy ---
    "MIPGap":          1e-4,     # 0.0001
    "Threads":         4,
    "Presolve":        0,
    "Method":          3,        # dual simplex

    # --- Logging & run control ---
    "DisplayInterval": 2,
    "TimeLimit":       3600,     # seconds
    "Seed":            2,
}
