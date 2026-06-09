# ---------------------------------------------------------------------
# 1) Basic "AMPL param" equivalents
# ---------------------------------------------------------------------
from pathlib import Path
"""
All static parameters for a simulation
"""

PROJECT_ROOT = Path.home() / "OneDrive" / "Documentos" / "MESIO" / "TFM" / "Repos" / "mmobec-pyomo"   #This is the root directory

MARKET_CHAIN = ["DA", "RM", "IM1", "IM2", "IM3", "IB"]

# For PreviousResultsLoader:

VAR_FILES = {
    "DA":  {"eDA_p": "eDA_p.txt",
            "eDA_m": "eDA_m.txt",
            "ieDA_p": "ieDA_p.txt",
            "ieDA_m": "ieDA_m.txt",
            "lD": "lD.txt"
            },
    "RM":  {"rU":    "rU.txt",
            "rD":    "rD.txt",
            "lR": "lR.txt",
            "rU_B": "rU_B.txt",
            "rD_B": "rD_B.txt",
            "rU_FD": "rU_FD.txt",
            "rD_FD": "rD_FD.txt",
            }
    #IM: ..
}

BESS_datfile     = "ec_BESS.dat"
wind_datfile     = "ec_wind.dat"
market_datfile   = "market.dat"
hydro_datfile    = "ec_HYD.dat"
# In AMPL: set PROB default {'ec'}; param probl symbolic default 'ec';
PROB  = ['ec']
probl = 'ec'

# Suppose we define a scenario family (famscen) & set of SIMS in Python:

famscen_all = "FTC_20251031_20251130_c30_sc10_15min_different_ren"
#famscen_all = "FTC_10_2023_12_HYDRO"


# Suppose we have SIMS = [001..031]
n_days = 1
SIMS = [f"{i:03d}" for i in range(1, n_days+1)]  # Example with just few days for brevity

pathscen_all = f"scenarios/{famscen_all}"
pathdem  = "data/demand-15mins/"
pathdem_h2 = "data/demand_h2"

# Some log-file placeholders
resfile      = "results_log.res"
profitfile   = {p: f"profit_{p}.txt" for p in PROB}
timefile     = {p: f"time_{p}.txt"   for p in PROB}
timefileFull = "time.txt"
numscenfile  = "numscen.txt"

### Solver options ###
SOLVER_OPTIONS = {
    # --- MILP tolerances & strategy ---
    "MIPGap":          1e-2,     # 0.0001
    "Threads":         4,
    "Presolve":        0,
    "Method":          3,        # dual simplex

    # --- Logging & run control ---
    "DisplayInterval": 2,
    "TimeLimit":       3600,     # seconds
    "Seed":            2,
}
