import os
import math
import time
import pyomo.environ as pyo
from pyomo.environ import DataPortal, value, SolverFactory

from codes.results_analysis import ResultAnalysis
from ec_model import model as abstract_model  # Your AbstractModel definition
import run_config
from instancecreator import PrepareInstance
from simulation_summary_writer import SimulationSummaryWriter
from simulation_context import SimulationContext

def prepare_scenario_data(sim_ctx):
    # Print messages like AMPL:
    print("\n########################")
    print(f"#### Instance {run_config.probl}-{sim_ctx.sim}")
    print("########################\n")

    print(f"scenfile path = {run_config.pathscen}{sim_ctx.scenfile}")
    print(f"pathres        = {sim_ctx.pathres}")

    print(f"demfile path   = {sim_ctx.pathdem}{sim_ctx.demfile}")
    print(f"pathres        = {sim_ctx.pathres}")

    scenario_data = DataPortal()
    # Load the "base" data
    scenario_data.load(filename=os.path.join("..", "data", run_config.market_datfile), model=abstract_model)
    scenario_data.load(filename=os.path.join("..", "data", run_config.BESS_datfile), model=abstract_model)
    scenario_data.load(filename=os.path.join("..", "data", run_config.wind_datfile), model=abstract_model)

    # Then load scenario & demand data
    scenario_data.load(filename=os.path.join("..", run_config.pathscen, sim_ctx.scenfile), model=abstract_model)
    scenario_data.load(filename=os.path.join("..", run_config.pathdem, sim_ctx.demfile), model=abstract_model)
    print(f"\nT = {scenario_data['nT']}, nS = {scenario_data['nS']}, nIM = {scenario_data['nIM']}")
    return scenario_data

def preprocess_data(scenario_data, sim_ctx):
    "Before creating the instance"
    # Some Data Preprocess needed before creating the instance because these values are used to build sets in model.py, so they must be defined before creating the instance

    ### S and Prob allocation (S is used in a lot of sets definition in ec_model.py, so it must be known before creating the instance, prob is used in the objective function)
    Prob0_raw = scenario_data.data().get("Prob0", {})  # Extract raw probabilities
    # Compute number of preserved scenarios BEFORE creating the instance
    S_preserved = [s for s in Prob0_raw if Prob0_raw[s] > 0]
    Prob_preserved = {s: Prob0_raw[s] for s in S_preserved}
    print(f"Probabilities at Day {sim_ctx.sim}: {Prob_preserved}")
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


def solve_model(instance_prep, sim_ctx):
    instance = instance_prep.instance
    print("\n\n#EC problem: \n\n")
    with open(os.path.join("..", sim_ctx.pathres, run_config.resfile), "a") as res_log:
        res_log.write("\n\n#EC problem: \n\n")

    # Display initial conditions
    print("Initial conditions:")
    print(f"SOCini: {value(instance.SOCini)}")
    print(f"sOR: {value(instance.sOR)}")

    with open(os.path.join("..", sim_ctx.pathres, run_config.resfile), "a") as res_log:
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

    sim_ctx.solve_time = end_time - start_time  # Compute elapsed time
    sim_ctx.n_scenarios = len(instance_prep.instance.S)
    print(f"Solve elapsed time: {sim_ctx.solve_time:.2f} seconds")

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
    return results

def next_initial_conditions(instance, sim_ctx):
    # -------------------------------------------------
    # Next Initial Conditions
    # -------------------------------------------------

    # Retrieve the results of the closest scenario as the next starting point
    SOCini_next = value(instance.socV[max(instance.T0), int(value(instance.sOR))])

    # Update the Pyomo model's initial SOC value
    instance.SOCini = SOCini_next

    # Log the new initial conditions
    with open(os.path.join("..", sim_ctx.pathres, run_config.resfile), "a") as res_log:
        res_log.write("\nNew initial conditions:\n")
        res_log.write(f"SOCini: {SOCini_next}\n")
        res_log.write(f"sOR: {value(instance.sOR)}\n")

    # Print new initial conditions to console
    print(f"New Initial Conditions:")
    print(f"SOCini: {SOCini_next}, sOR: {value(instance.sOR)}")


if __name__ == "__main__":

    sim_data = []
    for sim in run_config.SIMS:
        sim_ctx = SimulationContext(
            sim=sim,
            famscen=run_config.famscen,
            probl=run_config.probl,
            pathscen=run_config.pathscen,
            pathdem=run_config.pathdem,
            profitfile=run_config.profitfile,
            timefile=run_config.timefile,
            numscenfile=run_config.numscenfile
        )
        scenario_data = prepare_scenario_data(sim_ctx)
        scenario_data = preprocess_data(scenario_data, sim_ctx)
        instance_prep = PrepareInstance(scenario_data, sim_ctx)
        instance_prep.compute_instance()
        #Now Solve the problem
        result = solve_model(instance_prep, sim_ctx)
        #results analysis
        result_analysis = ResultAnalysis(result, instance_prep.instance, sim_ctx)
        result_analysis.perform_nac_checks()
        result_analysis.store_results()

        next_initial_conditions(instance_prep.instance, sim_ctx)
        sim_data.append(sim_ctx)


summary_writer = SimulationSummaryWriter(sim_data)

summary_writer.write_all()
