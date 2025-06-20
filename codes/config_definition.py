# ---------------------------------------------------------------------
# 1) Basic "AMPL param" equivalents
# ---------------------------------------------------------------------
from pathlib import Path
"""
All static parameters for a simulation
"""

MARKET_CHAIN = ["DA", "RM", "IM1", "IM2", "IM3", "IB"]

BESS_datfile     = "ec_BESS.dat"
wind_datfile     = "ec_wind.dat"
market_datfile   = "market.dat"

# In AMPL: set PROB default {'ec'}; param probl symbolic default 'ec';
PROB  = ['ec']
probl = 'ec'

# These are placeholders for scenario file and demand file
#scenfile = None
#demfile  = None

# Suppose we define a scenario family (famscen) & set of SIMS in Python:
#famscen = "FTC_10_2023_12"
famscen_all = "FTC_100_2023_v2"
# Suppose we have SIMS = [001..031]
n_days = 1
SIMS = [f"{i:03d}" for i in range(1, n_days+1)]  # Example with just few days for brevity

pathscen_all = f"scenarios/{famscen_all}"
pathdem  = "data/demand/"
base_result_dir = Path("results")
#pathres  = None         # Will be set inside the loop
#pathmarketres = None

# Some log-file placeholders
resfile      = "results_log.res"
profitfile   = {p: f"profit_{p}.txt" for p in PROB}
timefile     = {p: f"time_{p}.txt"   for p in PROB}
timefileFull = "time.txt"
numscenfile  = "numscen.txt"

# location of the DAM run results folder (to extract the matched energy)
#dam_results_folder = "data/DAM_sim_results"

### Solver options ###
# config_definition.py  (or just config.py)

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

DA_PRICE_OBS = {
     1:  96.07,  2:  94.32,  3:  92.11,  4:  90.25,
     5:  88.60,  6:  87.45,  7:  90.10,  8:  95.80,
     9: 100.30, 10: 102.40, 11: 103.70, 12: 104.10,
    13: 103.00, 14: 101.20, 15:  98.90, 16:  96.80,
    17:  95.50, 18:  97.10, 19: 101.80, 20: 108.40,
    21: 110.20, 22: 107.00, 23: 102.50, 24:  98.80,
}


# --- Day‑Ahead accepted SALES  (eDA_p) ----------------------------
DA_E_P_OBS = {t: 0.0 for t in range(1, 25)}          # all zeros

# --- Day‑Ahead accepted PURCHASES (eDA_m)  –‑ scenario 1 ----------
"""
DA_E_M_OBS = {
     1: 19.203390000000002,
     2: 19.605060833333336,
     3: 18.010591666666667,
     4: 16.16319,
     5: 20.192275,
     6: 21.254574999999996,
     7: 23.2888125,
     8: 29.76,
     9: 22.75,
    10: 29.5765,
    11: 38.62940625,
    12: 51.120000000000005,
    13: 50.93,
    14: 44.724792499999964,
    15: 46.73624999999999,
    16: 42.188750000000006,
    17: 39.04359999999999,
    18: 43.643360000000015,
    19: 40.3360625,
    20: 29.053066666666663,
    21: 33.91674166666667,
    22: 33.98761666666667,
    23: 27.614839166666663,
    24: 35.75,
}
"""

def load_dam_prices(file_path):
    """
    Reads DAM prices from a text file and returns a dictionary indexed by (t, s).

    Returns:
        dict: {(t, s): price}
    """
    DA_E_M_OBS = {}

    with open("/Users/janjettmann/PycharmProjects/mmobec-pyomo/results/Cristian_testing/market/001/DA/eDA_m.txt", 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 26:
                continue  # skip malformed lines

            s = int(parts[0])  # scenario number
            # parts[1] is probability, which we skip for this
            prices = list(map(float, parts[2:]))

            for t, price in enumerate(prices, start=1):  # t from 1 to 24
                DA_E_M_OBS[(t, s)] = price

    return DA_E_M_OBS

DA_E_M_OBS = load_dam_prices("zxc")
"""
obj_results = {key: {} for key in [
    "obj_fun", "obj_DA_income", "obj_RM_income", "obj_IM_income",
    "obj_IB_income", "obj_IB_costs", "obj_IB_net", "obj_FD_costs"
]}

solve_time = {}
n_scenarios = {}
"""