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
        scenario_data, model = preprocessing.run_preprocessing()
        # Create Instance
        instance_wrapper = InstanceManager(scenario_data, sim_ctx, model)
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
    #main("DA")
    #main("RM")

    #ToDo: for IM3: these have to be fixed: discharges, charges, flex. demand -> think about how the first 12 hours
    # of the  IM3 can be fixed

    main("IM1")
    # ToDO: How do we decide how much reserve energy is demanded by the market after clearing?
    # I uncommented the IM constraints, but changed the cap on the amount that can be traded in IM, otherwise
    # the model is unbounded.


    #main("IM2")
    #main("IM3")
    #ToDo: Copare the results of this with the models separate and see if they are the same

