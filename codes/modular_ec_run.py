import config_definition as run_config
from instancemanager import InstanceManager
from simulation_summary_writer import SimulationSummaryWriter
from simulation_context import SimulationContext
from preprocessing import PreProcessor
from solver import Solver
from postprocess import PostProcess
import multiprocessing as mp



def run_day(sim, market, hydro = False):
        # Create Simulationcontext object to store data of each sim
        sim_ctx = SimulationContext(sim=sim, market=market, include_hydro = hydro) # market parameter is used in preprocessing to confirm which
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

        return sim_ctx


def main(market, hydro=False):
    sim_data = []

    with mp.Pool(processes=64) as pool:  # choose a sensible number
        sim_data = pool.starmap(
            run_day,
            [(sim, market, hydro) for sim in run_config.SIMS]
        )

    # Final Summary of all Simulation Runs


    summary_writer = SimulationSummaryWriter(sim_data)
    summary_writer.write_all()


if __name__ == "__main__":

    #for i in run_config.SIMS:
    #     result = run_day(i, "RM")
    #run_day("002", "EMS")
    #main("EMS")
    #main("DA", hydro = True)
    run_day("001", "DA", hydro= False)
    main("DA")
    main("RM")
    main("IM1")
    main("IM2")
    main("IM3")
