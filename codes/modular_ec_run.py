import os
import math
import time
import pyomo.environ as pyo
from pyomo.environ import DataPortal, value, SolverFactory
from ec_model import model as abstract_model  # Your AbstractModel definition
import run_config
from instancecreator import PrepareInstance

def prepare_scenario_data():
    # Print messages like AMPL:
    print("\n########################")
    print(f"#### Instance {run_config.probl}-{run_config.sim}")
    print("########################\n")

    pathres = f"results/{run_config.famscen}/{run_config.probl}/{run_config.sim}/"
    pathmarketres = f"results/{run_config.famscen}/market/{run_config.sim}/"

    # Ensure pathres and pathmarketres exist before writing files
    os.makedirs(os.path.join("..", pathres), exist_ok=True)
    os.makedirs(os.path.join("..", pathmarketres), exist_ok=True)

    # let scenfile := famscen&"-"&sim&".dat";
    scenfile = f"{run_config.famscen}-{run_config.sim}.dat"
    print(f"scenfile path = {run_config.pathscen}{scenfile}")
    print(f"pathres        = {pathres}")

    # let demfile := "demand-"&sim&".dat";
    demfile = f"demand-{run_config.sim}.dat"
    print(f"demfile path   = {run_config.pathdem}{demfile}")
    print(f"pathres        = {pathres}")

    scenario_data = DataPortal()
    # Load the "base" data
    scenario_data.load(filename=os.path.join("..", "data", run_config.market_datfile), model=abstract_model)
    scenario_data.load(filename=os.path.join("..", "data", run_config.BESS_datfile), model=abstract_model)
    scenario_data.load(filename=os.path.join("..", "data", run_config.wind_datfile), model=abstract_model)

    # Then load scenario & demand data
    scenario_data.load(filename=os.path.join("..", run_config.pathscen, scenfile), model=abstract_model)
    scenario_data.load(filename=os.path.join("..", run_config.pathdem, demfile), model=abstract_model)
    print(f"\nT = {scenario_data['nT']}, nS = {scenario_data['nS']}, nIM = {scenario_data['nIM']}")
    return scenario_data

def preprocess_data(scenario_data):
    "Before creating the instance"
    # Some Data Preprocess needed before creating the instance because these values are used to build sets in model.py, so they must be defined before creating the instance

    ### S and Prob allocation (S is used in a lot of sets definition in ec_model.py, so it must be known before creating the instance, prob is used in the objective function)
    Prob0_raw = scenario_data.data().get("Prob0", {})  # Extract raw probabilities
    # Compute number of preserved scenarios BEFORE creating the instance
    S_preserved = [s for s in Prob0_raw if Prob0_raw[s] > 0]
    Prob_preserved = {s: Prob0_raw[s] for s in S_preserved}
    print(f"Probabilities at Day {run_config.sim}: {Prob_preserved}")
    print(f"Preserved Scenarios (S): {S_preserved}")
    print(f"Sum of Probabilities: {sum(Prob_preserved.values())}")
    # Inject `S_preserved` and `Prob_preserved` into `scenario_data`
    scenario_data.data()["S"] = {None: S_preserved}  # Ensure correct S
    scenario_data.data()["Prob"] = Prob_preserved  # Assign Probabilities correctly

    ### lD allocation (necessary to define Ssd set in ec_model.py which is necessary to build bidding curves)
    # Scen values are needed to define lD values
    Scen0_raw = scenario_data.data().get("Scen0", {})  # Extract full scenario data
    # Compute preserved scenarios BEFORE creating the instance
    Scen_preserved = {}
    nRV_value = sum(scenario_data.data()["nRVSG"].values())
    # Only keep `Scen0` values that belong to preserved scenarios
    for rv in range(1, nRV_value + 1):  # Loop over random variables
        for s in S_preserved:
            Scen_preserved[(rv, s)] = Scen0_raw.get((rv, s), 0.0)  # Default to 0.0 if missing
    # Inject preserved `Scen` values before `create_instance()`
    scenario_data.data()["Scen"] = Scen_preserved
    # Extract `lD` values
    lD_preserved = {}
    for t in range(1, scenario_data["nT"] + 1):  # Iterate over T
        for s in S_preserved:  # Only for preserved scenarios
            lD_preserved[(t, s)] = scenario_data.data().get("Scen", {}).get((t, s), 0.0)  # Default to 0.0 if missing
    scenario_data.data()["lD"] = lD_preserved  # Assign `lD` values
    return scenario_data


def solve_model(instance):
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
    solver.options["MIPGap"] = 0.0001  # Equivalent to mipgap in CPLEX
    solver.options["Threads"] = 4  # Use 4 threads
    solver.options["DisplayInterval"] = 2  # Similar to mipdisplay in CPLEX
    solver.options["Presolve"] = 0  # Equivalent to mipbasis (no presolve)
    solver.options["TimeLimit"] = 3600  # No direct equivalent for "timing", but setting a time limit
    solver.options["Seed"] = 2  # Equivalent to clocktype = 2 (deterministic runs)
    solver.options["Method"] = 3  # Dual simplex (like CPLEX default)

    print("Solving the optimization problem...")
    start_time = time.time()

    results = solver.solve(instance, tee=True)  # Solve and print log
    end_time = time.time()

    solve_elapsed_time = end_time - start_time  # Compute elapsed time
    print(f"Solve elapsed time: {solve_elapsed_time:.2f} seconds")

    print(
        f"DA Income: {sum(value(instance.Prob[s]) * value(instance.lD[t, s]) * (value(instance.eDA_p[t, s]) - value(instance.eDA_m[t, s])) for t in instance.T for s in instance.S)}")
    print(
        f"RM Income: {sum(value(instance.Prob[s]) * (value(instance.rD[t, s]) + value(instance.rU[t, s])) * value(instance.lR[t, s]) for t in instance.T for s in instance.S)}")
    print(
        f"IM Income: {sum(value(instance.Prob[s]) * sum(value(instance.lI[i, t, s]) * value(instance.eIM[i, t, s]) for i in instance.IMT[t]) for t in instance.T for s in instance.S)}")
    print(
        f"IB Income: {sum(value(instance.Prob[s]) * value(instance.lPIB[t, s]) * value(instance.pIB_p[t, s]) for t in instance.T for s in instance.S)}")
    print(
        f"IB Costs: {sum(value(instance.Prob[s]) * value(instance.lNIB[t, s]) * value(instance.pIB_m[t, s]) for t in instance.T for s in instance.S)}")
    print(
        f"FD Costs: {sum(value(instance.Prob[s]) * value(instance.C_FD) * (value(instance.var_afd_p[t, s]) + value(instance.var_afd_m[t, s])) for t in instance.T for s in instance.S)}")


if __name__ == "__main__":
    scenario_data = prepare_scenario_data()
    scenario_data = preprocess_data(scenario_data)
    instance = PrepareInstance(scenario_data)
    instance.compute_instance()
    #Now Solve the problem
    solve_model(instance)

