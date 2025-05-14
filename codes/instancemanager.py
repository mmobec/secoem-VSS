import os
import math
import time
import pyomo.environ as pyo
from pyomo.environ import DataPortal, value, SolverFactory
from ec_model_rm import model as abstract_model  # Your AbstractModel definition
import config_definition as run_config


class InstanceManager:

    def __init__(self, scenario_data, sim_ctx):
        self.scenario_data = scenario_data
        self.instance = self.create_instance_wrapper()
        self.metrics = {}
        self.sim_ctx = sim_ctx

    def create_instance_wrapper(self):
        "instance creation"
        self.override_da_results()
        self.instance = abstract_model.create_instance(self.scenario_data)

        print(f"self.instance Variables: {len(list(self.instance.component_objects(pyo.Var)))}")
        print(f"self.instance Constraints: {len(list(self.instance.component_objects(pyo.Constraint)))}")
        if hasattr(self.instance, 'var_fd'):
            print(f"var_fd size: {len(list(self.instance.var_fd.keys()))}")  # Should be 24
        print(f"T size: {len(list(self.instance.T))}")  # Should be 24
        print(f"S size: {len(list(self.instance.S))}")  # Should be 10
        return self.instance


    #This is for RM
    def override_da_results(self):

        scenarios = self.scenario_data.data()["S"][None]

        for s in scenarios:
            for t, price in run_config.DA_PRICE_OBS.items():
                self.scenario_data["lD"][t, s] = price

        self.scenario_data.data()["eDA_p"] = {}
        self.scenario_data.data()["eDA_m"] = {}
        for t in range(1, 25):
            for s in scenarios:
                self.scenario_data.data()["eDA_p"][t,s] = run_config.DA_E_P_OBS[t]
                self.scenario_data.data()["eDA_m"][t,s] = run_config.DA_E_M_OBS[t,s]
            """
            self.scenario_data.data()["eDA_p"] = {} # since these are not initialized in the scenario_data
            for t, energy in run_config.DA_E_P_OBS.items():
                for s in scenarios:
                    self.scenario_data.data()["eDA_p"][t, s] = energy

            self.scenario_data.data()["eDA_m"] = {}
            for t, energy in run_config.DA_E_M_OBS.items():
                for s in scenarios:
                    self.scenario_data.data()["eDA_m"][t, s] = energy
            """
        x=1
    def compute_scenario_cluster(self):
        "After creating the self.instance but before running the solver other parameters must be allocated"
        # Compute scenario cluster (c)
        c_filtered = {}
        for sg in self.instance.SG0:
            for s in self.instance.S0:
                c_filtered[(sg, s)] = [sc for sc in self.instance.c[sg, s] if sc in self.instance.S]
        # Store filtered clusters back into Pyomo model
        for (sg, s), cluster in c_filtered.items():
            self.instance.c[sg, s] = sorted(cluster)

    def compute_expected_scenario_cluster(self):
        # Compute Expected Scenario (ScenE)
        ScenE_dict = {}
        for rv in range(1, value(self.instance.nRV) + 1):  # Loop over all random variables
            ScenE_dict[rv] = sum(value(self.instance.Prob0[s_]) * value(self.instance.Scen0[rv, s_]) for s_ in self.instance.S0)
        # Store into Pyomo model (ScenE is mutable, so we can assign values)
        for rv, val in ScenE_dict.items():
            self.instance.ScenE[rv] = val

    def compute_power_outputs(self):
        # Compute pW and pPV
        pW_dict = {}
        pPV_dict = {}
        mean_pW_dict = {}
        mean_pPV_dict = {}
        sigma_pW_dict = {}

        for t in self.instance.T:
            for s in self.instance.S:
                # Fetch the correct random variable index from fRVSG
                rv_index_wind = value(self.instance.fRVSG[value(self.instance.sgpw[t])])
                rv_index_solar = rv_index_wind + 1  # Next variable corresponds to PV
                # Compute wind power
                pW_dict[(t, s)] = min(value(self.instance.Scen[rv_index_wind, s]), 1.0) * value(self.instance.Pavg)
                # Compute PV power
                pPV_dict[(t, s)] = min(value(self.instance.Scen[rv_index_solar, s]), 1.0) * value(self.instance.Pavg_PV)
        # Compute mean values
        for t in self.instance.T:
            mean_pW_dict[t] = sum(value(self.instance.Prob[s]) * pW_dict[(t, s)] for s in self.instance.S)
            mean_pPV_dict[t] = sum(value(self.instance.Prob[s]) * pPV_dict[(t, s)] for s in self.instance.S)
        # Compute sigma_pW (standard deviation)
        for t in self.instance.T:
            variance_pW = sum(value(self.instance.Prob[s]) * (pW_dict[(t, s)] - mean_pW_dict[t]) ** 2 for s in self.instance.S)
            sigma_pW_dict[t] = math.sqrt(variance_pW)
        # Store values in Pyomo model
        for (t, s), val in pW_dict.items():
            self.instance.pW[t, s] = val
        for (t, s), val in pPV_dict.items():
            self.instance.pPV[t, s] = val
        for t, val in mean_pW_dict.items():
            self.instance.mean_pW[t] = val
        for t, val in mean_pPV_dict.items():
            self.instance.mean_pPV[t] = val
        for t, val in sigma_pW_dict.items():
            self.instance.sigma_pW[t] = val

        # Compute max values for wind and solar power
        mean_pW_avg = sum(mean_pW_dict[t] for t in self.instance.T) / value(self.instance.nT)
        mean_pPV_avg = sum(mean_pPV_dict[t] for t in self.instance.T) / value(self.instance.nT)
        max_pW = max(value(self.instance.pW[t, s]) for t in self.instance.T for s in self.instance.S)
        max_pPV = max(value(self.instance.pPV[t, s]) for t in self.instance.T for s in self.instance.S)
        # Store max values in Pyomo model
        self.instance.max_pW = max_pW
        self.instance.max_pPV = max_pPV

        #Logging
        self.metrics["max_pW"] = max_pW
        self.metrics["max_pPV"] = max_pPV
        self.metrics["mean_pW_avg"] = mean_pW_avg
        self.metrics["mean_pPV_avg"] = mean_pPV_avg


        #with open(os.path.join("..", self.sim_ctx.pathres, run_config.resfile), "a") as res_log:
        #    res_log.write(f"max_pW: {max_pW}, max_pPV: {max_pPV}\n")
        #    res_out.write(f"mean_pW_avg  = {mean_pW_avg:.6f}\n")
        #    res_out.write(f"mean_pPV_avg  = {mean_pW_avg:.6f}\n")

        print(f"max_pW: {max_pW}, mean_pW: {mean_pW_avg}, max_pPV: {max_pPV}, mean_pPV: {mean_pPV_avg}")

    def compute_instance_cardinality(self):
        # Cardinality of S0 and S
        card_S0 = len(self.instance.S0)
        card_S = len(self.instance.S)

        self.metrics["\n Cardinality \n card(S0)"] = card_S0
        self.metrics["Cardinality card(S)"] = card_S

        #with open(os.path.join("..", self.sim_ctx.pathres, run_config.resfile), "a") as res_log:
        #    res_log.write("\n Cardinality of the problem:\n")
        #    res_log.write(f"card(S0): {card_S0}\n")
        #    res_log.write(f"card(S): {card_S}\n")
        print(f"card(S0): {card_S0}, card(S): {card_S}")

    def compute_nearest_tree(self):
        # Compute nearest tree scenario to the observed scenario ScenO: dTO and sOR
        dTO_dict = {}
        min_dTO = 10 ** 10  # Large initial value
        sOR = -1  # Default value
        for s in self.instance.S:
            dTO_dict[s] = math.sqrt(sum(
                (value(self.instance.Scen[rv, s]) - value(self.instance.ScenO[rv])) ** 2 for rv in
                range(1, value(self.instance.nRV) + 1)))
        # Find the scenario with the minimum distance
        for s in self.instance.S:
            if dTO_dict[s] < min_dTO:
                min_dTO = dTO_dict[s]
                sOR = s
        # Store in Pyomo model
        self.instance.min_dTO = min_dTO
        self.instance.sOR = sOR
        # Log nearest tree scenario
        self.metrics["\n Nearest Tree scenario, Observed data:\n sOR"] = sOR
        self.metrics["min_dTO"] = min_dTO


        #with open(os.path.join("..", self.sim_ctx.pathres, run_config.resfile), "a") as res_log:
        #    res_log.write("\n Nearest Tree scenario, Observed data:\n")
        #    res_log.write(f"sOR: {sOR}\n")
        #    res_log.write(f"min_dTO: {min_dTO}\n")
        print(f"Nearest Tree Scenario: sOR={sOR}, min_dTO={min_dTO}")

    def compute_representative_scenarios(self):
        # Reset IM bid bounds and auxiliary parameters
        SSG_dict = {sg: set() for sg in self.instance.SG0}  # Representative scenarios per stage
        probc_dict = {}  # Probability of clusters
        mean_pWc_dict = {}  # Conditional mean wind power
        # Identify representative scenarios at each stage sg
        for sg in self.instance.SG0:
            SSG_dict[sg] = sorted({s for s in self.instance.S0 if len(self.instance.c[sg, s]) > 0})
        # Compute probability of cluster c[sg, sc]
        for sg in self.instance.SG0:
            for sc in SSG_dict[sg]:
                probc_dict[sg, sc] = sum(value(self.instance.Prob[s]) for s in self.instance.c[sg, sc])
        # Store computed values into the Pyomo model
        for sg, scenarios in SSG_dict.items():
            self.instance.SSG[sg] = scenarios

    def compute_imbalance_bounds(self):

        # Compute bounds for imbalance bids
        PIB_p_dict = {}
        PIB_m_dict = {}
        for t in self.instance.T:
            for s in self.instance.S:
                imbalance_p = value(self.instance.pW[t, s]) + value(self.instance.pPV[t, s]) - value(self.instance.mean_pW[t]) - value(
                    self.instance.mean_pPV[t])
                PIB_p_dict[(t, s)] = imbalance_p if imbalance_p >= 0 else 0.0
                PIB_m_dict[(t, s)] = -imbalance_p if imbalance_p < 0 else 0.0
        # Store computed values into Pyomo model
        for (t, s), val in PIB_p_dict.items():
            self.instance.PIB_p[t, s] = val
        for (t, s), val in PIB_m_dict.items():
            self.instance.PIB_m[t, s] = val

    def compute_market_prices(self):
        # Compute market prices (Day-Ahead prices already defined before creating the self.instance)

        """
        Commented Out RM because it is defined similarly to DAM in preprocessing
        """

        #lR_dict = {}
        lI_dict = {}
        lIB_dict = {}
        # Assign values to dictionaries
        for t in self.instance.T:
            for s in self.instance.S:
                # Reserve market prices
                #lR_dict[t, s] = value(self.instance.Scen[value(self.instance.nT) + t, s])
                # System imbalance prices
                lIB_dict[t, s] = value(self.instance.Scen[value(self.instance.fRVSG[value(self.instance.nSG)]) + (t - 1), s])
        # Assign Intraday Market prices
        for i in self.instance.IM:
            for t in self.instance.TIM[i]:
                for s in self.instance.S:
                    lI_dict[i, t, s] = value(
                        self.instance.Scen[value(self.instance.fRVSG[value(self.instance.sgim[i])]) + t - min(self.instance.TIM[i]), s])
        # Store values in Pyomo self.instance
        #for (t, s), val in lR_dict.items():
            #self.instance.lR[t, s] = val
        for (i, t, s), val in lI_dict.items():
            self.instance.lI[i, t, s] = val
        for (t, s), val in lIB_dict.items():
            self.instance.lIB[t, s] = val

    def compute_mean_market_prices(self):
        # Compute mean market prices (the average value across all scenarios for each hour)
        mean_lD_dict = {}
        mean_lR_dict = {}
        mean_lI_dict = {}
        mean_lIB_dict = {}
        # Compute mean values
        for t in self.instance.T:
            mean_lD_dict[t] = sum(value(self.instance.Prob[s]) * value(self.instance.lD[t, s]) for s in self.instance.S)
            mean_lR_dict[t] = sum(value(self.instance.Prob[s]) * value(self.instance.lR[t, s]) for s in self.instance.S)
            mean_lIB_dict[t] = sum(value(self.instance.Prob[s]) * value(self.instance.lIB[t, s]) for s in self.instance.S)
        # Compute mean values for intraday markets
        for i in self.instance.IM:
            for t in self.instance.TIM[i]:
                mean_lI_dict[i, t] = sum(value(self.instance.Prob[s]) * value(self.instance.lI[i, t, s]) for s in self.instance.S)

        # Store values in Pyomo self.instance
        for t, val in mean_lD_dict.items():
            self.instance.mean_lD[t] = val
        for t, val in mean_lR_dict.items():
            self.instance.mean_lR[t] = val
        for (i, t), val in mean_lI_dict.items():
            self.instance.mean_lI[i, t] = val
        for t, val in mean_lIB_dict.items():
            self.instance.mean_lIB[t] = val

        # === PRINT RESULTS ===
        # print("\n##### mean_lD (Day-Ahead Prices) #####")
        # for t, val in mean_lD_dict.items():
        #     print(f"mean_lD[{t}] = {val}")

        # print("\n##### mean_lR (Reserve Market Prices) #####")
        # for t, val in mean_lR_dict.items():
        #     print(f"mean_lR[{t}] = {val}")

        # print("\n##### mean_lI (Intraday Market Prices) #####")
        # for i in self.instance.IM:
        #     print(f"\n--- Intraday Market {i} ---")
        #     for t in self.instance.TIM[i]:
        #         print(f"mean_lI[{i}, {t}] = {mean_lI_dict[i, t]}")

        # print("\n##### mean_lIB (System Imbalance Prices) #####")
        # for t, val in mean_lIB_dict.items():
        #     print(f"mean_lIB[{t}] = {val}")

        # Compute and display mean values (the average value across all scenarios for all hours)
        mean_lD_avg = sum(mean_lD_dict[t] for t in self.instance.T) / value(self.instance.nT)
        mean_lR_avg = sum(mean_lR_dict[t] for t in self.instance.T) / value(self.instance.nT)
        mean_lIB_avg = sum(mean_lIB_dict[t] for t in self.instance.T) / value(self.instance.nT)

        # Compute average per intraday market (per i)
        mean_lI_avg_per_market = {}
        for i in self.instance.IM:
            t_list = list(self.instance.TIM[i])
            mean_lI_avg_per_market[i] = sum(mean_lI_dict[i, t] for t in t_list) / len(t_list)

        # Compute total average across all intraday markets (global average)
        total_sum_lI = sum(mean_lI_dict[i, t] for i in self.instance.IM for t in self.instance.TIM[i])
        total_TIM = sum(len(self.instance.TIM[i]) for i in self.instance.IM)
        mean_lI_global_avg = total_sum_lI / total_TIM

        # Write results to file
        self.metrics['mean_lD_avg'] = mean_lD_avg
        self.metrics['mean_lR_avg'] = mean_lR_avg
        self.metrics['mean_lIB_avg'] = mean_lIB_avg
        #with open(os.path.join("..", self.sim_ctx.pathres, run_config.resfile), "a") as res_out:
        #    res_out.write("\nMean Values:\n")
        #    res_out.write(f"mean_lD_avg  = {mean_lD_avg:.6f}\n")
        #    res_out.write(f"mean_lR_avg  = {mean_lR_avg:.6f}\n")
        #    res_out.write(f"mean_lIB_avg = {mean_lIB_avg:.6f}\n")
        #    res_out.write(f"mean_pW_avg  = {mean_pW_avg:.6f}\n")
        #    res_out.write(f"mean_pPV_avg  = {mean_pW_avg:.6f}\n")

    def compute_imbalance_prices(self):
        # Compute positive and negative imbalance prices
        lPIB_dict = {}
        lNIB_dict = {}
        for t in self.instance.T:
            for s in self.instance.S:
                lIB_val = value(self.instance.lIB[t, s])
                lD_val = value(self.instance.lD[t, s])
                if lIB_val <= 1:
                    lPIB_dict[(t, s)] = min(180.3, lIB_val * lD_val)
                    lNIB_dict[(t, s)] = lD_val
                else:
                    lPIB_dict[(t, s)] = lD_val
                    lNIB_dict[(t, s)] = min(180.3, lIB_val * lD_val)
        # Store computed values in Pyomo model
        for (t, s), val in lPIB_dict.items():
            self.instance.lPIB[t, s] = val
        for (t, s), val in lNIB_dict.items():
            self.instance.lNIB[t, s] = val

        # Compute mean values for imbalance prices
        mean_lPIB_dict = {t: sum(value(self.instance.Prob[s]) * lPIB_dict[(t, s)] for s in self.instance.S) for t in self.instance.T}
        mean_lNIB_dict = {t: sum(value(self.instance.Prob[s]) * lNIB_dict[(t, s)] for s in self.instance.S) for t in self.instance.T}

        # Store computed values in Pyomo model
        for t, val in mean_lPIB_dict.items():
            self.instance.mean_lPIB[t] = val
        for t, val in mean_lNIB_dict.items():
            self.instance.mean_lNIB[t] = val

        # === PRINT RESULTS ===
        # print("\n##### Positive imbalance prices #####")
        # for t, val in mean_lPIB_dict.items():
        #     print(f"mean_lPIB[{t}] = {val}")

        # print("\n##### Negative imbalance prices #####")
        # for t, val in mean_lNIB_dict.items():
        #     print(f"mean_lNIB[{t}] = {val}")

        # Compute the average values
        mean_lPIB_avg = sum(mean_lPIB_dict[t] for t in self.instance.T) / value(self.instance.nT)
        mean_lNIB_avg = sum(mean_lNIB_dict[t] for t in self.instance.T) / value(self.instance.nT)

        print("\nMean Values:")
        print(f"mean_lD_avg  = {self.metrics.get('mean_lD_avg', 0):.6f}")
        print(f"mean_lR_avg  = {self.metrics.get('mean_lR_avg', 0):.6f}")
        print(f"mean_lIB_avg = {self.metrics.get('mean_lIB_avg', 0):.6f} (used to calculate pos. and neg. imb. prices)")
        for i, val in self.metrics.get('mean_lI_avg_per_market', {}).items():
            print(f"mean_lI_avg for IM[{i}] = {val:.6f}")
        print(f"mean_lI_global_avg (all IMs combined) = {self.metrics.get('mean_lI_global_avg', 0):.6f}")

        # Print average imbalances prices
        print(f"mean_lPIB_avg  = {mean_lPIB_avg:.6f}")
        print(f"mean_lNIB_avg  = {mean_lNIB_avg:.6f}")

    def log_metrics(self):
        """
        Consolidate the collected metrics and log (print and write) them to the results file.
        """
        lines = ["\n==== Instance Metrics Summary ===="]
        for key, val in self.metrics.items():
            if isinstance(val, dict):
                lines.append(f"{key}:")
                for sub_key, sub_val in val.items():
                    lines.append(f"  {sub_key}: {sub_val:.6f}")
            else:
                lines.append(f"{key}: {val:.6f}")
        text = "\n".join(lines)
        print(text)
        with open(os.path.join("..", self.sim_ctx.pathres, run_config.resfile), "a") as f:
            f.write(text + "\n")

    def _append_to_file(self, text):
        """Helper method to append text to the results file."""
        with open(os.path.join("..", self.sim_ctx.pathres, run_config.resfile), "a") as f:
            f.write(text + "\n")

    def next_initial_conditions(self):
        # -------------------------------------------------
        # Next Initial Conditions
        # -------------------------------------------------
        instance = self.instance
        sc = self.sim_ctx
        # Retrieve the results of the closest scenario as the next starting point
        SOCini_next = value(instance.socV[max(instance.T0), int(value(instance.sOR))])

        # Update the Pyomo model's initial SOC value
        instance.SOCini = SOCini_next

        # Log the new initial conditions
        with open(os.path.join("..", sc.pathres, run_config.resfile), "a") as res_log:
            res_log.write("\nNew initial conditions:\n")
            res_log.write(f"SOCini: {SOCini_next}\n")
            res_log.write(f"sOR: {value(instance.sOR)}\n")

        # Print new initial conditions to console
        print(f"New Initial Conditions:")
        print(f"SOCini: {SOCini_next}, sOR: {value(instance.sOR)}")

    def compute_instance(self):
        #self.find_closest_dam_scenario()
        self.compute_scenario_cluster()
        self.compute_expected_scenario_cluster()
        self.compute_power_outputs()
        self.compute_instance_cardinality()
        self.compute_nearest_tree()
        self.compute_representative_scenarios()
        self.compute_imbalance_bounds()
        self.compute_market_prices()
        self.compute_mean_market_prices()
        self.compute_imbalance_prices()
        self.log_metrics()



