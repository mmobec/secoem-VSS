import os
import run_config

class SimulationSummaryWriter:
    def __init__(self, sim_contexts):
        self.sim_contexts = sim_contexts

    def print_console_summary(self):
        print("############################################################")
        print(f"Benefit/costs problem {self.probl}")

        print("           ", end=" ")
        for sim in self.sims:
            print(f"{sim:>6s}", end=" ")
        print("\n")

        def print_component(name):
            print(f"{name + ' =':<15}", end=" ")
            for sim in self.sims:
                print(f"{self.obj_results[name].get(sim, 0):6.0f}", end=" ")
            print("\n")

        for key in self.obj_results:
            print_component(key)

        print("############################################################")

        print("#" * 80)
        print(f"{' ' * 24} Solve elapsed time {self.probl} =", end=" ")
        for sim in self.sims:
            print(f"{self.solve_time[self.probl, sim]:7.1f}", end=" ")
        print("\n" + "#" * 80)

    def write_results_log(self):
        with open(os.path.join("..", self.pathres, self.resfile), "a") as res_log:
            res_log.write("\n#######################################################\n")
            res_log.write(f"Objective Function and its Components {self.probl}\n")
            for key in self.obj_results:
                res_log.write(f"{key} = {self.obj_results[key].get(self.sims[0], 0):.0f}\n")
            res_log.write("#######################################################\n")

    def write_profit_file(self):
        path = os.path.join("..", "results", self.famscen, "tables/")
        os.makedirs(path, exist_ok=True)

        profit_path = os.path.join(path, self.profitfile[self.probl])
        with open(profit_path, "w") as f:
            f.write(f"     {self.probl} ")
            f.write(" ".join([f"{sim:6s}" for sim in self.sims]) + "\n")

            for key in self.obj_results:
                f.write(f"{key} ")
                f.write(" ".join([f"{self.obj_results[key].get(sim, 0):6.0f}" for sim in self.sims]) + "\n")

    def write_time_file(self):
        path = os.path.join("..", "results", self.famscen, "tables/")
        time_path = os.path.join(path, self.timefile[self.probl])
        with open(time_path, "w") as f:
            f.write(f" {self.probl} ")
            f.write(" ".join([f"{sim:7s}" for sim in self.sims]) + "\n")

            f.write("time ")
            f.write(" ".join([f"{self.solve_time[self.probl, sim]:7.1f}" for sim in self.sims]) + "\n")

    def write_num_scen_file(self):
        path = os.path.join("..", "results", self.famscen, "tables/")
        scen_path = os.path.join(path, self.numscenfile)
        with open(scen_path, "w") as f:
            f.write(f" {self.probl} ")
            f.write(" ".join([f"{sim:7s}" for sim in self.sims]) + "\n")

            f.write("num scenarios ")
            f.write(" ".join([f"{self.n_scenarios[self.probl, sim]:7d}" for sim in self.sims]) + "\n")

    def write_out_file(self):
        out_path = os.path.join("..", "results", self.famscen, f"ec_{self.famscen}_summary.out")
        with open(out_path, "w") as f:
            f.write("############################################################\n")
            f.write(f"Benefit/costs problem {self.probl}\n")
            f.write("           ")
            for sim in self.sims:
                f.write(f"{sim:7s} ")
            f.write("\n")

            for key in self.obj_results:
                f.write(f"{key:<15}")
                for sim in self.sims:
                    f.write(f"{self.obj_results[key].get(sim, 0):6.0f} ")
                f.write("\n")

            f.write("############################################################\n")

            f.write("#" * 80 + "\n")
            f.write(f"{' ' * 24} Solve elapsed time {self.probl} = ")
            for sim in self.sims:
                f.write(f"{self.solve_time[self.probl, sim]:7.1f} ")
            f.write("\n" + "#" * 80 + "\n")

            f.write(f"\nNumber of Scenarios ({self.probl})\n")
            f.write("           ")
            for sim in self.sims:
                f.write(f"{sim:7s} ")
            f.write("\nnum scenarios ")
            for sim in self.sims:
                f.write(f"{self.n_scenarios[self.probl, sim]:7d} ")
            f.write("\n")

            f.write("\nEND\n")

        print(f"\nSummary .out file saved to: {out_path}")
        print("END")

    def write_all(self):
        self.print_console_summary()
        self.write_results_log()
        self.write_profit_file()
        self.write_time_file()
        self.write_num_scen_file()
        self.write_out_file()
