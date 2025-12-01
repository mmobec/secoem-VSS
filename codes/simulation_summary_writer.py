import os
from config_definition import probl, profitfile, timefile, numscenfile, resfile, famscen_all, PROJECT_ROOT


class SimulationSummaryWriter:
    def __init__(self, sim_contexts):
        self.sim_contexts = sim_contexts  # List of SimulationContext objects

    def print_console_summary(self):
        print("############################################################")
        print(f"Benefit/costs problem {probl}")

        print("           ", end=" ")
        for ctx in self.sim_contexts:
            print(f"{ctx.sim:>6s}", end=" ")
        print("\n")

        # Get keys from first sim context (assumed same structure)
        keys = list(self.sim_contexts[0].obj_results.keys())
        for key in keys:
            print(f"{key + ' =':<15}", end=" ")
            for ctx in self.sim_contexts:
                print(f"{ctx.obj_results[key]:6.0f}", end=" ")
            print("\n")

        print("############################################################")
        print("#" * 80)
        print(f"{' ' * 24} Solve elapsed time {probl} =", end=" ")
        for ctx in self.sim_contexts:
            print(f"{ctx.solve_time:7.1f}", end=" ")
        print("\n" + "#" * 80)

    def write_results_log(self):
        log_path = os.path.join(PROJECT_ROOT, self.sim_contexts[-1].pathres, resfile)
        with open(log_path, "a") as res_log:
            res_log.write("\n#######################################################\n")
            res_log.write(f"Objective Function and its Components {probl}\n")
            keys = list(self.sim_contexts[0].obj_results.keys())
            for key in keys:
                res_log.write(f"{key} = {self.sim_contexts[-1].obj_results[key]:.0f}\n")
            res_log.write("#######################################################\n")

    def write_profit_file(self):
        table_path = os.path.join(PROJECT_ROOT, "results", famscen_all,self.sim_contexts[0].market, "tables/")
        os.makedirs(table_path, exist_ok=True)
        filepath = os.path.join(table_path, profitfile[probl])

        with open(filepath, "w") as f:
            f.write(f"     {probl} ")
            f.write(" ".join([f"{ctx.sim:6s}" for ctx in self.sim_contexts]) + "\n")

            keys = list(self.sim_contexts[0].obj_results.keys())
            for key in keys:
                f.write(f"{key} ")
                f.write(" ".join([f"{ctx.obj_results[key]:6.0f}" for ctx in self.sim_contexts]) + "\n")

    def write_time_file(self):
        table_path = os.path.join(PROJECT_ROOT, "results", famscen_all,self.sim_contexts[0].market, "tables/")
        filepath = os.path.join(table_path, timefile[probl])

        with open(filepath, "w") as f:
            f.write(f" {probl} ")
            f.write(" ".join([f"{ctx.sim:7s}" for ctx in self.sim_contexts]) + "\n")
            f.write("time ")
            f.write(" ".join([f"{ctx.solve_time:7.1f}" for ctx in self.sim_contexts]) + "\n")

    def write_num_scen_file(self):
        table_path = os.path.join(PROJECT_ROOT, "results", famscen_all,self.sim_contexts[0].market, "tables/")
        filepath = os.path.join(table_path, numscenfile)

        with open(filepath, "w") as f:
            f.write(f" {probl} ")
            f.write(" ".join([f"{ctx.sim:7s}" for ctx in self.sim_contexts]) + "\n")
            f.write("num scenarios ")
            f.write(" ".join([f"{ctx.n_scenarios:7d}" for ctx in self.sim_contexts]) + "\n")

    def write_out_file(self):
        out_file = os.path.join(PROJECT_ROOT, "results", famscen_all,self.sim_contexts[0].market, f"ec_{famscen_all}_summary.out")

        with open(out_file, "w") as f:
            f.write("############################################################\n")
            f.write(f"Benefit/costs problem {probl}\n")
            f.write("           ")
            for ctx in self.sim_contexts:
                f.write(f"{ctx.sim:7s} ")
            f.write("\n")

            keys = list(self.sim_contexts[0].obj_results.keys())
            for key in keys:
                f.write(f"{key:<15}")
                for ctx in self.sim_contexts:
                    f.write(f"{ctx.obj_results[key]:6.0f} ")
                f.write("\n")

            f.write("############################################################\n")
            f.write("#" * 80 + "\n")
            f.write(f"{' ' * 24} Solve elapsed time {probl} = ")
            for ctx in self.sim_contexts:
                f.write(f"{ctx.solve_time:7.1f} ")
            f.write("\n" + "#" * 80 + "\n")

            f.write(f"\nNumber of Scenarios ({probl})\n")
            f.write("           ")
            for ctx in self.sim_contexts:
                f.write(f"{ctx.sim:7s} ")
            f.write("\nnum scenarios ")
            for ctx in self.sim_contexts:
                f.write(f"{ctx.n_scenarios:7d} ")
            f.write("\nEND\n")

        print(f"\nSummary .out file saved to: {out_file}")
        print("END")

    def write_all(self):
        self.print_console_summary()
        self.write_results_log()
        self.write_profit_file()
        self.write_time_file()
        self.write_num_scen_file()
        self.write_out_file()
