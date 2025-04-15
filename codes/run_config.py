# ---------------------------------------------------------------------
# 1) Basic "AMPL param" equivalents
# ---------------------------------------------------------------------

BESS_datfile     = "ec_BESS.dat"
wind_datfile     = "ec_wind.dat"
market_datfile   = "market.dat"

# In AMPL: set PROB default {'ec'}; param probl symbolic default 'ec';
PROB  = ['ec']
probl = 'ec'

# These are placeholders for scenario file and demand file
scenfile = None
demfile  = None

# Suppose we define a scenario family (famscen) & set of SIMS in Python:
famscen = "FTC_10_2023_12"
# Suppose we have SIMS = [001..031]
n_days = 2
SIMS = [f"{i:03d}" for i in range(1, n_days+1)]  # Example with just few days for brevity

pathscen = f"scenarios/{famscen}/"
pathdem  = "data/demand/"
pathres  = None         # Will be set inside the loop
pathmarketres = None

# Some log-file placeholders
resfile      = "results_log.res"
profitfile   = {p: f"profit_{p}.txt" for p in PROB}
timefile     = {p: f"time_{p}.txt"   for p in PROB}
timefileFull = "time.txt"
numscenfile  = "numscen.txt"

obj_results = {key: {} for key in [
    "obj_fun", "obj_DA_income", "obj_RM_income", "obj_IM_income",
    "obj_IB_income", "obj_IB_costs", "obj_IB_net", "obj_FD_costs"
]}
