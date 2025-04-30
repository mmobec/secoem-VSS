from pyomo.environ import DataPortal, value, SolverFactory
import config_definition as config
import os
import time


class Solver:
    def __init__(self, isntance_prep, sim_ctx ):
        self.instance_prep = isntance_prep
        self.sim_ctx = sim_ctx
        self.solver = SolverFactory("gurobi")  # Use gurobi solver
        self.results = None

    def _populate_solver_options(self):
        for k, v in config.SOLVER_OPTIONS.items():
            self.solver.options[k] = v

    def _solve_model(self):
        instance = self.instance_prep.instance
        sc = self.sim_ctx

        print("\n\n#EC problem: \n\n")
        with open(os.path.join("..", sc.pathres, config.resfile), "a") as res_log:
            res_log.write("\n\n#EC problem: \n\n")

        # Display initial conditions
        print("Initial conditions:")
        print(f"SOCini: {value(instance.SOCini)}")
        print(f"sOR: {value(instance.sOR)}")

        with open(os.path.join("..", sc.pathres, config.resfile), "a") as res_log:
            res_log.write("\nInitial conditions:\n")
            res_log.write(f"SOCini: {value(instance.SOCini)}\n")
            res_log.write(f"sOR: {value(instance.sOR)}\n")

        # SOLVER OPTIONS
        solver = SolverFactory("gurobi")  # Use gurobi solver

        # Set Gurobi options equivalent to CPLEX settings

        print("Solving the optimization problem...")
        start_time = time.time()

        self.results = solver.solve(instance, tee=True)  # Solve and print log
        end_time = time.time()

        sc.solve_time = end_time - start_time  # Compute elapsed time
        sc.n_scenarios = len(instance.S)

        print(f"Solve elapsed time: {sc.solve_time:.2f} seconds")

    def solve(self):
        self._populate_solver_options()
        self._solve_model()
        return self.results

