# -*- coding: utf-8 -*-
"""
Created on Mon Jan 27 11:06:23 2025

@author: andre
"""


# =============================================================================
# Pyomo translation of ec_run.py
# 
# A Python script replicating ec.run
# when using a Pyomo AbstractModel defined in ec_model.py.
# 
# NOTE: We assume 'ec_model.py' is in the same folder, containing:
#   from pyomo.environ import AbstractModel, ...
#   model = AbstractModel()
#   # [ sets, params, constraints, etc. ]
# =============================================================================

import os
import math
import time
import pyomo.environ as pyo
from pyomo.environ import DataPortal, value, SolverFactory
from ec_model import model as abstract_model  # Your AbstractModel definition

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
# In your code, "include ucwb_famscen.run" & "include ucwb_SIMS.run" might set them.
famscen = "FTC_10_2023_12"
# Suppose we have SIMS = [001..031]
SIMS = [f"{i:03d}" for i in range(1, 4)]  # Example with just 2 days for brevity

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

# ---------------------------------------------------------------------
# 2) Load "base" data for the model (market, BESS, wind)
#    This is equivalent to:
#       model ec.mod; data data/market.dat; data data/ec_BESS.dat; data data/ec_wind.dat;
# ---------------------------------------------------------------------
print("\n########################")
print(f"#### Problem {probl}")
print("########################\n")

# base_data = DataPortal()
# # If your 'ec_model.py' is truly an AbstractModel, we load base data here:
# base_data.load(filename=os.path.join("..", "data", market_datfile),  model=abstract_model)
# base_data.load(filename=os.path.join("..", "data", BESS_datfile),    model=abstract_model)
# base_data.load(filename=os.path.join("..", "data", wind_datfile),    model=abstract_model)
# scenfile = f"{famscen}-{SIMS[0]}.dat"
# demfile = f"demand-{SIMS[0]}.dat"
# base_data.load(filename=os.path.join("..", pathscen, scenfile), model=abstract_model)
# base_data.load(filename=os.path.join("..", pathdem,  demfile),  model=abstract_model)

# # Create a partial instance with base data. We'll re-initialize for each scenario in the loop.
# base_instance = abstract_model.create_instance(base_data)

obj_results = {key: {} for key in [
    "obj_fun", "obj_DA_income", "obj_RM_income", "obj_IM_income",
    "obj_IB_income", "obj_IB_costs", "obj_IB_net", "obj_FD_costs"
]}

solve_time = {}
n_scenarios = {}

# ---------------------------------------------------------------------
# 3) For each sim in SIMS, replicate the logic in ec.run
# ---------------------------------------------------------------------
for sim in SIMS:
    # Print messages like AMPL:
    print("\n########################")
    print(f"#### Instance {probl}-{sim}")
    print("########################\n")

    pathres       = f"results/{famscen}/{probl}/{sim}/"
    pathmarketres = f"results/{famscen}/market/{sim}/"
    
    # Ensure pathres and pathmarketres exist before writing files
    os.makedirs(os.path.join("..", pathres), exist_ok=True)
    os.makedirs(os.path.join("..", pathmarketres), exist_ok=True)

    # let scenfile := famscen&"-"&sim&".dat";
    scenfile = f"{famscen}-{sim}.dat"
    print(f"scenfile path = {pathscen}{scenfile}")
    print(f"pathres        = {pathres}")

    # let demfile := "demand-"&sim&".dat";
    demfile = f"demand-{sim}.dat"
    print(f"demfile path   = {pathdem}{demfile}")
    print(f"pathres        = {pathres}")

    scenario_data = DataPortal()
    # Load the "base" data 
    scenario_data.load(filename=os.path.join("..", "data", market_datfile),  model=abstract_model)
    scenario_data.load(filename=os.path.join("..", "data", BESS_datfile),    model=abstract_model)
    scenario_data.load(filename=os.path.join("..", "data", wind_datfile),    model=abstract_model)

    # Then load scenario & demand data
    scenario_data.load(filename=os.path.join("..", pathscen, scenfile), model=abstract_model)
    scenario_data.load(filename=os.path.join("..", pathdem,  demfile),  model=abstract_model)
    print(f"nT = {scenario_data['nT']}, nS = {scenario_data['nS']}, nIM = {scenario_data['nIM']}")
    print(f"T = {list(range(1, scenario_data['nT'] + 1))}")  # Expected range
    
    # Extract Prob0 values directly from scenario_data **before creating the instance**
    Prob0_raw = scenario_data.data().get("Prob0", {})  # Extract raw probabilities

    # Compute preserved scenarios BEFORE creating the instance
    S_preserved = [s for s in Prob0_raw if Prob0_raw[s] > 0]
    Prob_preserved = {s: Prob0_raw[s] for s in S_preserved}
    
    print(f"Probabilities at Day {sim}: {Prob_preserved}")
    print(f"Preserved Scenarios (S): {S_preserved}")
    print(f"Sum of Probabilities: {sum(Prob_preserved.values())}")

    # Inject `S_preserved` and `Prob_preserved` into `scenario_data`
    scenario_data.data()["S"] = {None: S_preserved}  # Ensure correct S
    scenario_data.data()["Prob"] = Prob_preserved  # Assign Probabilities correctly
    
    # Extract `Scen0` values before creating the instance
    Scen0_raw = scenario_data.data().get("Scen0", {})  # Extract full scenario data
    # Compute preserved scenarios BEFORE creating the instance
    Scen_preserved = {}

    # Compute `nRV` manually before creating the instance
    nRV_value = sum(scenario_data.data()["nRVSG"].values())
    
    # Only keep `Scen0` values that belong to preserved scenarios
    for rv in range(1, nRV_value + 1):  # Loop over random variables
        for s in S_preserved:
            Scen_preserved[(rv, s)] = Scen0_raw.get((rv, s), 0.0)  # Default to 0.0 if missing

    # Inject preserved `Scen` values before `create_instance()`
    scenario_data.data()["Scen"] = Scen_preserved
    
    # Extract `lD` values before creating the instance
    lD_preserved = {}
    for t in range(1, scenario_data["nT"] + 1):  # Iterate over T
        for s in S_preserved:  # Only for preserved scenarios
            lD_preserved[(t, s)] = scenario_data.data().get("Scen", {}).get((t, s), 0.0)  # Default to 0.0 if missing
    
    scenario_data.data()["lD"] = lD_preserved  # Assign `lD` values
  
    # Create instance for this scenario
    instance = abstract_model.create_instance(scenario_data)
    print(f"Instance Variables: {len(list(instance.component_objects(pyo.Var)))}")
    print(f"Instance Constraints: {len(list(instance.component_objects(pyo.Constraint)))}")
    if hasattr(instance, 'var_fd'):
        print(f"var_fd size: {len(list(instance.var_fd.keys()))}")  # Should be 24
    print(f"T size: {len(list(instance.T))}")  # Should be 24
    print(f"S size: {len(list(instance.S))}")  # Should be 10
    
    # instance.del_component("Ssd")

    # instance.add_component(
    #     "Ssd",
    #     pyo.Set(
    #         initialize=lambda m: [
    #             (t, l, j)
    #             for t in m.T
    #             for l in m.S
    #             for j in m.S
    #             if (float(value(m.lD[t, l])) <= float(value(m.lD[t, j]))) and (j != l)
    #         ],
    #         dimen=3
    #     )
    # )


    # Compute Expected Scenario (ScenE)
    ScenE_dict = {}
    for rv in range(1, value(instance.nRV) + 1):  # Loop over all random variables
        ScenE_dict[rv] = sum(value(instance.Prob0[s_]) * value(instance.Scen0[rv, s_]) for s_ in instance.S0)
    
    # Store into Pyomo model (ScenE is mutable, so we can assign values)
    for rv, val in ScenE_dict.items():
        instance.ScenE[rv] = val
        
    # Filter scenario clusters
    c_filtered = {}
    for sg in instance.SG0:
        for s in instance.S0:
            c_filtered[(sg, s)] = [sc for sc in instance.c[sg, s] if sc in instance.S]
    
    # Store filtered clusters back into Pyomo model
    for (sg, s), cluster in c_filtered.items():
        instance.c[sg, s] = sorted(cluster)
        
    # # Assign values to preserved set of scenarios (Scen)
    # for rv in range(1, value(instance.nRV) + 1):
    #     for s in instance.S:
    #         instance.Scen[rv, s] = value(instance.Scen0[rv, s])  
        
    pW_dict = {}
    pPV_dict = {}
    mean_pW_dict = {}
    mean_pPV_dict = {}
    sigma_pW_dict = {}
    
    # Compute pW and pPV
    for t in instance.T:
        for s in instance.S:
            # Fetch the correct random variable index from fRVSG
            rv_index_wind = value(instance.fRVSG[value(instance.sgpw[t])])
            rv_index_solar = rv_index_wind + 1  # Next variable corresponds to PV
            
            # Compute wind power
            pW_dict[(t, s)] = min(value(instance.Scen[rv_index_wind, s]), 1.0) * value(instance.Pavg)
            
            # Compute PV power
            pPV_dict[(t, s)] = min(value(instance.Scen[rv_index_solar, s]), 1.0) * value(instance.Pavg_PV)
    
    # Compute mean values
    for t in instance.T:
        mean_pW_dict[t] = sum(value(instance.Prob[s]) * pW_dict[(t, s)] for s in instance.S)
        mean_pPV_dict[t] = sum(value(instance.Prob[s]) * pPV_dict[(t, s)] for s in instance.S)
    
    # Compute sigma_pW (standard deviation)
    for t in instance.T:
        variance_pW = sum(value(instance.Prob[s]) * (pW_dict[(t, s)] - mean_pW_dict[t]) ** 2 for s in instance.S)
        sigma_pW_dict[t] = math.sqrt(variance_pW)

    # Store values in Pyomo model
    for (t, s), val in pW_dict.items():
        instance.pW[t, s] = val
    for (t, s), val in pPV_dict.items():
        instance.pPV[t, s] = val
    for t, val in mean_pW_dict.items():
        instance.mean_pW[t] = val
    for t, val in mean_pPV_dict.items():
        instance.mean_pPV[t] = val
    for t, val in sigma_pW_dict.items():
        instance.sigma_pW[t] = val   

    # Compute max values for wind and solar power
    max_pW = max(value(instance.pW[t, s]) for t in instance.T for s in instance.S)
    max_pPV = max(value(instance.pPV[t, s]) for t in instance.T for s in instance.S)
             
    # Store max values in Pyomo model
    instance.max_pW = max_pW
    instance.max_pPV = max_pPV
        
    # Print results
    print(f"max_pW: {max_pW}, max_pPV: {max_pPV}")
    
    with open(os.path.join("..", pathres, resfile), "a") as res_log:
        res_log.write(f"max_pW: {max_pW}, max_pPV: {max_pPV}\n")

    # Cardinality of S0 and S
    card_S0 = len(instance.S0)
    card_S = len(instance.S)
    
    # Print cardinality to results log
    with open(os.path.join("..", pathres, resfile), "a") as res_log:
        res_log.write("\n Cardinality of the problem:\n")
        res_log.write(f"card(S0): {card_S0}\n")
        res_log.write(f"card(S): {card_S}\n")
    print(f"card(S0): {card_S0}, card(S): {card_S}")           
            
    dTO_dict = {}
    min_dTO = 10**10  # Large initial value
    sOR = -1  # Default value
    
    # Compute distances dTO[s]
    for s in instance.S:
        dTO_dict[s] = math.sqrt(sum((value(instance.Scen[rv, s]) - value(instance.ScenO[rv])) ** 2 for rv in range(1, value(instance.nRV) + 1)))
    
    # Find the scenario with the minimum distance
    for s in instance.S:
        if dTO_dict[s] < min_dTO:
            min_dTO = dTO_dict[s]
            sOR = s
    
    # Store in Pyomo model
    instance.min_dTO = min_dTO
    instance.sOR = sOR
    
    # Log nearest tree scenario
    with open(os.path.join("..", pathres, resfile), "a") as res_log:
        res_log.write("\n Nearest Tree scenario, Observed data:\n")
        res_log.write(f"sOR: {sOR}\n")
        res_log.write(f"min_dTO: {min_dTO}\n")
    print(f"Nearest Tree Scenario: sOR={sOR}, min_dTO={min_dTO}")

    # Reset IM bid bounds and auxiliary parameters
    SSG_dict = {sg: set() for sg in instance.SG0}  # Representative scenarios per stage
    probc_dict = {}  # Probability of clusters
    # mean_pWc_dict = {}  # Conditional mean wind power

    # Identify representative scenarios at each stage sg
    for sg in instance.SG0:
        SSG_dict[sg] = sorted({s for s in instance.S0 if len(instance.c[sg, s]) > 0})
    
    # Compute probability of cluster c[sg, sc]
    for sg in instance.SG0:
        for sc in SSG_dict[sg]:
            probc_dict[sg, sc] = sum(value(instance.Prob[s]) for s in instance.c[sg, sc])
    
    # # Compute conditional mean wind power for every cluster
    # for sg in instance.SG0:
    #     for sc in SSG_dict[sg]:
    #         for t in instance.T:
    #             if probc_dict.get((sg, sc), 0) > 0:
    #                 mean_pWc_dict[sg, sc, t] = sum(value(instance.Prob[s]) * value(instance.pW[t, s]) for s in instance.c[sg, sc]) / probc_dict[sg, sc]
    
    # Store computed values into the Pyomo model
    for sg, scenarios in SSG_dict.items():
        instance.SSG[sg] = scenarios
    
    # for (sg, sc), val in probc_dict.items():
    #     instance.probc[sg, sc] = val
    
    # for (sg, sc, t), val in mean_pWc_dict.items():
    #     instance.mean_pWc[sg, sc, t] = val
    
    
    # # Create dictionaries to store computed values
    # meanmax_pVI_RP_dict = {}
    # meanmin_pVI_RP_dict = {}
    # meanmax_pVI_EV_dict = {}
    # meanmin_pVI_EV_dict = {}
    
    # # Compute bounds for pVI deviations in RP and EV problems
    # for i in instance.IM:
    #     for t in instance.TIM[i]:
    #         # Loop over clusters at stage (sgim[i] - 1)
    #         for sc in instance.SSG[instance.sgim[i] - 1]:
    #             sg_stage = instance.sgim[i] - 1
    
    #             # Compute max and min deviations for pW[t,s]
    #             numerator_max = sum(
    #                 value(instance.Prob[s]) * (value(instance.pW[t, s]) - value(instance.mean_pW[t]))
    #                 for s in instance.c[sg_stage, sc]
    #                 if value(instance.pW[t, s]) - value(instance.mean_pW[t]) > 0
    #             )
    #             numerator_min = sum(
    #                 value(instance.Prob[s]) * (value(instance.pW[t, s]) - value(instance.mean_pW[t]))
    #                 for s in instance.c[sg_stage, sc]
    #                 if value(instance.pW[t, s]) - value(instance.mean_pW[t]) < 0
    #             )
    
    #             meanmax = numerator_max / value(instance.probc[sg_stage, sc]) if value(instance.probc[sg_stage, sc]) > 0 else 0.0
    #             meanmin = numerator_min / value(instance.probc[sg_stage, sc]) if value(instance.probc[sg_stage, sc]) > 0 else 0.0
    
    #             # Store computed deviations
    #             for s in instance.c[sg_stage, sc]:
    #                 meanmax_pVI_RP_dict[i, t, s] = meanmax
    #                 meanmin_pVI_RP_dict[i, t, s] = meanmin
    
    #         # Compute and store EV bounds
    #         meanmax_pVI_EV_dict[i, t] = sum(
    #             value(instance.probc[instance.sgim[i] - 1, sc]) * meanmax_pVI_RP_dict[i, t, next(iter(instance.c[instance.sgim[i] - 1, sc]))]
    #             for sc in instance.SSG[instance.sgim[i] - 1]
    #         )
    #         meanmin_pVI_EV_dict[i, t] = sum(
    #             value(instance.probc[instance.sgim[i] - 1, sc]) * meanmin_pVI_RP_dict[i, t, next(iter(instance.c[instance.sgim[i] - 1, sc]))]
    #             for sc in instance.SSG[instance.sgim[i] - 1]
    #         )
    
    # # Store computed values into Pyomo model
    # for (i, t, s), val in meanmax_pVI_RP_dict.items():
    #     instance.meanmax_pVI_RP[i, t, s] = val
    
    # for (i, t, s), val in meanmin_pVI_RP_dict.items():
    #     instance.meanmin_pVI_RP[i, t, s] = val
    
    # for (i, t), val in meanmax_pVI_EV_dict.items():
    #     instance.meanmax_pVI_EV[i, t] = val
    
    # for (i, t), val in meanmin_pVI_EV_dict.items():
    #     instance.meanmin_pVI_EV[i, t] = val

    
    # Create dictionaries to store computed values
    max_pPIB_RP_dict = {}
    max_pNIB_RP_dict = {}
    
    # Compute bounds for imbalance bids
    for t in instance.T:
        for s in instance.S:
            # Compute max_pPIB_RP
            imbalance_p = value(instance.pW[t, s]) + value(instance.pPV[t, s]) - value(instance.mean_pW[t]) - value(instance.mean_pPV[t])
            max_pPIB_RP_dict[t, s] = imbalance_p if imbalance_p >= 0 else 0.0
            
            # Compute max_pNIB_RP
            max_pNIB_RP_dict[t, s] = -imbalance_p if imbalance_p < 0 else 0.0
    
    # Store computed values into Pyomo model
    for (t, s), val in max_pPIB_RP_dict.items():
        instance.max_pPIB_RP[t, s] = val
    
    for (t, s), val in max_pNIB_RP_dict.items():
        instance.max_pNIB_RP[t, s] = val

    # Reset imbalance bounds (PIB_p, PIB_m)
    PIB_p_dict = {}
    PIB_m_dict = {}
    
    # Assign imbalance bounds from max_pPIB_RP and max_pNIB_RP
    for t in instance.T:
        for s in instance.S:
            PIB_p_dict[(t, s)] = value(instance.max_pPIB_RP[t, s])
            PIB_m_dict[(t, s)] = value(instance.max_pNIB_RP[t, s])
    
    # Store computed values in Pyomo model
    for (t, s), val in PIB_p_dict.items():
        instance.PIB_p[t, s] = val
    for (t, s), val in PIB_m_dict.items():
        instance.PIB_m[t, s] = val

    # Dictionaries to hold computed values before assigning to Pyomo
    # lD_dict = {}
    lR_dict = {}
    lI_dict = {}
    # pW_dict = {}
    # pPV_dict = {}
    lIB_dict = {}
    
    # Assign values to dictionaries
    for t in instance.T:
        for s in instance.S:
            # Day-ahead market prices
            # lD_dict[t, s] = value(instance.Scen[t, s])
    
            # Reserve market prices
            lR_dict[t, s] = value(instance.Scen[value(instance.nT) + t, s])
    
            # # Wind power values
            # pW_dict[t, s] = min(value(instance.Scen[value(instance.fRVSG[value(instance.sgpw[t])]), s]), 1.0) * value(instance.Pavg)

            # # Solar PV power values
            # pPV_dict[t, s] = min(value(instance.Scen[value(instance.fRVSG[value(instance.sgpw[t])]) + 1, s]), 1.0) * value(instance.Pavg_PV)
    
            # System imbalance prices
            lIB_dict[t, s] = value(instance.Scen[value(instance.fRVSG[value(instance.nSG)]) + (t - 1), s])
    
    # Assign Intraday Market prices
    for i in instance.IM:
        for t in instance.TIM[i]:
            for s in instance.S:
                lI_dict[i, t, s] = value(instance.Scen[value(instance.fRVSG[value(instance.sgim[i])]) + t - min(instance.TIM[i]), s])
    
    # Store values in Pyomo instance
    # for (t, s), val in lD_dict.items():
    #     instance.lD[t, s] = val
    
    for (t, s), val in lR_dict.items():
        instance.lR[t, s] = val
    
    for (i, t, s), val in lI_dict.items():
        instance.lI[i, t, s] = val
    
    # for (t, s), val in pW_dict.items():
    #     instance.pW[t, s] = val
    
    # for (t, s), val in pPV_dict.items():
    #     instance.pPV[t, s] = val
    
    for (t, s), val in lIB_dict.items():
        instance.lIB[t, s] = val

    # Dictionaries to store computed mean values before assigning to Pyomo
    mean_lD_dict = {}
    mean_lR_dict = {}
    mean_lI_dict = {}
    # mean_pW_dict = {}
    mean_lIB_dict = {}
    
    # Compute mean values
    for t in instance.T:
        mean_lD_dict[t]  = sum(value(instance.Prob[s]) * value(instance.lD[t, s]) for s in instance.S)
        mean_lR_dict[t]  = sum(value(instance.Prob[s]) * value(instance.lR[t, s]) for s in instance.S)
        # mean_pW_dict[t]  = sum(value(instance.Prob[s]) * value(instance.pW[t, s]) for s in instance.S)
        mean_lIB_dict[t] = sum(value(instance.Prob[s]) * value(instance.lIB[t, s]) for s in instance.S)
    
    # Compute mean values for intraday markets
    for i in instance.IM:
        for t in instance.TIM[i]:
            mean_lI_dict[i, t] = sum(value(instance.Prob[s]) * value(instance.lI[i, t, s]) for s in instance.S)
    
    # Store computed values in Pyomo instance
    for t, val in mean_lD_dict.items():
        instance.mean_lD[t] = val
    
    for t, val in mean_lR_dict.items():
        instance.mean_lR[t] = val
    
    for (i, t), val in mean_lI_dict.items():
        instance.mean_lI[i, t] = val
    
    # for t, val in mean_pW_dict.items():
    #     instance.mean_pW[t] = val
    
    for t, val in mean_lIB_dict.items():
        instance.mean_lIB[t] = val
    
    # Compute and display mean values
    mean_lD_avg  = sum(mean_lD_dict[t] for t in instance.T) / value(instance.nT)
    mean_lR_avg  = sum(mean_lR_dict[t] for t in instance.T) / value(instance.nT)
    mean_pW_avg  = sum(mean_pW_dict[t] for t in instance.T) / value(instance.nT)
    mean_lIB_avg = sum(mean_lIB_dict[t] for t in instance.T) / value(instance.nT)
    
    # Print results
    print("\nMean Values:")
    print(f"mean_lD_avg  = {mean_lD_avg:.6f}")
    print(f"mean_lR_avg  = {mean_lR_avg:.6f}")
    print(f"mean_pW_avg  = {mean_pW_avg:.6f}")
    print(f"mean_lIB_avg = {mean_lIB_avg:.6f}")
    
    # Write results to file
    with open(os.path.join("..", pathres, resfile), "a") as res_out:
        res_out.write("\nMean Values:\n")
        res_out.write(f"mean_lD_avg  = {mean_lD_avg:.6f}\n")
        res_out.write(f"mean_lR_avg  = {mean_lR_avg:.6f}\n")
        res_out.write(f"mean_pW_avg  = {mean_pW_avg:.6f}\n")
        res_out.write(f"mean_lIB_avg = {mean_lIB_avg:.6f}\n")
    
    # Compute imbalance prices
    lPIB_dict = {}
    lNIB_dict = {}
                   

    for t in instance.T:
        for s in instance.S:
            lIB_val = value(instance.lIB[t, s])
            lD_val = value(instance.lD[t, s])
    
            if lIB_val <= 1:
                lPIB_dict[(t, s)] = min(180.3, lIB_val * lD_val)
                lNIB_dict[(t, s)] = lD_val
            else:
                lPIB_dict[(t, s)] = lD_val
                lNIB_dict[(t, s)] = min(180.3, lIB_val * lD_val)
    
    # Store computed values in Pyomo model
    for (t, s), val in lPIB_dict.items():
        instance.lPIB[t, s] = val
    for (t, s), val in lNIB_dict.items():
        instance.lNIB[t, s] = val


    # Compute mean values for imbalance prices
    mean_lPIB_dict = {t: sum(value(instance.Prob[s]) * lPIB_dict[(t, s)] for s in instance.S) for t in instance.T}
    mean_lNIB_dict = {t: sum(value(instance.Prob[s]) * lNIB_dict[(t, s)] for s in instance.S) for t in instance.T}
    
    # Store computed values in Pyomo model
    for t, val in mean_lPIB_dict.items():
        instance.mean_lPIB[t] = val
    for t, val in mean_lNIB_dict.items():
        instance.mean_lNIB[t] = val

    # Log the problem
    print("\n\n#EC problem: \n\n")
    with open(os.path.join("..", pathres, resfile), "a") as res_log:
        res_log.write("\n\n#EC problem: \n\n")

    # Display initial conditions
    print("Initial conditions:")
    print(f"SOCini: {value(instance.SOCini)}")
    print(f"sOR: {value(instance.sOR)}")
    
    with open(os.path.join("..", pathres, resfile), "a") as res_log:
        res_log.write("\nInitial conditions:\n")
        res_log.write(f"SOCini: {value(instance.SOCini)}\n")
        res_log.write(f"sOR: {value(instance.sOR)}\n")

    # SOLVER OPTIONS
    solver = SolverFactory("gurobi")  # Use gurobi solver
    
    # Set Gurobi options equivalent to CPLEX settings
    solver.options["MIPGap"] = 0.0001      # Equivalent to mipgap in CPLEX
    solver.options["Threads"] = 4        # Use 4 threads
    solver.options["DisplayInterval"] = 2  # Similar to mipdisplay in CPLEX
    solver.options["Presolve"] = 0       # Equivalent to mipbasis (no presolve)
    solver.options["TimeLimit"] = 3600   # No direct equivalent for "timing", but setting a time limit
    solver.options["Seed"] = 2           # Equivalent to clocktype = 2 (deterministic runs)
    solver.options["Method"] = 3  # Dual simplex (like CPLEX default)
    # # Set CPLEX options
    # solver.options["mipgap"] = 0.01          # Tolerance for integer solutions
    # solver.options["threads"] = 4            # Use 4 threads
    # solver.options["mipdisplay"] = 2         # Display level of MIP logs
    # solver.options["mipbasis"] = 0           # Disable MIP basis
    # solver.options["timing"] = 1             # Enable timing
    # solver.options["clocktype"] = 2          # Use deterministic time

    print("Solving the optimization problem...")
    start_time = time.time()
    
    results = solver.solve(instance, tee=True)  # Solve and print log
    end_time = time.time()
    
    solve_elapsed_time = end_time - start_time  # Compute elapsed time
    print(f"Solve elapsed time: {solve_elapsed_time:.2f} seconds")
    
    print(f"DA Income: {sum(value(instance.Prob[s]) * value(instance.lD[t, s]) * (value(instance.eDA_p[t, s]) - value(instance.eDA_m[t, s])) for t in instance.T for s in instance.S)}")
    print(f"RM Income: {sum(value(instance.Prob[s]) * (value(instance.rD[t, s]) + value(instance.rU[t, s])) * value(instance.lR[t, s]) for t in instance.T for s in instance.S)}")
    print(f"IM Income: {sum(value(instance.Prob[s]) * sum(value(instance.lI[i, t, s]) * value(instance.eIM[i, t, s]) for i in instance.IMT[t]) for t in instance.T for s in instance.S)}")
    print(f"IB Income: {sum(value(instance.Prob[s]) * value(instance.lPIB[t, s]) * value(instance.pIB_p[t, s]) for t in instance.T for s in instance.S)}")
    print(f"IB Costs: {sum(value(instance.Prob[s]) * value(instance.lNIB[t, s]) * value(instance.pIB_m[t, s]) for t in instance.T for s in instance.S)}")
    print(f"FD Costs: {sum(value(instance.Prob[s]) * value(instance.C_FD) * (value(instance.var_afd_p[t, s]) + value(instance.var_afd_m[t, s])) for t in instance.T for s in instance.S)}")

    # for t in instance.T:
    #     for s in instance.S:
    #         print(f"DA Sell UB[{t},{s}] = {value(instance.DA_sell_bid_UB[t,s])}")
    #         print(f"DA Buy UB[{t},{s}] = {value(instance.DA_buy_bid_UB[t,s])}")

    # for t in instance.T:
    #     for s in instance.S:
    #         print(f"RM Upward[{t},{s}] = {value(instance.rU[t,s])}")
    #         print(f"RM Downward[{t},{s}] = {value(instance.rD[t,s])}")
    
    # for t in instance.T:
    #     for s in instance.S:
    #         print(f"RM Upward BESS[{t},{s}] = {value(instance.rU_B[t,s])}")
    #         print(f"RM Upward Flex Demand[{t},{s}] = {value(instance.rU_FD[t,s])}")


    
    def consecutive_scenarios(model, sg, k):
        if (sg, k) not in model.c.index_set():
            return []
        # Sort using the same numeric key!
        scenario_list = sorted([l for l in model.c[sg, k] if l in model.S],
                               key=lambda x: int(x))
        return [(scenario_list[i], scenario_list[i+1]) for i in range(len(scenario_list)-1)]

    
    print(f"\nChecking non-anticipativity for Day {sim}")
    
    # List of all variables in non-anticipativity constraints
    nac_variables = [
        "eDA_p", "eDA_m", "ieDA_p",  # Day-Ahead Market
        "rU", "rU_B", "rU_FD",        # Reserve Market Upward
        "rD", "rD_B", "rD_FD",        # Reserve Market Downward
    ]
    
    # Iterate over all variables
    for var_name in nac_variables:
        if not hasattr(instance, var_name):  # Skip if variable not in model
            print(f"Skipping {var_name} (not found in model)")
            continue
    
        print(f"Checking NAC for {var_name}:")
        var = getattr(instance, var_name)  # Get the variable dynamically
    
        for t in instance.T:
            for k in instance.S0:
                for (l, l_next) in consecutive_scenarios(instance, 1, k):
                    try:
                        diff = abs(value(var[t, l]) - value(var[t, l_next]))
                        if diff > 1e-6:
                            print(f"Non-anticipativity violated: {var_name}[{t}, {l}] ≠ {var_name}[{t}, {l_next}]")
                    except KeyError:
                        print(f"Skipping {var_name}[{t}, {l}] or {var_name}[{t}, {l_next}] due to missing index")
    
    print(f"Checking NAC for pIB_p:")
    for t in instance.T:
        for k in instance.S0:
            sg_for_t = instance.sgpw[t]  # use the same stage as in the constraint
            for (l, l_next) in consecutive_scenarios(instance, sg_for_t, k):
                try:
                    diff = abs(value(instance.pIB_p[t, l]) - value(instance.pIB_p[t, l_next]))
                    if diff > 1e-6:
                        print(f"Non-anticipativity violated: pIB_p[{t}, {l}] ≠ pIB_p[{t}, {l_next}]")
                except KeyError:
                    print(f"Skipping pIB_p[{t}, {l}] or pIB_p[{t}, {l_next}] due to missing index")

    print(f"Checking NAC for pIB_m:")
    for t in instance.T:
        for k in instance.S0:
            sg_for_t = instance.sgpw[t]  # use the same stage as in the constraint
            for (l, l_next) in consecutive_scenarios(instance, sg_for_t, k):
                try:
                    diff = abs(value(instance.pIB_m[t, l]) - value(instance.pIB_m[t, l_next]))
                    if diff > 1e-6:
                        print(f"Non-anticipativity violated: pIB_m[{t}, {l}] ≠ pIB_m[{t}, {l_next}]")
                except KeyError:
                    print(f"Skipping pIB_m[{t}, {l}] or pIB_m[{t}, {l_next}] due to missing index")


    # List of all variables in non-anticipativity constraints
    nac_variables = [
        "var_fd", "var_afd_p", "var_afd_m",  # Flexible Demand
        "dV", "cV", "idV", "socV"     # Battery Energy Storage
    ]
    
    # Iterate over all variables
    for var_name in nac_variables:
        if not hasattr(instance, var_name):  # Skip if variable not in model
            print(f"Skipping {var_name} (not found in model)")
            continue
    
        print(f"Checking NAC for {var_name}:")
        var = getattr(instance, var_name)  # Get the variable dynamically
    
        for t in instance.T:
            for k in instance.S0:
                sg_for_t = instance.sgpw[t] - 1  # use the same stage as in the constraint
                for (l, l_next) in consecutive_scenarios(instance, sg_for_t, k):
                    try:
                        diff = abs(value(var[t, l]) - value(var[t, l_next]))
                        if diff > 1e-6:
                            print(f"Non-anticipativity violated: {var_name}[{t}, {l}] ≠ {var_name}[{t}, {l_next}]")
                    except KeyError:
                        print(f"Skipping {var_name}[{t}, {l}] or {var_name}[{t}, {l_next}] due to missing index")
    

    print(f"Checking NAC for all eIM:")
    # Check nonanticipativity for eIM using the same index logic as in build_nac_eIM_index:
    for i in instance.IM:
        for t in instance.TIM[i]:
            for k in instance.S0:
                sg_for_i = instance.sgim[i] - 1
                for (l, l_next) in consecutive_scenarios(instance, sg_for_i, k):
                    try:
                        diff = abs(value(instance.eIM[i, t, l]) - value(instance.eIM[i, t, l_next]))
                        if diff > 1e-6:
                            print(f"Non-anticipativity violated: eIM[{i}, {t}, {l}] ≠ eIM[{i}, {t}, {l_next}]")
                    except KeyError:
                        print(f"Skipping eIM[{i}, {t}, {l}] or eIM[{i}, {t}, {l_next}] due to missing index")



    # Store results
    print("\n########################")
    print("###### Results #########")
    print("########################\n")
    
    with open(os.path.join("..", pathres, resfile), "a") as res_log:
        res_log.write("\n########################\n")
        res_log.write("###### Results #########\n")
        res_log.write("########################\n\n")
    
        # Store solver results
        res_log.write(f"solve_message: {results.solver.message}\n")
        res_log.write(f"solve_result_num: {results.solver.status}\n")
        res_log.write(f"solve_result: {results.solver.termination_condition}\n")
        res_log.write(f"solve_elapsed_time: {solve_elapsed_time:.2f} seconds\n")
    
    instance.time[probl, sim] = solve_elapsed_time  # Assign elapsed time
    instance.num_scen[probl, sim] = len(instance.S)  # Store scenario count
    # Store elapsed time in dictionary
    solve_time[(probl, sim)] = solve_elapsed_time
    n_scenarios[(probl, sim)] = len(instance.S)
    
    print(f"solve_message: {results.solver.message}")
    print(f"solve_result_num: {results.solver.status}")
    print(f"solve_result: {results.solver.termination_condition}")
    print(f"solve_elapsed_time: {solve_elapsed_time:.2f} seconds")
    # print(f"Number of scenarios: {num_scenarios}")
    
    # Save Flexible Demand Variables
    fd_path = os.path.join("..", pathres, "FD/")
    os.makedirs(fd_path, exist_ok=True)
    
    for filename, var in zip(["var_fd.txt", "var_afd_p.txt", "var_afd_m.txt"], 
                             [instance.var_fd, instance.var_afd_p, instance.var_afd_m]):
        with open(os.path.join(fd_path, filename), "w") as f:
            for s in instance.S:
                for t in instance.T:
                    f.write(f"{s} {value(instance.Prob[s])} {t} {value(var[t, s])}\n")
    
    # Define the FD results directory
    fd_path = os.path.join("..", pathres, "FD/")
    os.makedirs(fd_path, exist_ok=True)
    
    # Store FD parameters and sets
    fd_params_file = os.path.join(fd_path, "FD_params.txt")
    with open(fd_params_file, "w") as f:
        f.write(f"nFI: {value(instance.nFI)}\n")
        f.write(f"FI: {list(instance.FI)}\n")
        
        for t in instance.T:
            f.write(f"FD[{t}]: {value(instance.FD[t])}\n")
            f.write(f"FD_L[{t}]: {value(instance.FD_L[t])}\n")
            f.write(f"FD_U[{t}]: {value(instance.FD_U[t])}\n")
            f.write(f"RUFD[{t}]: {value(instance.RUFD[t])}\n")
            f.write(f"RDFD[{t}]: {value(instance.RDFD[t])}\n")
        
        for f_ in instance.FI:
            f.write(f"TF_L[{f_}]: {value(instance.TF_L[f_])}\n")
            f.write(f"TF_U[{f_}]: {value(instance.TF_U[f_])}\n")
            f.write(f"coef_FD[{f_}]: {value(instance.coef_FD[f_])}\n")
    
        f.write(f"C_FD: {value(instance.C_FD)}\n")
    
    # Define the WP results directory
    wp_path = os.path.join("..", pathres, "WP/")
    os.makedirs(wp_path, exist_ok=True)
    
    # Store WP parameters
    wp_params_file = os.path.join(wp_path, "WP_params.txt")
    with open(wp_params_file, "w") as f:
        f.write("###### Printing Wind Power Plant Sets and Parameters #########\n\n")
        f.write(f"sgpw: {list(instance.sgpw.values())}\n")
        f.write(f"max_pW: {value(instance.max_pW)}\n")
        f.write(f"Pavg: {value(instance.Pavg)}\n")

    # Store pW values for each scenario
    pw_file = os.path.join(wp_path, "pW.txt")
    with open(pw_file, "w") as f:
        for s in instance.S:
            f.write(f"{s} {value(instance.Prob[s])} ")
            for t in instance.T:
                f.write(f"{value(instance.pW[t, s])} ")
            f.write("\n")

    
    # Define the PV results directory
    pv_path = os.path.join("..", pathres, "PV/")
    os.makedirs(pv_path, exist_ok=True)
    
    # Store PV parameters
    pv_params_file = os.path.join(pv_path, "PV_params.txt")
    with open(pv_params_file, "w") as f:
        f.write("###### Printing PV Sets and Parameters #########\n\n")
        f.write("sgpPV = \n")
        
        for t in instance.T:
            f.write(f"{t}: {value(instance.sgpw[t]) + 1}\n")
        
        f.write(f"Pavg_PV: {value(instance.Pavg_PV)}\n")

    # Store pPV values for each scenario
    ppv_file = os.path.join(pv_path, "pPV.txt")
    with open(ppv_file, "w") as f:
        for s in instance.S:
            f.write(f"{s} {value(instance.Prob[s])} ")
            for t in instance.T:
                f.write(f"{value(instance.pPV[t, s])} ")
            f.write("\n")
    
    # Define the BESS results directory
    bess_path = os.path.join("..", pathres, "BESS/")
    os.makedirs(bess_path, exist_ok=True)
    
    # Store BESS parameters
    bess_params_file = os.path.join(bess_path, "BESS_params.txt")
    with open(bess_params_file, "w") as f:
        f.write("###### Printing BESS Parameters and Optimal Variables #########\n\n")
        f.write(f"Emax: {value(instance.Emax)}\n")
        f.write(f"Dmax: {value(instance.Dmax)}\n")
        f.write(f"RTE: {value(instance.RTE)}\n")
        f.write(f"SOCmax: {value(instance.SOCmax)}\n")
        f.write(f"SOCmin: {value(instance.SOCmin)}\n")
        f.write(f"SOCini: {value(instance.SOCini)}\n")
        f.write(f"SOCfin: {value(instance.SOCfin)}\n")
    
    # Define the BESS results directory
    bess_path = os.path.join("..", pathres, "BESS/")
    os.makedirs(bess_path, exist_ok=True)
    
    # Store BESS discharge variable (dV)
    dv_file = os.path.join(bess_path, "dV.txt")
    with open(dv_file, "w") as f:
        for s in instance.S:
            f.write(f"{s} {value(instance.Prob[s])} ")
            for t in instance.T:
                f.write(f"{value(instance.dV[t, s])} ")
            f.write("\n")
    
    # Store BESS charge variable (cV)
    cv_file = os.path.join(bess_path, "cV.txt")
    with open(cv_file, "w") as f:
        for s in instance.S:
            f.write(f"{s} {value(instance.Prob[s])} ")
            for t in instance.T:
                f.write(f"{value(instance.cV[t, s])} ")
            f.write("\n")
    
    # Store BESS binary charge/discharge indicator (idV)
    idv_file = os.path.join(bess_path, "idV.txt")
    with open(idv_file, "w") as f:
        for s in instance.S:
            f.write(f"{s} {value(instance.Prob[s])} ")
            for t in instance.T:
                f.write(f"{value(instance.idV[t, s])} ")
            f.write("\n")
    
    # Store net charge-discharge difference (cV - dV)
    cv_dv_file = os.path.join(bess_path, "cV-dV.txt")
    with open(cv_dv_file, "w") as f:
        for s in instance.S:
            f.write(f"{s} {value(instance.Prob[s])} ")
            for t in instance.T:
                f.write(f"{value(instance.cV[t, s]) - value(instance.dV[t, s])} ")
            f.write("\n")
    
    # Store BESS state of charge (socV)
    socv_file = os.path.join(bess_path, "socV.txt")
    with open(socv_file, "w") as f:
        for s in instance.S:
            f.write(f"{s} {value(instance.Prob[s])} ")
            for t in instance.T0:  # Includes initial state at t=0
                f.write(f"{value(instance.socV[t, s])} ")
            f.write("\n")
    
    # Define the DA results directory
    da_path = os.path.join("..", pathmarketres, "DA/")
    os.makedirs(da_path, exist_ok=True)
    
    # Store DA price data (lD)
    ld_file = os.path.join(da_path, "lD.txt")
    with open(ld_file, "w") as f:
        for s in instance.S:
            f.write(f"{s} {value(instance.Prob[s])} ")
            for t in instance.T:
                f.write(f"{value(instance.lD[t, s])} ")
            f.write("\n")
    
    # Close DA params file (even if not used explicitly, to align with AMPL behavior)
    da_params_file = os.path.join(da_path, "DA_params.txt")
    open(da_params_file, "w").close()

    # Define the DA results directory
    da_path = os.path.join("..", pathmarketres, "DA/")
    os.makedirs(da_path, exist_ok=True)
    
    # Store DA matched energy variables (eDA_p)
    eda_p_file = os.path.join(da_path, "eDA_p.txt")
    with open(eda_p_file, "w") as f:
        for s in instance.S:
            f.write(f"{s} {value(instance.Prob[s])} ")
            for t in instance.T:
                f.write(f"{value(instance.eDA_p[t, s])} ")
            f.write("\n")
    
    # Store DA matched energy variables (eDA_m)
    eda_m_file = os.path.join(da_path, "eDA_m.txt")
    with open(eda_m_file, "w") as f:
        for s in instance.S:
            f.write(f"{s} {value(instance.Prob[s])} ")
            for t in instance.T:
                f.write(f"{value(instance.eDA_m[t, s])} ")
            f.write("\n")
    
    # Store DA matched binary selling variables (ieDA_p)
    ieda_p_file = os.path.join(da_path, "ieDA_p.txt")
    with open(ieda_p_file, "w") as f:
        for s in instance.S:
            f.write(f"{s} {value(instance.Prob[s])} ")
            for t in instance.T:
                f.write(f"{value(instance.ieDA_p[t, s])} ")
            f.write("\n")
    
    # Store DA matched binary buying variables (ieDA_m)
    ieda_m_file = os.path.join(da_path, "ieDA_m.txt")
    with open(ieda_m_file, "w") as f:
        for s in instance.S:
            f.write(f"{s} {value(instance.Prob[s])} ")
            for t in instance.T:
                f.write(f"{value(instance.ieDA_m[t, s])} ")
            f.write("\n")
    
    # Define the RM results directory
    rm_path = os.path.join("..", pathmarketres, "RM/")
    os.makedirs(rm_path, exist_ok=True)
    
    # Store RM price variables (lR)
    lr_file = os.path.join(rm_path, "lR.txt")
    with open(lr_file, "w") as f:
        for s in instance.S:
            f.write(f"{s} {value(instance.Prob[s])} ")
            for t in instance.T:
                f.write(f"{value(instance.lR[t, s])} ")
            f.write("\n")
    
    # Store RM parameter TSR
    rm_params_file = os.path.join(rm_path, "RM_params.txt")
    with open(rm_params_file, "w") as f:
        f.write(f"TSR: {value(instance.TSR)}\n")
    
    # Store Reserve Market Variables
    
    # Define the RM results directory
    rm_path = os.path.join("..", pathmarketres, "RM/")
    os.makedirs(rm_path, exist_ok=True)
    
    # Store RM variable rU[t, s]
    ru_file = os.path.join(rm_path, "rU.txt")
    with open(ru_file, "w") as f:
        for s in instance.S:
            f.write(f"{s} {value(instance.Prob[s])} ")
            for t in instance.T:
                f.write(f"{value(instance.rU[t, s])} ")
            f.write("\n")
    
    # Store RM variable rU_B[t, s]
    ru_b_file = os.path.join(rm_path, "rU_B.txt")
    with open(ru_b_file, "w") as f:
        for s in instance.S:
            f.write(f"{s} {value(instance.Prob[s])} ")
            for t in instance.T:
                f.write(f"{value(instance.rU_B[t, s])} ")
            f.write("\n")
    
    # Store RM variable rU_FD[t, s]
    ru_fd_file = os.path.join(rm_path, "rU_FD.txt")
    with open(ru_fd_file, "w") as f:
        for s in instance.S:
            f.write(f"{s} {value(instance.Prob[s])} ")
            for t in instance.T:
                f.write(f"{value(instance.rU_FD[t, s])} ")
            f.write("\n")
    
    # Store RM variable rD[t, s]
    rd_file = os.path.join(rm_path, "rD.txt")
    with open(rd_file, "w") as f:
        for s in instance.S:
            f.write(f"{s} {value(instance.Prob[s])} ")
            for t in instance.T:
                f.write(f"{value(instance.rD[t, s])} ")
            f.write("\n")
    
    # Store RM variable rD_B[t, s]
    rd_b_file = os.path.join(rm_path, "rD_B.txt")
    with open(rd_b_file, "w") as f:
        for s in instance.S:
            f.write(f"{s} {value(instance.Prob[s])} ")
            for t in instance.T:
                f.write(f"{value(instance.rD_B[t, s])} ")
            f.write("\n")
    
    # Store RM variable rD_FD[t, s]
    rd_fd_file = os.path.join(rm_path, "rD_FD.txt")
    with open(rd_fd_file, "w") as f:
        for s in instance.S:
            f.write(f"{s} {value(instance.Prob[s])} ")
            for t in instance.T:
                f.write(f"{value(instance.rD_FD[t, s])} ")
            f.write("\n")

    # Print header for Intraday Market Parameters
    with open(os.path.join("..", pathmarketres, resfile), "a") as res_log:
        res_log.write("\n###### Printing Intraday Market Parameters and Optimal Variables #########\n\n")
    
    # Define the IM results directory
    im_path = os.path.join("..", pathmarketres, "IM/")
    os.makedirs(im_path, exist_ok=True)
    
    # IM Sets and Parameters (lI values for each i in IM)
    for i in instance.IM:
        li_file = os.path.join(im_path, f"lI_{i}.txt")
        with open(li_file, "w") as f:
            for s in instance.S:
                f.write(f"{s} {value(instance.Prob[s])} ")
                for t in instance.T:
                    if t in instance.TIM[i]:
                        f.write(f"{value(instance.lI[i, t, s])} ")
                    else:
                        f.write("0 ")
                f.write("\n")
    
    # Store IM parameter maxTIM
    im_params_file = os.path.join(im_path, "IM_params.txt")
    with open(im_params_file, "w") as f:
        f.write(f"maxTIM: {value(instance.maxTIM)}\n")
    
    # IM Variables (eIM values for each i in IM)
    for i in instance.IM:
        eim_file = os.path.join(im_path, f"eIM_{i}.txt")
        with open(eim_file, "w") as f:
            for s in instance.S:
                f.write(f"{s} {value(instance.Prob[s])} ")
                for t in instance.T:
                    if t in instance.TIM[i]:
                        f.write(f"{value(instance.eIM[i, t, s])} ")
                    else:
                        f.write("0 ")
                f.write("\n")
    
    # Compute total intraday market energy (eIM_TOT)
    eim_tot_dict = {}
    for t in instance.T:
        for s in instance.S:
            eim_tot_dict[(t, s)] = sum(value(instance.eIM[i, t, s]) for i in instance.IMT[t])
    
    # Store total IM energy (eIM_TOT)
    eim_tot_file = os.path.join(im_path, "eIM_TOT.txt")
    with open(eim_tot_file, "w") as f:
        for s in instance.S:
            f.write(f"{s} {value(instance.Prob[s])} ")
            for t in instance.T:
                f.write(f"{eim_tot_dict[(t, s)]} ")
            f.write("\n")
    
    # Print header for Imbalances Parameters
    with open(os.path.join("..", pathmarketres, resfile), "a") as res_log:
        res_log.write("\n###### Printing Imbalances Parameters and Optimal Variables #########\n\n")
    

    # Define the IB results directory
    ib_path = os.path.join("..", pathmarketres, "IB/")
    os.makedirs(ib_path, exist_ok=True)
    
    # Store IB Parameters (lPIB and lNIB)
    lPIB_file = os.path.join(ib_path, "lPIB.txt")
    with open(lPIB_file, "w") as f:
        for s in instance.S:
            f.write(f"{s} {value(instance.Prob[s])} ")
            for t in instance.T:
                f.write(f"{value(instance.lPIB[t, s])} ")
            f.write("\n")
    
    lNIB_file = os.path.join(ib_path, "lNIB.txt")
    with open(lNIB_file, "w") as f:
        for s in instance.S:
            f.write(f"{s} {value(instance.Prob[s])} ")
            for t in instance.T:
                f.write(f"{value(instance.lNIB[t, s])} ")
            f.write("\n")
    
    # Store IB Variables (pIB_p and pIB_m)
    pIB_p_file = os.path.join(ib_path, "pIB_p.txt")
    with open(pIB_p_file, "w") as f:
        for s in instance.S:
            f.write(f"{s} {value(instance.Prob[s])} ")
            for t in instance.T:
                f.write(f"{value(instance.pIB_p[t, s])} ")
            f.write("\n")
    
    pIB_m_file = os.path.join(ib_path, "pIB_m.txt")
    with open(pIB_m_file, "w") as f:
        for s in instance.S:
            f.write(f"{s} {value(instance.Prob[s])} ")
            for t in instance.T:
                f.write(f"{value(instance.pIB_m[t, s])} ")
            f.write("\n")
    
    # Store IB Net Imbalances (pIB_p - pIB_m)
    pIB_net_file = os.path.join(ib_path, "pIB_p-pIB_m.txt")
    with open(pIB_net_file, "w") as f:
        for s in instance.S:
            f.write(f"{s} {value(instance.Prob[s])} ")
            for t in instance.T:
                pIB_net = value(instance.pIB_p[t, s]) - value(instance.pIB_m[t, s])
                f.write(f"{pIB_net} ")
            f.write("\n")
    
    
    # Print header for Scenarios
    with open(os.path.join("..", pathmarketres, resfile), "a") as res_log:
        res_log.write("\n###### Printing Scenarios #########\n\n")
    
    # Define the Scenarios results directory
    scenarios_path = os.path.join("..", pathmarketres)
    os.makedirs(scenarios_path, exist_ok=True)
    
    # Store Scenarios Data (Scen0)
    scenarios_file = os.path.join(scenarios_path, "scenarios.txt")
    with open(scenarios_file, "w") as f:
        for s in instance.S:
            f.write(f"{s} {value(instance.Prob[s])} ")
            for n in range(1, value(instance.nRV) + 1):
                f.write(f"{value(instance.Scen0[n, s])} ")
            f.write("\n")
    
    # Store Scenario Tree (Clusters)
    tree_file = os.path.join(scenarios_path, "tree.txt")
    with open(tree_file, "w") as f:
        for k in instance.S:
            f.write(f"{k} ")
            for s in instance.SG0:
                for i in instance.S0:
                    # Find the minimum representative scenario `m` in cluster `c[s, i]`
                    cluster_members = [m for m in instance.c[s, i] if m == k]
                    if cluster_members:
                        min_representative = min(instance.c[s, i])
                        f.write(f"{min_representative} ")
            f.write("\n")
    
    # Print header for Objective Function
    with open(os.path.join("..", pathres, resfile), "a") as res_log:
        res_log.write("\n###### Objective Function #########\n\n")
    
    # Define the Objective function results directory
    obj_path = os.path.join("..", pathres, "OBJ/")
    os.makedirs(obj_path, exist_ok=True)

    # Compute Objective Function Components
    obj_fun = value(instance.EECSW)
    
    obj_DA_income = sum(value(instance.Prob[s]) * value(instance.lD[t, s]) * 
        (value(instance.eDA_p[t, s]) - value(instance.eDA_m[t, s]))
        for t in instance.T for s in instance.S)
    
    obj_RM_income = sum(value(instance.Prob[s]) * (value(instance.rD[t, s]) + value(instance.rU[t, s])) * value(instance.lR[t, s])
        for t in instance.T for s in instance.S)
    
    obj_IM_income = sum(value(instance.Prob[s]) * sum(value(instance.lI[i, t, s]) * value(instance.eIM[i, t, s]) for i in instance.IMT[t])
        for t in instance.T for s in instance.S)
    
    obj_IB_income = sum(value(instance.Prob[s]) * value(instance.lPIB[t, s]) * value(instance.pIB_p[t, s])
        for t in instance.T for s in instance.S)
    
    obj_IB_costs = sum(value(instance.Prob[s]) * value(instance.lNIB[t, s]) * value(instance.pIB_m[t, s])
        for t in instance.T for s in instance.S)
    
    obj_IB_net = obj_IB_income - obj_IB_costs
    
    obj_FD_costs = sum(value(instance.Prob[s]) * value(instance.C_FD) * 
        (value(instance.var_afd_p[t, s]) + value(instance.var_afd_m[t, s]))
        for t in instance.T for s in instance.S)

    instance.obj_fun[probl, sim] = obj_fun
    instance.obj_DA_income[probl, sim] = obj_DA_income
    instance.obj_RM_income[probl, sim] = obj_RM_income
    instance.obj_IM_income[probl, sim] = obj_IM_income
    instance.obj_IB_income[probl, sim] = obj_IB_income
    instance.obj_IB_costs[probl, sim] = obj_IB_costs
    instance.obj_IB_net[probl, sim] = obj_IB_net
    instance.obj_FD_costs[probl, sim] = obj_FD_costs

    # Store Objective Function Components
    obj_components = {
        "obj_fun.txt": obj_fun,
        "obj_DA_income.txt": obj_DA_income,
        "obj_RM_income.txt": obj_RM_income,
        "obj_IM_income.txt": obj_IM_income,
        "obj_IB_income.txt": obj_IB_income,
        "obj_IB_costs.txt": obj_IB_costs,
        "obj_IB_net.txt": obj_IB_net,
        "obj_FD_costs.txt": obj_FD_costs,
    }
    
    for filename, obj_val in obj_components.items():
        with open(os.path.join(obj_path, filename), "w") as f:
            f.write(f"{obj_val}\n")
    
    # -------------------------------------------------
    # Next Initial Conditions
    # -------------------------------------------------
    
    # Retrieve the results of the closest scenario as the next starting point
    SOCini_next = value(instance.socV[max(instance.T0), int(value(instance.sOR))])

    # Update the Pyomo model's initial SOC value
    instance.SOCini = SOCini_next
    
    # Log the new initial conditions
    with open(os.path.join("..", pathres, resfile), "a") as res_log:
        res_log.write("\nNew initial conditions:\n")
        res_log.write(f"SOCini: {SOCini_next}\n")
        res_log.write(f"sOR: {value(instance.sOR)}\n")
    
    # Print new initial conditions to console
    print(f"New Initial Conditions:")
    print(f"SOCini: {SOCini_next}, sOR: {value(instance.sOR)}")

    # -------------------------------------------------
    # Print Objective Function and its Components to Results Log
    # -------------------------------------------------
    with open(os.path.join("..", pathres, resfile), "a") as res_log:
        res_log.write("\n#######################################################\n")
        res_log.write(f"Objective Function and its Components {probl}\n")
    
        res_log.write(f"obj_fun = {value(instance.obj_fun[probl, sim]):6.0f}\n")
        res_log.write(f"obj_DA_income = {value(instance.obj_DA_income[probl, sim]):6.0f}\n")
        res_log.write(f"obj_RM_income = {value(instance.obj_RM_income[probl, sim]):6.0f}\n")
        res_log.write(f"obj_IM_income = {value(instance.obj_IM_income[probl, sim]):6.0f}\n")
        res_log.write(f"obj_IB_income = {value(instance.obj_IB_income[probl, sim]):6.0f}\n")
        res_log.write(f"obj_IB_costs = {value(instance.obj_IB_costs[probl, sim]):6.0f}\n")
        res_log.write(f"obj_IB_net = {value(instance.obj_IB_net[probl, sim]):6.0f}\n")
        res_log.write(f"obj_FD_costs = {value(instance.obj_FD_costs[probl, sim]):6.0f}\n")
    
        res_log.write("#######################################################\n")

    obj_results["obj_fun"][sim] = obj_fun
    obj_results["obj_DA_income"][sim] = obj_DA_income
    obj_results["obj_RM_income"][sim] = obj_RM_income
    obj_results["obj_IM_income"][sim] = obj_IM_income
    obj_results["obj_IB_income"][sim] = obj_IB_income
    obj_results["obj_IB_costs"][sim] = obj_IB_costs
    obj_results["obj_IB_net"][sim] = obj_IB_net
    obj_results["obj_FD_costs"][sim] = obj_FD_costs
    
# -------------------------------------------------
# Print Objective Function and Components Summary to Console
# -------------------------------------------------
print("############################################################")
print(f"Benefit/costs problem {probl}")

# Print header with all scenario labels
print("           ", end=" ")
for s in SIMS:
    print(f"{s:>6s}", end=" ")
print("\n")

# Print Objective Function Components
def print_obj_component(name, results_dict):
    print(f"{name + ' =':<15}", end=" ")  # Append '=' to the name
    for s in SIMS:
        print(f"{results_dict[name].get(s, 0):6.0f}", end=" ")
    print("\n")

print_obj_component("obj_fun", obj_results)
print_obj_component("obj_DA_income", obj_results)
print_obj_component("obj_RM_income", obj_results)
print_obj_component("obj_IM_income", obj_results)
print_obj_component("obj_IB_income", obj_results)
print_obj_component("obj_IB_costs", obj_results)
print_obj_component("obj_IB_net", obj_results)
print_obj_component("obj_FD_costs", obj_results)

print("############################################################")


# ---------------------------------------------------------------------------------
# Print solving times
# ---------------------------------------------------------------------------------
print("#" * 80)
print(f"{' ' * 24} Solve elapsed time {probl} =", end=" ")
for sim in SIMS:
    print(f"{solve_time[probl, sim]:7.1f}", end=" ")
print("\n" + "#" * 80)

# ---------------------------------------------------------------------------------
# Print Objective Function and Components in 'results_log.res'
# ---------------------------------------------------------------------------------
with open(os.path.join("..", pathres, resfile), "a") as res_log:
    res_log.write("\n#######################################################\n")
    res_log.write(f"Objective Function and its Components {probl}\n")

    # Retrieve values from obj_results dictionary
    res_log.write(f"obj_fun = {obj_results['obj_fun'].get(sim, 0):.0f}\n")
    res_log.write(f"obj_DA_income = {obj_results['obj_DA_income'].get(sim, 0):.0f}\n")
    res_log.write(f"obj_RM_income = {obj_results['obj_RM_income'].get(sim, 0):.0f}\n")
    res_log.write(f"obj_IM_income = {obj_results['obj_IM_income'].get(sim, 0):.0f}\n")
    res_log.write(f"obj_IB_income = {obj_results['obj_IB_income'].get(sim, 0):.0f}\n")
    res_log.write(f"obj_IB_costs = {obj_results['obj_IB_costs'].get(sim, 0):.0f}\n")
    res_log.write(f"obj_IB_net = {obj_results['obj_IB_net'].get(sim, 0):.0f}\n")
    res_log.write(f"obj_FD_costs = {obj_results['obj_FD_costs'].get(sim, 0):.0f}\n")

    res_log.write("#######################################################\n")

# ---------------------------------------------------------------------------------
# Print Objective Function and Components into profit file (ec_"famscen"_"month".out)
# ---------------------------------------------------------------------------------
# Define the path where summary results are stored
pathtablesres = os.path.join("..", "results", famscen, "tables/")
os.makedirs(pathtablesres, exist_ok=True)  # Ensure the directory exists

profit_file = os.path.join(pathtablesres, profitfile[probl])
with open(profit_file, "w") as f:
    f.write(f"     {probl} ")
    f.write(" ".join([f"{sim:6s}" for sim in SIMS]) + "\n")

    f.write("obj_fun ")
    f.write(" ".join([f"{obj_results['obj_fun'].get(s, 0):6.0f}" for s in SIMS]) + "\n")

    f.write("obj_DA_income ")
    f.write(" ".join([f"{obj_results['obj_DA_income'].get(s, 0):6.0f}" for s in SIMS]) + "\n")

    f.write("obj_RM_income ")
    f.write(" ".join([f"{obj_results['obj_RM_income'].get(s, 0):6.0f}" for s in SIMS]) + "\n")

    f.write("obj_IM_income ")
    f.write(" ".join([f"{obj_results['obj_IM_income'].get(s, 0):6.0f}" for s in SIMS]) + "\n")

    f.write("obj_IB_income ")
    f.write(" ".join([f"{obj_results['obj_IB_income'].get(s, 0):6.0f}" for s in SIMS]) + "\n")

    f.write("obj_IB_costs ")
    f.write(" ".join([f"{obj_results['obj_IB_costs'].get(s, 0):6.0f}" for s in SIMS]) + "\n")

    f.write("obj_IB_net ")
    f.write(" ".join([f"{obj_results['obj_IB_net'].get(s, 0):6.0f}" for s in SIMS]) + "\n")

    f.write("obj_FD_costs ")
    f.write(" ".join([f"{obj_results['obj_FD_costs'].get(s, 0):6.0f}" for s in SIMS]) + "\n")

# ---------------------------------------------------------------------------------
# Print Summary of Computational Time
# ---------------------------------------------------------------------------------
time_file = os.path.join(pathtablesres, timefile[probl])
with open(time_file, "w") as f:
    f.write(f" {probl} ")
    f.write(" ".join([f"{sim:7s}" for sim in SIMS]) + "\n")
    
    f.write("time ")
    f.write(" ".join([f"{solve_time[probl, s]:7.1f}" for s in SIMS]) + "\n")

# ---------------------------------------------------------------------------------
# Print Number of Scenarios File
# ---------------------------------------------------------------------------------
numscen_file = os.path.join(pathtablesres, numscenfile)
with open(numscen_file, "w") as f:
    f.write(f" {probl} ")
    f.write(" ".join([f"{sim:7s}" for sim in SIMS]) + "\n")

    f.write("num scenarios ")
    f.write(" ".join([f"{n_scenarios[probl, s]:7d}" for s in SIMS]) + "\n")


# ---------------------------------------------------------------------------------
# Generate the .out file (equivalent to AMPL output)
# ---------------------------------------------------------------------------------

out_filename = os.path.join("..", "results", famscen, f"ec_{famscen}_summary.out")

with open(out_filename, "w") as out_file:
    # Print and store Objective Function Components
    out_file.write("############################################################\n")
    out_file.write(f"Benefit/costs problem {probl}\n")
    
    # Print header with all scenario labels
    out_file.write("           ")
    for sim in SIMS:
        out_file.write(f"{sim:7s} ")
    out_file.write("\n")

    # Function to write objective function components to file
    def write_obj_component(name, key):
        out_file.write(f"{name:<15}")
        for sim in SIMS:
            out_file.write(f"{obj_results[key].get(sim, 0):6.0f} ")
        out_file.write("\n")

    # Write each objective function component
    write_obj_component("obj_fun", "obj_fun")
    write_obj_component("obj_DA_income", "obj_DA_income")
    write_obj_component("obj_RM_income", "obj_RM_income")
    write_obj_component("obj_IM_income", "obj_IM_income")
    write_obj_component("obj_IB_income", "obj_IB_income")
    write_obj_component("obj_IB_costs", "obj_IB_costs")
    write_obj_component("obj_IB_net", "obj_IB_net")
    write_obj_component("obj_FD_costs", "obj_FD_costs")

    out_file.write("############################################################\n")

    # Solve elapsed times
    out_file.write("#" * 80 + "\n")
    out_file.write(f"{' ' * 24} Solve elapsed time {probl} = ")
    for sim in SIMS:
        out_file.write(f"{solve_time[probl, sim]:7.1f} ")
    out_file.write("\n" + "#" * 80 + "\n")

    # Number of scenarios per simulation
    out_file.write(f"\nNumber of Scenarios ({probl})\n")
    out_file.write("           ")
    for sim in SIMS:
        out_file.write(f"{sim:7s} ")
    out_file.write("\nnum scenarios ")
    for sim in SIMS:
        out_file.write(f"{n_scenarios[probl, sim]:7d} ")
    out_file.write("\n")

    out_file.write("\nEND\n")

print(f"\nSummary .out file saved to: {out_filename}")

print("END")

