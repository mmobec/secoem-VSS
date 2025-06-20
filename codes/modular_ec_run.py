import os
import math
import time
import pyomo.environ as pyo
from pyomo.environ import DataPortal, value, SolverFactory

from ec_model_rm import model as abstract_model  # Your AbstractModel definition
import config_definition as run_config
from instancemanager import InstanceManager
from simulation_summary_writer import SimulationSummaryWriter
from simulation_context import SimulationContext
from preprocessing import PreProcessor
from solver import Solver
from postprocess import PostProcess

def main(market):
    sim_data = []
    for sim in run_config.SIMS:
        # Create Simulationcontext object to store data of each sim
        sim_ctx = SimulationContext(sim=sim, market=market) # market parameter is used in preprocessing to confirm which
                                                          # results are loaded into the model

        # Preprocessing
        preprocessing = PreProcessor(sim_ctx)
        scenario_data = preprocessing.run_preprocessing()
        # Create Instance
        instance_wrapper = InstanceManager(scenario_data, sim_ctx)
        instance_wrapper.compute_instance()

        # Now Solve the problem
        results = Solver(instance_wrapper, sim_ctx).solve()

        # Postprocessing
        postprocess = PostProcess(results, instance_wrapper.instance, sim_ctx)
        postprocess.perform_nac_checks()
        postprocess.store_results()

        # Update initial conditions for next scenario
        instance_wrapper.next_initial_conditions()

        sim_data.append(sim_ctx)

    # Final Summary of all Simulation Runs


    summary_writer = SimulationSummaryWriter(sim_data)
    summary_writer.write_all()


if __name__ == "__main__":
    main("DA")
    main("RM")


