from pyomo.environ import DataPortal, value, SolverFactory
import os
import config_definition as run_config
import matplotlib.pyplot as plt
from numpy import cumsum, array
import pyomo.environ as pyo


class PostProcess:

    def __init__(self, results, instance, sim_ctx):
        self.results = results
        self.instance = instance
        self.sim_ctx = sim_ctx

    @staticmethod
    def consecutive_scenarios(model, sg, k):
        if (sg, k) not in model.c.index_set():
            return []
        # Sort using the same numeric key!
        scenario_list = sorted([l for l in model.c[sg, k] if l in model.S],
                               key=lambda x: int(x))
        return [(scenario_list[i], scenario_list[i + 1]) for i in range(len(scenario_list) - 1)]

    def nac_DAM_and_RM(self):
        # List of all variables in non-anticipativity constraints
        nac_variables = {
            "DA": ["eDA_p", "eDA_m", "ieDA_p",  # Day-Ahead Market
            "rU", "rU_B", "rU_FD",  # Reserve Market Upward
            "rD", "rD_B", "rD_FD"],  # Reserve Market Downward
            "RM": ["rU", "rU_B", "rU_FD",
            "rD", "rD_B", "rD_FD"]  #ToDo: for IM: IM1: ..
        }
        # Iterate over all variables
        for var_name in nac_variables.get(self.sim_ctx.market.upper(), []):
            if not hasattr(self.instance, var_name):  # Skip if variable not in model
                print(f"Skipping {var_name} (not found in model)")
                continue

            print(f"Checking NAC for {var_name} at market {self.sim_ctx.market}:")
            var = getattr(self.instance, var_name)  # Get the variable dynamically

            for t in self.instance.T:
                for q in self.instance.Q:
                    for k in self.instance.S0:
                        for (l, l_next) in self.consecutive_scenarios(self.instance, 1, k): #ToDo: sg needs to change depending on the market run
                            try:
                                diff = abs(value(var[t, q, l]) - value(var[t, q, l_next]))
                                if diff > 1e-6:
                                    print(f"Non-anticipativity violated: {var_name}[{t}, {q}, {l}] ≠ {var_name}[{t}, {q}, {l_next}]")
                            except KeyError:
                                print(f"Skipping {var_name}[{t}, {q}, {l}] or {var_name}[{t}, {q}, {l_next}] due to missing index")

        print(f"Checking NAC for pIB_p:")
        for t in self.instance.T:
            for q in self.instance.Q:
                for k in self.instance.S0:
                    sg_for_t = self.instance.sgpw[t]  # use the same stage as in the constraint
                    for (l, l_next) in self.consecutive_scenarios(self.instance, sg_for_t, k):
                        try:
                            diff = abs(value(self.instance.pIB_p[t, q, l]) - value(self.instance.pIB_p[t, q, l_next]))
                            if diff > 1e-6:
                                print(f"Non-anticipativity violated: pIB_p[{t}, {q}, {l}] ≠ pIB_p[{t}, {q}, {l_next}]")
                        except KeyError:
                            print(f"Skipping pIB_p[{t}, {q}, {l}] or pIB_p[{t}, {q}, {l_next}] due to missing index")

        print(f"Checking NAC for pIB_m:")
        for t in self.instance.T:
            for q in self.instance.Q:
                for k in self.instance.S0:
                    sg_for_t = self.instance.sgpw[t]  # use the same stage as in the constraint
                    for (l, l_next) in self.consecutive_scenarios(self.instance, sg_for_t, k):
                        try:
                            diff = abs(value(self.instance.pIB_m[t, q, l]) - value(self.instance.pIB_m[t, q, l_next]))
                            if diff > 1e-6:
                                print(f"Non-anticipativity violated: pIB_m[{t}, {q}, {l}] ≠ pIB_m[{t}, {q}, {l_next}]")
                        except KeyError:
                            print(f"Skipping pIB_m[{t}, {q}, {l}] or pIB_m[{t}, {q}, {l_next}] due to missing index")

    def nac_demand_and_battery(self):
        # List of all variables in non-anticipativity constraints
        nac_variables = [
            "var_fd", "var_afd_p", "var_afd_m",  # Flexible Demand
            "dV", "cV", "idV", "socV"  # Battery Energy Storage
        ]

        # Iterate over all variables
        for var_name in nac_variables:
            if not hasattr(self.instance, var_name):  # Skip if variable not in model
                print(f"Skipping {var_name} (not found in model)")
                continue

            print(f"Checking NAC for {var_name}:")
            var = getattr(self.instance, var_name)  # Get the variable dynamically

            for t in self.instance.T:
                for q in self.instance.Q:
                    for k in self.instance.S0:
                        sg_for_t = self.instance.sgpw[t] - 1  # use the same stage as in the constraint
                        for (l, l_next) in self.consecutive_scenarios(self.instance, sg_for_t, k):
                            try:
                                diff = abs(value(var[t, q, l]) - value(var[t, q, l_next]))
                                if diff > 1e-6:
                                    print(f"Non-anticipativity violated: {var_name}[{t}, {q}, {l}] ≠ {var_name}[{t}, {q}, {l_next}]")
                            except KeyError:
                                print(f"Skipping {var_name}[{t}, {q}, {l}] or {var_name}[{t}, {q}, {l_next}] due to missing index")

        print(f"Checking NAC for all eIM:")
        # Check nonanticipativity for eIM using the same index logic as in build_nac_eIM_index:
        for i in self.instance.IM:
            for t in self.instance.TIM[i]:
                for q in self.instance.Q:
                    for k in self.instance.S0:
                        sg_for_i = self.instance.sgim[i] - 1
                        for (l, l_next) in self.consecutive_scenarios(self.instance, sg_for_i, k):
                            try:
                                diff = abs(value(self.instance.eIM[i, t, q, l]) - value(self.instance.eIM[i, t, q, l_next]))
                                if diff > 1e-6:
                                    print(f"Non-anticipativity violated: eIM[{i}, {t}, {q}, {l}] ≠ eIM[{i}, {t}, {q}, {l_next}]")
                            except KeyError:
                                print(f"Skipping eIM[{i}, {t}, {q}, {l}] or eIM[{i}, {t}, {q}, {l_next}] due to missing index")

    def save_ts_variable_group(self, output_dir, var_info_list, t_set=None, header=None):
        """
        Generic method to save a group of (t, q, s)-indexed variables to individual files.

        Args:
            output_dir (str): Directory to save files into.
            var_info_list (list): List of (filename, variable) tuples.
            t_set (iterable): Optional set to use instead of self.instance.T.
            header (str): Optional header string to write at top of each file.
        """
        os.makedirs(output_dir, exist_ok=True)
        t_set = t_set if t_set is not None else self.instance.T

        for filename, var in var_info_list:
            file_path = os.path.join(output_dir, filename)
            with open(file_path, "w") as f:
                if header:
                    f.write(header + "\n\n")
                for s in self.instance.S:
                    f.write(f"{s} {value(self.instance.Prob[s])} ")
                    for t in t_set:
                        for q in self.instance.Q:
                            try:
                                f.write(f"{value(var[t, q, s])} ")
                            except KeyError:
                                f.write("0 ")  # fallback if variable missing
                    f.write("\n")

    def print_ampl_console_output(self):
        # Store results
        print("\n########################")
        print("###### Results #########")
        print("########################\n")
        with open(os.path.join(run_config.PROJECT_ROOT, "results",self.sim_ctx.pathres, run_config.resfile), "a") as res_log:
            res_log.write("\n########################\n")
            res_log.write("###### Results #########\n")
            res_log.write("########################\n\n")

            # Store solver results
            res_log.write(f"solve_message: {self.results.solver.message}\n")
            res_log.write(f"solve_result_num: {self.results.solver.status}\n")
            res_log.write(f"solve_result: {self.results.solver.termination_condition}\n")
            res_log.write(f"solve_elapsed_time: {self.sim_ctx.solve_time:.2f} seconds\n")


        self.instance.time[run_config.probl, self.sim_ctx.sim] = self.sim_ctx.solve_time  # Assign elapsed time
        self.instance.num_scen[run_config.probl, self.sim_ctx.sim] = len(self.instance.S)  # Store scenario count
        # Store elapsed time in dictionary

        #This is now done in solve_model
        #self.sim_ctx.solve_time[(run_config.probl, self.sim_ctx.sim)] = self.sim_ctx.solve_time
        #self.sim_ctx.n_scenarios[(run_config.probl, self.sim_ctx.sim)] = len(self.instance.S)


        """
        print(f"solve_message: {results.solver.message}")
        print(f"solve_result_num: {results.solver.status}")
        print(f"solve_result: {results.solver.termination_condition}")
        print(f"solve_elapsed_time: {solve_elapsed_time:.2f} seconds")
        # print(f"Number of scenarios: {num_scenarios}")
        """

    def store_flex_demand_vars(self):

        # Save Flexible Demand Variables
        fd_path = os.path.join(run_config.PROJECT_ROOT, "results", self.sim_ctx.pathres, "FD/")
        os.makedirs(fd_path, exist_ok=True)

        """

        for filename, var in zip(["var_fd.txt", "var_afd_p.txt", "var_afd_m.txt"],
                                 [self.instance.var_fd, self.instance.var_afd_p, self.instance.var_afd_m]):
            with open(os.path.join(fd_path, filename), "w") as f:
                for s in self.instance.S:
                    for t in self.instance.T:
                        f.write(f"{s} {value(self.instance.Prob[s])} {t} {value(var[t, s])}\n")
        """
        fd_vars = [
            ("var_fd.txt", self.instance.var_fd),
            ("var_afd_p.txt", self.instance.var_afd_p),
            ("var_afd_m.txt", self.instance.var_afd_m),
        ]
        self.save_ts_variable_group(fd_path,fd_vars)
        # Store FD parameters and sets
        fd_params_file = os.path.join(fd_path, "FD_params.txt")
        with open(fd_params_file, "w") as f:
            f.write(f"nFI: {value(self.instance.nFI)}\n")
            f.write(f"FI: {list(self.instance.FI)}\n")

            for t in self.instance.T:
                for q in self.instance.Q:
                    f.write(f"FD[{t},{q}]: {value(self.instance.FD[t, q])}\n")
                    f.write(f"FD_L[{t},{q}]: {value(self.instance.FD_L[t, q])}\n")
                    f.write(f"FD_U[{t},{q}]: {value(self.instance.FD_U[t, q])}\n")
                    f.write(f"RUFD[{t},{q}]: {value(self.instance.RUFD[t, q])}\n")
                    f.write(f"RDFD[{t},{q}]: {value(self.instance.RDFD[t, q])}\n")


            for f_ in self.instance.FI:
                f.write(f"TF_L[{f_}]: {value(self.instance.TF_L[f_])}\n")
                f.write(f"TF_U[{f_}]: {value(self.instance.TF_U[f_])}\n")
                f.write(f"coef_FD[{f_}]: {value(self.instance.coef_FD[f_])}\n")

            f.write(f"C_FD: {value(self.instance.C_FD)}\n")

    def store_wind_power(self):
        # Define the WP results directory
        wp_path = os.path.join(run_config.PROJECT_ROOT, "results", self.sim_ctx.pathres, "WP/")
        os.makedirs(wp_path, exist_ok=True)

        # Store WP parameters
        wp_params_file = os.path.join(wp_path, "WP_params.txt")
        with open(wp_params_file, "w") as f:
            f.write("###### Printing Wind Power Plant Sets and Parameters #########\n\n")
            f.write(f"sgpw: {list(self.instance.sgpw.values())}\n")
            f.write(f"max_pW: {value(self.instance.max_pW)}\n")
            f.write(f"Pavg: {value(self.instance.Pavg)}\n")

        # Store pW values for each scenario
        pw_file = os.path.join(wp_path, "pW.txt")
        with open(pw_file, "w") as f:
            for s in self.instance.S:
                f.write(f"{s} {value(self.instance.Prob[s])} ")
                for t in self.instance.T:
                    for q in self.instance.Q:
                        f.write(f"{value(self.instance.pW[t, q, s])} ")
                f.write("\n")


    def store_pv(self):
        # Define the PV results directory
        pv_path = os.path.join(run_config.PROJECT_ROOT, "results", self.sim_ctx.pathres, "PV/")
        os.makedirs(pv_path, exist_ok=True)

        # Store PV parameters
        pv_params_file = os.path.join(pv_path, "PV_params.txt")
        with open(pv_params_file, "w") as f:
            f.write("###### Printing PV Sets and Parameters #########\n\n")
            f.write("sgpPV = \n")

            for t in self.instance.T:
                f.write(f"{t}: {value(self.instance.sgpw[t]) + 1}\n")

            f.write(f"Pavg_PV: {value(self.instance.Pavg_PV)}\n")

        # Store pPV values for each scenario
        ppv_file = os.path.join(pv_path, "pPV.txt")
        with open(ppv_file, "w") as f:
            for s in self.instance.S:
                f.write(f"{s} {value(self.instance.Prob[s])} ")
                for t in self.instance.T:
                    for q in self.instance.Q:
                        f.write(f"{value(self.instance.pPV[t, q, s])} ")
                f.write("\n")

    def store_bess(self):
        bess_path = os.path.join(run_config.PROJECT_ROOT, "results", self.sim_ctx.pathres, "BESS/")
        os.makedirs(bess_path, exist_ok=True)

        # Save BESS parameters
        with open(os.path.join(bess_path, "BESS_params.txt"), "w") as f:
            f.write("###### Printing BESS Parameters and Optimal Variables #########\n\n")
            f.write(f"Emax: {value(self.instance.Emax)}\n")
            f.write(f"Dmax: {value(self.instance.Dmax)}\n")
            f.write(f"RTE: {value(self.instance.RTE)}\n")
            f.write(f"SOCmax: {value(self.instance.SOCmax)}\n")
            f.write(f"SOCmin: {value(self.instance.SOCmin)}\n")
            f.write(f"SOCini: {value(self.instance.SOCini)}\n")
            f.write(f"SOCfin: {value(self.instance.SOCfin)}\n")

        # Save (t, s) indexed variables
        bess_vars = [
            ("dV.txt", self.instance.dV),
            ("cV.txt", self.instance.cV),
            ("idV.txt", self.instance.idV),
        ]
        self.save_ts_variable_group(bess_path, bess_vars)

        # === Store net charge-discharge difference (cV - dV) ===
        cv_dv_file = os.path.join(bess_path, "cV-dV.txt")
        with open(cv_dv_file, "w") as f:
            for s in self.instance.S:
                f.write(f"{s} {value(self.instance.Prob[s])} ")
                for t in self.instance.T:
                    for q in self.instance.Q:
                        net = value(self.instance.cV[t, q, s]) - value(self.instance.dV[t, q, s])
                        f.write(f"{net} ")
                f.write("\n")

        # Save (t0, s) indexed socV
        soc_file = os.path.join(bess_path, "socV.txt")
        with open(soc_file, "w") as f:
            for s in self.instance.S:
                f.write(f"{s} {value(self.instance.Prob[s])} ")
                f.write(f"{value(self.instance.socV[0, 1, s])} ")
                for t in self.instance.T:
                    for q in self.instance.Q:
                        f.write(f"{value(self.instance.socV[t, q, s])} ")
                f.write("\n")

    def store_day_ahead(self):
        da_path = os.path.join(run_config.PROJECT_ROOT, "results", self.sim_ctx.pathmarketres, "DA/")
        da_vars = [
            ("lD.txt", self.instance.lD),
            ("eDA_p.txt", self.instance.eDA_p),
            ("eDA_m.txt", self.instance.eDA_m),
            ("ieDA_p.txt", self.instance.ieDA_p),
            ("ieDA_m.txt", self.instance.ieDA_m),
        ]
        self.save_ts_variable_group(da_path, da_vars)
        open(os.path.join(da_path, "DA_params.txt"), "w").close()

    def store_rm(self):
        """
        Saves Reserve Market (RM) variables and parameters.
        """
        rm_path = os.path.join(run_config.PROJECT_ROOT, "results", self.sim_ctx.pathmarketres, "RM/")
        os.makedirs(rm_path, exist_ok=True)

        # Store RM parameter TSR
        with open(os.path.join(rm_path, "RM_params.txt"), "w") as f:
            f.write(f"TSR: {value(self.instance.TSR)}\n")

        # Define RM variables to save
        rm_vars = [
            ("rU.txt", self.instance.rU),
            ("rU_B.txt", self.instance.rU_B),
            ("rU_FD.txt", self.instance.rU_FD),
            ("rD.txt", self.instance.rD),
            ("rD_B.txt", self.instance.rD_B),
            ("rD_FD.txt", self.instance.rD_FD),
            ("lR.txt", self.instance.lR),
        ]
        if "IM" in self.sim_ctx.market:
            rm_vars.append(("rU_penalty.txt", self.instance.rU_penalty))
            rm_vars.append(("rD_penalty.txt", self.instance.rD_penalty))

        # Use the general method
        self.save_ts_variable_group(rm_path, rm_vars)

    def store_im(self):
        # Print header for Intraday Market Parameters
        with open(os.path.join(run_config.PROJECT_ROOT, "results", self.sim_ctx.pathmarketres, run_config.resfile), "a") as res_log:
            res_log.write("\n###### Printing Intraday Market Parameters and Optimal Variables #########\n\n")

        # Define the IM results directory
        im_path = os.path.join(run_config.PROJECT_ROOT, "results", self.sim_ctx.pathmarketres, "IM/")
        os.makedirs(im_path, exist_ok=True)

        # IM Sets and Parameters (lI values for each i in IM)
        for i in self.instance.IM:
            li_file = os.path.join(im_path, f"lI_{i}.txt")
            with open(li_file, "w") as f:
                for s in self.instance.S:
                    f.write(f"{s} {value(self.instance.Prob[s])} ")
                    for t in self.instance.T:
                        for q in self.instance.Q:
                            if t in self.instance.TIM[i]:
                                    f.write(f"{value(self.instance.lI[i, t, q, s])} ")
                            else:
                                f.write("0 ")
                        f.write("\n")

        # Store IM parameter maxTIM
        im_params_file = os.path.join(im_path, "IM_params.txt")
        with open(im_params_file, "w") as f:
            f.write(f"maxTIM: {value(self.instance.maxTIM)}\n")

        # IM Variables (eIM values for each i in IM)
        for i in self.instance.IM:
            eim_file = os.path.join(im_path, f"eIM_{i}.txt")
            with open(eim_file, "w") as f:
                for s in self.instance.S:
                    f.write(f"{s} {value(self.instance.Prob[s])} ")
                    for t in self.instance.T:
                        for q in self.instance.Q:
                            if t in self.instance.TIM[i]:
                                f.write(f"{value(self.instance.eIM[i, t, q, s])} ")
                            else:
                                f.write("0 ")
                        f.write("\n")

        # Compute total intraday market energy (eIM_TOT)
        eim_tot_dict = {}
        for t in self.instance.T:
            for q in self.instance.Q:
                for s in self.instance.S:
                    eim_tot_dict[(t, q, s)] = sum(value(self.instance.eIM[i, t, q, s]) for i in self.instance.IMT[t])

        # Store total IM energy (eIM_TOT)
        eim_tot_file = os.path.join(im_path, "eIM_TOT.txt")
        with open(eim_tot_file, "w") as f:
            for s in self.instance.S:
                f.write(f"{s} {value(self.instance.Prob[s])} ")
                for t in self.instance.T:
                    for q in self.instance.Q:
                        f.write(f"{eim_tot_dict[(t, q, s)]} ")
                f.write("\n")


    def store_ib_var(self, var_name, ib_path):
        file = os.path.join(ib_path, f"{var_name}.txt")
        atrribute = getattr(self.instance, var_name)   #this gets self.instance.PIB for example 
        with open(file, "w") as f:
            for s in self.instance.S:
                f.write(f"{s} {value(self.instance.Prob[s])} ")
                for t in self.instance.T:
                    for q in self.instance.Q:
                        val = pyo.value(atrribute[t, q, s], exception=False)
                        if val == None:
                            val = 0.0
                        f.write(f"{val} ")
                    f.write("\n")


    def store_ib(self):
        # Print header for Imbalances Parameters
        with open(os.path.join(run_config.PROJECT_ROOT, "results", self.sim_ctx.pathmarketres, run_config.resfile), "a") as res_log:
            res_log.write("\n###### Printing Imbalances Parameters and Optimal Variables #########\n\n")

        # Define the IB results directory
        ib_path = os.path.join(run_config.PROJECT_ROOT, "results", self.sim_ctx.pathmarketres, "IB/")
        os.makedirs(ib_path, exist_ok=True)

        # Store IB Parameters (lPIB and lNIB)

        self.store_ib_var("lPIB", ib_path)
        self.store_ib_var("lNIB", ib_path)
        self.store_ib_var("pIB_p", ib_path)
        self.store_ib_var("pIB_m", ib_path)

        # Store IB Net Imbalances (pIB_p - pIB_m)
        pIB_net_file = os.path.join(ib_path, "pIB_p-pIB_m.txt")
        with open(pIB_net_file, "w") as f:
            for s in self.instance.S:
                f.write(f"{s} {value(self.instance.Prob[s])} ")
                for t in self.instance.T:
                    for q in self.instance.Q:
                        val_pibp = pyo.value(self.instance.pIB_p[t, q, s], exception=False)
                        val_pibm = pyo.value(self.instance.pIB_m[t, q, s], exception=False)
                        if val_pibp == None:
                            val_pibp = 0.0
                        if val_pibm == None:
                            val_pibm = 0.0
                        pIB_net = val_pibp - val_pibm
                    f.write(f"{pIB_net} ")
                f.write("\n")
        
        if ("IM" in self.sim_ctx.market) or ("RM" in self.sim_ctx.market):
            self.store_ib_var("IB_pos_slack", ib_path)
            self.store_ib_var("IB_neg_slack", ib_path)


    def store_scenarios(self):
        # Print header for Scenarios
        with open(os.path.join(run_config.PROJECT_ROOT, "results", self.sim_ctx.pathmarketres, run_config.resfile), "a") as res_log:
            res_log.write("\n###### Printing Scenarios #########\n\n")

        # Define the Scenarios results directory
        scenarios_path = os.path.join(run_config.PROJECT_ROOT, "results", self.sim_ctx.pathmarketres)
        os.makedirs(scenarios_path, exist_ok=True)

        # Store Scenarios Data (Scen0)
        scenarios_file = os.path.join(scenarios_path, "scenarios.txt")
        with open(scenarios_file, "w") as f:
            for s in self.instance.S:
                f.write(f"{s} {value(self.instance.Prob[s])} ")
                for n in range(1, value(self.instance.nRV) + 1):
                    f.write(f"{value(self.instance.Scen0[n, s])} ")
                f.write("\n")

        # Store Scenario Tree (Clusters)
        tree_file = os.path.join(scenarios_path, "tree.txt")
        with open(tree_file, "w") as f:
            for k in self.instance.S:
                f.write(f"{k} ")
                for s in self.instance.SG0:
                    for i in self.instance.S0:
                        # Find the minimum representative scenario `m` in cluster `c[s, i]`
                        cluster_members = [m for m in self.instance.c[s, i] if m == k]
                        if cluster_members:
                            min_representative = min(self.instance.c[s, i])
                            f.write(f"{min_representative} ")
                f.write("\n")

    def store_hydrogen(self):
        # Define RM variables to save
        hydrogen_path = os.path.join(run_config.PROJECT_ROOT, "results", self.sim_ctx.pathres, "HYD/")
        hydrogen_vars = [
        ("eEL.txt", self.instance.eEL),
        ("HEL.txt", self.instance.HEL),
        ("eEL_on.txt", self.instance.eEL_on),
        ("eEL_sb.txt", self.instance.eEL_sb),
        ("iEL_on.txt", self.instance.iEL_on),
        ("iEL_sb.txt", self.instance.iEL_sb),
        ("iEL_off.txt", self.instance.iEL_off),
        ("i_EL_warm.txt", self.instance.i_EL_warm),
        ("i_EL_cold.txt", self.instance.i_EL_cold),
        ("HDIR_EL.txt", self.instance.HDIR_EL),
        ("HCOMP_EL.txt", self.instance.HCOMP_EL),
        ("eCOMP.txt", self.instance.eCOMP),
        ("HDIR_COMP.txt", self.instance.HDIR_COMP),
        ("Hsold.txt", self.instance.Hsold),
        ("HC_TK.txt", self.instance.HC_TK),
        ("LOH.txt", self.instance.LOH),
        ("HDISCH_TK.txt", self.instance.HDISCH_TK),
        ("HDIR_TK.txt", self.instance.HDIR_TK),
        ("iTK.txt", self.instance.iTK),
        ("HFC.txt", self.instance.HFC),
        ("eFC_on.txt", self.instance.eFC_on),
        ("eFC_sb.txt", self.instance.eFC_sb),
        ("iFC_on.txt", self.instance.iFC_on),
        ("iFC_sb.txt", self.instance.iFC_sb),
        ("iFC_off.txt", self.instance.iFC_off),
        ("i_FC_warm.txt", self.instance.i_FC_warm),
        ("i_FC_cold.txt", self.instance.i_FC_cold),
    ]
        # Use the general method
        self.save_ts_variable_group(hydrogen_path, hydrogen_vars)

        # store HYD parameters
        hyd_params_file = os.path.join(hydrogen_path, "HYD_params.txt")
        instance = self.instance
        with open(hyd_params_file, "w") as f:
            f.write("###### Printing HYD Parameters and Optimal Variables #########\n\n")
            f.write(f"HDEM_press: {value(self.instance.HDEM_press)}\n")
            f.write(f"min_EL_frac: {value(self.instance.min_EL_frac)}\n")
            f.write(f"P_EL_nom: {value(self.instance.P_EL_nom)}\n")
            f.write(f"eta_EL: {value(self.instance.eta_EL)}\n")
            f.write(f"sp_wat_EL: {value(self.instance.sp_wat_EL)}\n")
            f.write(f"lambda_wat: {value(self.instance.lambda_wat)}\n")
            f.write(f"SB_frac: {value(self.instance.SB_frac)}\n")
            f.write(f"EL_lifetime: {value(self.instance.EL_lifetime)}\n")
            f.write(f"EL_repl_cost: {value(self.instance.EL_repl_cost)}\n")
            f.write(f"lambda_warm_st: {value(self.instance.lambda_warm_st)}\n")
            f.write(f"lambda_cold_st: {value(self.instance.lambda_cold_st)}\n")
            f.write(f"spec_COMP: {value(self.instance.spec_COMP)}\n")
            f.write(f"P_COMP_nom: {value(self.instance.P_COMP_nom)}\n")
            f.write(f"H_tank_cap: {value(self.instance.H_tank_cap)}\n")
            f.write(f"P_tank: {value(self.instance.P_tank)}\n")
            f.write(f"eta_tank: {value(self.instance.eta_tank)}\n")
            f.write(f"LOH_min: {value(self.instance.LOH_min)}\n")
            f.write(f"LOH_max: {value(self.instance.LOH_max)}\n")
            f.write(f"LOH_ini: {value(self.instance.LOH_ini)}\n")
            f.write(f"LOH_fin: {value(self.instance.LOH_fin)}\n")
            f.write(f"min_FC_frac: {value(self.instance.min_FC_frac)}\n")
            f.write(f"P_FC_nom: {value(self.instance.P_FC_nom)}\n")
            f.write(f"eta_FC: {value(self.instance.eta_FC)}\n")
            f.write(f"SB_frac_FC: {value(self.instance.SB_frac_FC)}\n")
            f.write(f"FC_lifetime: {value(self.instance.FC_lifetime)}\n")
            f.write(f"FC_repl_cost: {value(self.instance.FC_repl_cost)}\n")
            f.write(f"lambda_warm_st_FC: {value(self.instance.lambda_warm_st_FC)}\n")
            f.write(f"lambda_cold_st_FC: {value(self.instance.lambda_cold_st_FC)}\n")

    def store_objective_function(self):
        # Print header for Objective Function
        with open(os.path.join(run_config.PROJECT_ROOT, "results", self.sim_ctx.pathres, run_config.resfile), "a") as res_log:
            res_log.write("\n###### Objective Function #########\n\n")

        # Define the Objective function results directory
        obj_path = os.path.join(run_config.PROJECT_ROOT, "results", self.sim_ctx.pathres, "OBJ/")
        os.makedirs(obj_path, exist_ok=True)

        # Compute Objective Function Components
        obj_fun = value(self.instance.EECSW)

        obj_DA_income = sum(value(self.instance.Prob[s]) * value(self.instance.lD[t, q, s]) *
                            (value(self.instance.eDA_p[t, q, s]) - value(self.instance.eDA_m[t, q, s]))
                            for t in self.instance.T for q in self.instance.Q for s in self.instance.S)

        if "IM" in self.sim_ctx.market:
            obj_RM_income = sum(
                value(self.instance.Prob[s]) * (
                        (value(self.instance.rD[t, q, s]) + value(self.instance.rU[t, q, s])) * value(self.instance.lR[t, q, s])
                        - value(self.instance.lR_penalty[t, q, s]) * (
                                    value(self.instance.rU_penalty[t, q, s]) + value(self.instance.rD_penalty[t, q, s]))
                )
                for t in self.instance.T
                for q in self.instance.Q
                for s in self.instance.S
            )
        else:
            obj_RM_income = sum(
                value(self.instance.Prob[s]) * (value(self.instance.rD[t, q, s]) + value(self.instance.rU[t, q, s])) * value(
                    self.instance.lR[t, q, s])
                for t in self.instance.T for q in self.instance.Q for s in self.instance.S)

        obj_IM_income = sum(
            value(self.instance.Prob[s]) * sum(
                value(self.instance.lI[i, t, q, s]) * value(self.instance.eIM[i, t, q, s]) for i in self.instance.IMT[t])
            for t in self.instance.T for q in self.instance.Q for s in self.instance.S)

        obj_IB_income = sum(
            value(self.instance.Prob[s]) * value(self.instance.lPIB[t, q, s]) * value(self.instance.pIB_p[t, q, s])
            for t in self.instance.T for q in self.instance.Q for s in self.instance.S)

        obj_IB_costs = sum(
            value(self.instance.Prob[s]) * value(self.instance.lNIB[t, q, s]) * value(self.instance.pIB_m[t, q, s])
            for t in self.instance.T for q in self.instance.Q for s in self.instance.S)

        obj_IB_net = obj_IB_income - obj_IB_costs

        obj_FD_costs = sum(value(self.instance.Prob[s]) * value(self.instance.C_FD) *
                           (value(self.instance.var_afd_p[t, q, s]) + value(self.instance.var_afd_m[t, q, s]))
                           for t in self.instance.T for q in self.instance.Q for s in self.instance.S)

        if self.sim_ctx.include_hydro:
            obj_H2_income = sum(value(self.instance.Prob[s]) * value(self.instance.lambda_H) * 
                value(self.instance.Hsold[t, q, s]) * value(self.instance.can_sell_H2)
                for t in self.instance.T for q in self.instance.Q for s in self.instance.S)    
                                                                 
            obj_H2_DEM = sum(value(self.instance.lambda_H) * value(self.instance.HDEM[t, q])
                for t in self.instance.T for q in self.instance.Q)
             
            obj_BESS_costs = sum(value(self.instance.Prob[s]) * 
            ((value(self.instance.dV[t, q, s]) + value(self.instance.cV[t, q, s]))/(2 * value(self.instance.Emax))) * (value(self.instance.B_sp_cost) * value(self.instance.Emax) / value(self.instance.cyc_max))
            for t in self.instance.T for q in self.instance.Q for s in self.instance.S)

            obj_wat_costs = sum(value(self.instance.Prob[s]) * value(self.instance.lambda_wat) * value(self.instance.sp_wat_EL) *
            value(self.instance.HEL[t, q, s])
            for t in self.instance.T for q in self.instance.Q for s in self.instance.S)

            obj_warm_st_costs = sum(value(self.instance.Prob[s]) * value(self.instance.lambda_warm_st) * 
                value(self.instance.P_EL_nom) * value(self.instance.i_EL_warm[t, q, s]) 
                for t in self.instance.T for q in self.instance.Q for s in self.instance.S)

            obj_cold_st_costs = sum(value(self.instance.Prob[s]) * value(self.instance.lambda_cold_st) * 
                value(self.instance.P_EL_nom) * value(self.instance.i_EL_cold[t, q, s]) 
                for t in self.instance.T for q in self.instance.Q for s in self.instance.S)

            obj_deg_EL_costs = sum(value(self.instance.Prob[s]) * value(self.instance.EL_repl_cost) * 
                value(self.instance.P_EL_nom) / value(self.instance.EL_lifetime) * value(self.instance.iEL_on[t, q, s])
                for t in self.instance.T for q in self.instance.Q for s in self.instance.S)
             
            obj_warm_st_costs_FC = sum(value(self.instance.Prob[s]) * value(self.instance.lambda_warm_st_FC) * 
                value(self.instance.P_FC_nom) * value(self.instance.i_FC_warm[t, q, s]) 
                for t in self.instance.T for q in self.instance.Q for s in self.instance.S)

            obj_cold_st_costs_FC = sum(value(self.instance.Prob[s]) * value(self.instance.lambda_cold_st_FC) * 
                value(self.instance.P_FC_nom) * value(self.instance.i_FC_cold[t, q, s]) 
                for t in self.instance.T for q in self.instance.Q for s in self.instance.S)
             
            obj_deg_FC_costs = sum(value(self.instance.Prob[s]) * value(self.instance.FC_repl_cost) * 
                value(self.instance.P_FC_nom) / value(self.instance.FC_lifetime) * value(self.instance.iFC_on[t, q, s])
                for t in self.instance.T for q in self.instance.Q for s in self.instance.S)

        obj_IB_costs = sum(value(self.instance.Prob[s]) * value(self.instance.lNIB[t, q, s]) * value(self.instance.pIB_m[t, q, s])
            for t in self.instance.T for q in self.instance.Q for s in self.instance.S)

        self.instance.obj_fun[run_config.probl, self.sim_ctx.sim] = obj_fun
        self.instance.obj_DA_income[run_config.probl, self.sim_ctx.sim] = obj_DA_income
        self.instance.obj_RM_income[run_config.probl, self.sim_ctx.sim] = obj_RM_income
        self.instance.obj_IM_income[run_config.probl, self.sim_ctx.sim] = obj_IM_income
        self.instance.obj_IB_income[run_config.probl, self.sim_ctx.sim] = obj_IB_income
        self.instance.obj_IB_costs[run_config.probl, self.sim_ctx.sim] = obj_IB_costs
        self.instance.obj_IB_net[run_config.probl, self.sim_ctx.sim] = obj_IB_net
        self.instance.obj_FD_costs[run_config.probl, self.sim_ctx.sim] = obj_FD_costs
        if self.sim_ctx.include_hydro:
            self.instance.obj_H2_income[run_config.probl, self.sim_ctx.sim] = obj_H2_income
            self.instance.obj_H2_DEM[run_config.probl, self.sim_ctx.sim] = obj_H2_DEM
            self.instance.obj_BESS_costs[run_config.probl, self.sim_ctx.sim] = obj_BESS_costs
            self.instance.obj_wat_costs[run_config.probl, self.sim_ctx.sim] = obj_wat_costs
            self.instance.obj_warm_st_costs[run_config.probl, self.sim_ctx.sim] = obj_warm_st_costs
            self.instance.obj_cold_st_costs[run_config.probl, self.sim_ctx.sim] = obj_cold_st_costs
            self.instance.obj_deg_EL_costs[run_config.probl, self.sim_ctx.sim] = obj_deg_EL_costs
            self.instance.obj_warm_st_costs_FC[run_config.probl, self.sim_ctx.sim] = obj_warm_st_costs_FC
            self.instance.obj_cold_st_costs_FC[run_config.probl, self.sim_ctx.sim] = obj_cold_st_costs_FC
            self.instance.obj_deg_FC_costs[run_config.probl, self.sim_ctx.sim] = obj_deg_FC_costs
        # Store Objective Function Components
        if self.sim_ctx.include_hydro:
            obj_components = {
                "obj_fun.txt": obj_fun,
                "obj_DA_income.txt": obj_DA_income,
                "obj_RM_income.txt": obj_RM_income,
                "obj_IM_income.txt": obj_IM_income,
                "obj_IB_income.txt": obj_IB_income,
                "obj_H2_income.txt": obj_H2_income,
                "obj_H2_DEM.txt": obj_H2_DEM,
                "obj_IB_costs.txt": obj_IB_costs,
                "obj_IB_net.txt": obj_IB_net,
                "obj_FD_costs.txt": obj_FD_costs,
                "obj_BESS_costs.txt": obj_BESS_costs,
                "obj_wat_costs.txt": obj_wat_costs,
                "obj_warm_st_costs.txt": obj_warm_st_costs,
                "obj_cold_st_costs.txt": obj_cold_st_costs,
                "obj_deg_EL_costs.txt": obj_deg_EL_costs,
                "obj_warm_st_costs_FC.txt": obj_warm_st_costs_FC,
                "obj_cold_st_costs_FC.txt": obj_cold_st_costs_FC,
                "obj_deg_FC_costs.txt": obj_deg_FC_costs,
            }
        else:
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

        # Store values in SimulationContext for summary writer
        self.sim_ctx.obj_results["obj_fun"] = obj_fun
        self.sim_ctx.obj_results["obj_DA_income"] = obj_DA_income
        self.sim_ctx.obj_results["obj_RM_income"] = obj_RM_income
        self.sim_ctx.obj_results["obj_IM_income"] = obj_IM_income
        self.sim_ctx.obj_results["obj_IB_income"] = obj_IB_income
        self.sim_ctx.obj_results["obj_IB_costs"] = obj_IB_costs
        self.sim_ctx.obj_results["obj_IB_net"] = obj_IB_net
        self.sim_ctx.obj_results["obj_FD_costs"] = obj_FD_costs
        if self.sim_ctx.include_hydro:
            self.sim_ctx.obj_results["obj_H2_income"] = obj_H2_income
            self.sim_ctx.obj_results["obj_H2_DEM"] = obj_H2_DEM
            self.sim_ctx.obj_results["obj_BESS_costs"] = obj_BESS_costs
            self.sim_ctx.obj_results["obj_wat_costs"] = obj_wat_costs
            self.sim_ctx.obj_results["obj_warm_st_costs"] = obj_warm_st_costs
            self.sim_ctx.obj_results["obj_cold_st_costs"] = obj_cold_st_costs
            self.sim_ctx.obj_results["obj_deg_EL_costs"] = obj_deg_EL_costs
            self.sim_ctx.obj_results["obj_warm_st_costs_FC"] = obj_warm_st_costs_FC
            self.sim_ctx.obj_results["obj_cold_st_costs_FC"]= obj_cold_st_costs_FC
            self.sim_ctx.obj_results["obj_deg_FC_costs"] = obj_deg_FC_costs

    def print_incomes(self):
        instance = self.instance
        print(
            f"DA Income: {sum(value(self.instance.Prob[s]) * value(self.instance.lD[t, q, s]) * (value(self.instance.eDA_p[t, q, s]) - value(self.instance.eDA_m[t, q, s])) for t in self.instance.T for q in self.instance.Q for s in self.instance.S)}")
        print(
            f"RM Income: {sum(value(self.instance.Prob[s]) * (value(self.instance.rD[t, q, s]) + value(self.instance.rU[t, q, s])) * value(self.instance.lR[t, q, s]) for t in self.instance.T for q in self.instance.Q for s in self.instance.S)}")
        print(
            f"IM Income: {sum(value(self.instance.Prob[s]) * sum(value(self.instance.lI[i, t, q, s]) * value(self.instance.eIM[i, t, q, s]) for i in self.instance.IMT[t]) for t in self.instance.T for q in self.instance.Q for s in self.instance.S)}")
        print(
            f"IB Income: {sum(value(self.instance.Prob[s]) * value(self.instance.lPIB[t, q, s]) * value(self.instance.pIB_p[t, q, s]) for t in self.instance.T for q in self.instance.Q for s in self.instance.S)}")
        print(
            f"IB Costs: {sum(value(self.instance.Prob[s]) * value(self.instance.lNIB[t, q, s]) * value(self.instance.pIB_m[t, q, s]) for t in self.instance.T for q in self.instance.Q for s in self.instance.S)}")
        print(
            f"FD Costs: {sum(value(self.instance.Prob[s]) * value(self.instance.C_FD) * (value(self.instance.var_afd_p[t, q, s]) + value(self.instance.var_afd_m[t, q, s])) for t in self.instance.T for q in self.instance.Q for s in self.instance.S)}")


    def store_results(self):
        self.print_ampl_console_output()

        # Save individual components
        self.store_flex_demand_vars()
        self.store_wind_power()
        self.store_pv()
        self.store_bess()
        self.store_day_ahead()
        self.store_rm()
        self.store_im()
        self.store_ib()
        self.store_scenarios()
        if self.sim_ctx.include_hydro:
            self.store_hydrogen()
        self.store_objective_function()
        curves = self.get_RM_bid_curves()
        #plot_rm_bid_curve(curves, cumulate=False, t=1)
        #plot_rm_bid_curve(curves, cumulate=False, t=14)
        x=1

    def perform_nac_checks(self):
        # Perform Non-Anticipativity Constraint (NAC) checks
        self.nac_DAM_and_RM()
        self.nac_demand_and_battery()

    def get_RM_bid_curves(self):

        curves = {}
        for t in self.instance.T:
            for q in self.instance.Q:
                up = sorted(
                    [(value(self.instance.lR[t, q, s]), value(self.instance.rU[t, q, s]))
                     for s in self.instance.S],
                    key=lambda x: x[0]
                )
                down = sorted(
                    [(value(self.instance.lR[t, q, s]), value(self.instance.rD[t, q, s]))
                     for s in self.instance.S],
                    key=lambda x: x[0]
                )
                curves[(t, q)] = {"up": up, "down": down}
        return curves

def plot_rm_bid_curve(curves, t, *, cumulate=True, show=True, ax=None):
    """
    Plot the RM upward & downward bid curves for hour *t*.

    Parameters
    ----------
    curves : dict
        What `get_RM_bid_curves()` (your function) returns, i.e.
        {t: {"up": [(price, MW), …], "down": [(price, MW), …]}, …}.
    t : int
        Hour to plot.
    cumulate : bool, default True
        If True the curve is drawn as the cumulative MW staircase,
        which is how market-clearing supply curves are usually shown.
        If False, raw MW values are plotted.
    show : bool, default True
        Whether to immediately display the figure (handy in notebooks).
    ax : matplotlib.axes.Axes, default None
        Pass an existing axes if you want to embed the plot elsewhere.

    Returns
    -------
    matplotlib.axes.Axes
        The axes that contains the plot (so you can further style or save).
    """
    if t not in curves:
        raise KeyError(f"Hour {t} not found in curves dict")

    # --- pull the data ---------------------------------------------------
    up_pairs   = curves[t]["up"]
    down_pairs = curves[t]["down"]
    def _prep(pairs):
        if not pairs:
            return array([0.0, 1.0]), array([0.0, 0.0])  # harmless flat line
        # unpack
        prices = array([p for p, _ in pairs], dtype=float)
        qty    = array([q for _, q in pairs], dtype=float)
        if cumulate:
            qty = cumsum(qty)
        # build staircase with horizontal tails:
        # left tail: start at q=0 with first price
        # Start with tail at q=0
        x = [0.0] + qty.tolist()
        y = [0] + prices.tolist()
        # End tail: extend x and y by one more point at same price
        #xmax = x[-1] + x[-1] * 1.25
        #x.append(xmax)
        #y.append(prices[-1])
        return array(x), array(y)


    p_up,   q_up   = zip(*up_pairs)   if up_pairs   else ([], [])
    p_down, q_down = zip(*down_pairs) if down_pairs else ([], [])

    # --- plotting --------------------------------------------------------
    p_up,   q_up   = _prep(up_pairs)
    p_down, q_down = _prep(down_pairs)
    if ax is None:
        fig, ax = plt.subplots(figsize=(6, 4))

    ax.step(q_up,   p_up,   where="post", label="Up reserve")
    ax.step(q_down, p_down, where="post", linestyle="--", label="Down reserve")

    ax.set_xlabel("Cumulative MW" if cumulate else "MW (per scenario)")
    ax.set_ylabel("Price (€/MW h)")
    ax.set_title(f"Reserve-market bid curves – hour {t}")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()

    if show:
        plt.show()

    return ax
