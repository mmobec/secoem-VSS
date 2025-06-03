from pyomo.environ import DataPortal, value, SolverFactory
import config_definition as config
import os
import time
import logging
from pyomo.util.infeasible import (
    log_infeasible_constraints,
    log_infeasible_bounds,
    find_infeasible_constraints,
)
from pyomo.core.expr.visitor import identify_variables
from pyomo.environ import Var, value


class Solver:
    def __init__(self, isntance_prep, sim_ctx ):
        self.instance_prep = isntance_prep
        self.sim_ctx = sim_ctx
        self.solver = SolverFactory("gurobi")  # Use gurobi solver
        self.results = None

    def _populate_solver_options(self):
        for k, v in config.SOLVER_OPTIONS.items():
            self.solver.options[k] = v
        #self.solver.options['PreSolve'] = 0
        #self.solver.options['Aggregate'] = 0
        # Ask Gurobi to compute an IIS if it finds infeasibility
        #self.solver.options['InfUnbdInfo'] = 1
        # Choose a method (1 is more thorough but slower)
        #self.solver.options['IISMethod'] = 1



    def debug_infeasibility(self, init_values=True, tol=1e-6):
        """
        Diagnose infeasibility in a Pyomo model after a failed solve.

        Parameters
        ----------
        model : Pyomo ConcreteModel or Block
            Your model instance.
        init_values : bool
            Whether to assign 0 to all uninitialized variables before checking.
        tol : float
            Feasibility tolerance (default: 1e-6)
        """
        model = self.instance_prep.instance
        print("🔍 Starting infeasibility diagnostics...")

        # Ensure logging is set up
        log = logging.getLogger('pyomo.util.infeasible')
        log.setLevel(logging.INFO)

        # Optional: assign default values to help expression evaluation
        if init_values:
            for v in model.component_data_objects(Var, descend_into=True):
                if v.value is None:
                    v.set_value(0)

        print("\n🔧 Checking infeasible constraints:")
        log_infeasible_constraints(
            model, tol=tol, log_expression=True, log_variables=True
        )

        print("\n🔧 Checking infeasible variable bounds:")
        log_infeasible_bounds(model, tol=tol)

        """
        print("\n🧪 Manually inspecting undefined constraint variables:")
        for c, val, flag in find_infeasible_constraints(model, tol=tol):
            if val is None:
                print(f"⚠️ Constraint {c.name} has unevaluable body")
                for v in identify_variables(c.body, include_fixed=True):
                    print(f"  - Variable {v.name}: value={v.value}")
        """
        print("\n✅ Done. Review the above output for violated constraints or variables.")

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
        solver = self.solver   #SolverFactory("gurobi")  # Use gurobi solver

        # Set Gurobi options equivalent to CPLEX settings

        print("Solving the optimization problem...")
        start_time = time.time()

        self.results = solver.solve(instance, tee=True, symbolic_solver_labels=True)  # Solve and print log
        self.debug_infeasibility()

        end_time = time.time()

        sc.solve_time = end_time - start_time  # Compute elapsed time
        sc.n_scenarios = len(instance.S)

        print(f"Solve elapsed time: {sc.solve_time:.2f} seconds")

    def solve(self):
        self._populate_solver_options()
        self._solve_model()
        return self.results

