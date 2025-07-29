import os
import math
from pyomo.environ import DataPortal, value, SolverFactory
import config_definition as config
from previous_results_loader import PreviousMarketResultsLoader
import importlib

class PreProcessor:
    def __init__(self, sim_ctx):
        self.sim_ctx = sim_ctx
        self.scenario_data = DataPortal()
        self.abstract_model = self.load_model()
        self.S_preserved = None

    def load_model(self):
        module_name = f"models.ec_{self.sim_ctx.market}_model"
        mdl = importlib.import_module(module_name)
        return mdl.model

    def prepare_scenario_data(self):
        sc = self.sim_ctx
        # Print messages like AMPL:
        print("\n########################")
        print(f"#### Instance {config.probl}-{sc.sim}")
        print(f"#### of Market {self.sim_ctx.market}")
        print("########################\n")

        print(f"scenfile path = {self.sim_ctx.pathscen}{sc.scenfile}")
        print(f"pathres        = {sc.pathres}")

        print(f"demfile path   = {config.pathdem}{sc.demfile}")
        print(f"pathres        = {sc.pathres}")

        abstract_model = self.abstract_model
        # Load the "base" data
        #ToDo: Should these be loaded according to market?
        self.scenario_data.load(filename=os.path.join("..", "data", config.market_datfile), model=abstract_model)
        self.scenario_data.load(filename=os.path.join("..", "data", config.BESS_datfile), model=abstract_model)
        self.scenario_data.load(filename=os.path.join("..", "data", config.wind_datfile), model=abstract_model)

        # Then load scenario & demand data
        self.scenario_data.load(filename=os.path.join("..", self.sim_ctx.pathscen, sc.scenfile), model=abstract_model)
        #ToDo: demand data should also be loaded according  to  market?
        self.scenario_data.load(filename=os.path.join("..", config.pathdem, sc.demfile), model=abstract_model)


        print(f"\nT = {self.scenario_data['nT']}, nS = {self.scenario_data['nS']}, nIM = {self.scenario_data['nIM']}")


    def preprocess_data(self):
        "Before creating the instance"
        # Some Data Preprocess needed before creating the instance because these values are used to build sets in model.py, so they must be defined before creating the instance

        sc = self.sim_ctx

        ### S and Prob allocation (S is used in a lot of sets definition in ec_DA_model.py, so it must be known before creating the instance, prob is used in the objective function)
        Prob0_raw = self.scenario_data.data().get("Prob0", {})  # Extract raw probabilities
        # Compute number of preserved scenarios BEFORE creating the instance
        self.S_preserved = [s for s in Prob0_raw if Prob0_raw[s] > 0]
        Prob_preserved = {s: Prob0_raw[s] for s in self.S_preserved}
        print(f"Probabilities at Day {sc.sim}: {Prob_preserved}")
        print(f"Preserved Scenarios (S): {self.S_preserved}")
        print(f"Sum of Probabilities: {sum(Prob_preserved.values())}")
        # Inject `S_preserved` and `Prob_preserved` into `scenario_data`
        self.scenario_data.data()["S"] = {None: self.S_preserved}  # Ensure correct S
        self.scenario_data.data()["Prob"] = Prob_preserved  # Assign Probabilities correctly


    def allocate_ld(self):

        ### lD allocation (necessary to define Ssd set in ec_DA_model.py which is necessary to build bidding curves)
        # Scen values are needed to define lD values
        Scen0_raw = self.scenario_data.data().get("Scen0", {})  # Extract full scenario data
        # Compute preserved scenarios BEFORE creating the instance
        Scen_preserved = {}
        nRV_value = sum(self.scenario_data.data()["nRVSG"].values())
        # Only keep `Scen0` values that belong to preserved scenarios
        for rv in range(1, nRV_value + 1):  # Loop over random variables
            for s in self.S_preserved:
                Scen_preserved[(rv, s)] = Scen0_raw.get((rv, s), 0.0)  # Default to 0.0 if missing
        # Inject preserved `Scen` values before `create_instance()`
        self.scenario_data.data()["Scen"] = Scen_preserved
        # Extract `lD` values
        lD_preserved = {}
        for t in range(1, self.scenario_data["nT"] + 1):  # Iterate over T
            for s in self.S_preserved:  # Only for preserved scenarios
                lD_preserved[(t, s)] = self.scenario_data.data().get("Scen", {}).get((t, s),
                                                                                0.0)  # Default to 0.0 if missing
        self.scenario_data.data()["lD"] = lD_preserved  # Assign `lD` values

    #def allocate_lr(self):
        #same thing for lR:
        # --- figure out the first RV of stage‑2 -----------------------------
        nRVSG1_dict = self.scenario_data.data().get("nRVSG", {})
        nRVSG1 = nRVSG1_dict.get(1, 0)  # RVs in stage‑1
        rv0_RM = 1 + int(nRVSG1)  # first RM RV index

        # --- copy 24 reserve‑market prices to lR ----------------------------
        lR_preserved = {}
        nT = int(self.scenario_data["nT"])
        for t in range(1, nT + 1):
            rv = rv0_RM + (t - 1)  # row that holds RM price for hour t
            for s in self.S_preserved:  # or self.scenario_data["S0"]
                price = self.scenario_data.data()["Scen"].get((rv, s), 0.0)
                lR_preserved[(t, s)] = float(price)

        self.scenario_data.data()["lR"] = lR_preserved

        #lI
        # --- figure out the first RV of stage‑2 -----------------------------
        nRVSG2_dict = self.scenario_data.data().get("nRVSG", {})
        nRVSG2 = nRVSG2_dict.get(2, 0)  # RVs in stage‑2
        rv0_IM = nRVSG1 + int(nRVSG2)  # first IM1 RV index

        # --- copy 24 IM1 prices to lI ----------------------------
        lI_preserved = {}
        nT = int(self.scenario_data["nT"])
        for i in range(1, self.scenario_data["nIM"] + 1):
            for t in range(1, nT + 1):
                rv = rv0_IM + (t - 1)  # row that holds IM price for hour t
                for s in self.S_preserved:  # or self.scenario_data["S0"]
                    price = self.scenario_data.data()["Scen"].get((rv, s), 0.0)
                    lI_preserved[(i,t, s)] = float(price)

        self.scenario_data.data()["lI"] = lI_preserved

    def find_closest_dam_scenario(self):
        best_s, best_d = None, 1e20

        for s in self.S_preserved:
            d = math.sqrt(sum((self.scenario_data.data()["lD"][rv, s] - config.DA_PRICE_OBS[rv] )**2 for rv in
                          range(1, int(self.scenario_data["nT"]) +1 )))

            if d < best_d:
                best_s, best_d = s, d

        c_dict = self.scenario_data.data()["c"]  # {(sg,k): [leaf IDs]}
        x=2

        kRM = None
        for (sg, k), cluster in c_dict.items():
            if sg == 1 and best_s in cluster:  # stage‑1 node whose cluster contains best_s
                kRM = k
                break

        # Filter the cluster to only contain scenarios that exist in S_preserved

        self.scenario_data.data()["kRM"] = kRM

    def update_probabilities_and_scenarios(self):
        """
         Considering that we now found the cluster that contains the scenarios,
         that are descendents of the closest DAM scenario, we can set the probabilities
         of the other ones to 0
         """

        c_dict = self.scenario_data.data()["c"]
        kRM = self.scenario_data.data()["kRM"]
        probs = self.scenario_data.data()["Prob"]
        cluster_closest_to_real_dam = c_dict[(1, kRM)]

        filtered_cluster_closest_to_real_dam = [s for s in cluster_closest_to_real_dam if s in probs.keys()]

        self.scenario_data.data()["S"] = {None: filtered_cluster_closest_to_real_dam}
        self.S_preserved = filtered_cluster_closest_to_real_dam

        """
        for s in self.scenario_data.data()["S"][None]:
            if s not in cluster_closest_to_real_dam:
                self.scenario_data.data()["Prob"][s]= 0
        """
        # Instead of setting the probability to 0, now the elements are removed so that S_preserved and Prob are in line
        prob = self.scenario_data.data()["Prob"]
        for s in list(prob.keys()):  # list(...) makes a snapshot
            if s not in cluster_closest_to_real_dam:
                del prob[s]
        self.scenario_data.data()["Prob"] = prob

        # Now, Rescale the probabilities
        sum_prob = sum(self.scenario_data.data()["Prob"].values())
        for s in self.scenario_data.data()["Prob"]:
            self.scenario_data.data()["Prob"][s] /= sum_prob


    def update_clusters(self):
        trimmed = {}
        for (sg, k), cluster in self.scenario_data.data()["c"].items():
            # cluster was a Python list of leaf IDs
            trimmed[(sg, k)] = [leaf for leaf in cluster if leaf in self.scenario_data.data()["S"][None]]
        self.scenario_data.data()["c"] = trimmed

    def truncate_remaining_vars(self):
        # 1) grab the raw Scen0 table
        Scen0_raw = self.scenario_data.data()["Scen0"]
        # total # of random variables (over *all* stages)
        nRV_total = sum(self.scenario_data.data()["nRVSG"].values())

        # 2) trim to only those scenarios we kept after DAM

        Scen_trim = {
            (rv, s): Scen0_raw.get((rv, s), 0.0)
            for rv in range(1, nRV_total + 1)
            for s in self.S_preserved
        }
        self.scenario_data.data()["Scen"] = Scen_trim

        # 3) figure out where the DA block lives:
        rv0_DA = 1  # by convention Pyomo stages start RV 1 at DA
        n_DA = int(self.scenario_data.data()["nRVSG"][1])
        # 4) build lD from that slice of Scen_trim
        lD = {}
        for t in range(1, int(self.scenario_data["nT"]) + 1):
            rv = rv0_DA + (t - 1)
            for s in self.S_preserved:
                lD[(t, s)] = float(Scen_trim.get((rv, s), 0.0))
        self.scenario_data.data()["lD"] = lD

        # 5) and the RM block immediately follows DA in RV‐space
        rv0_RM = rv0_DA + n_DA
        lR = {}
        for t in range(1, int(self.scenario_data["nT"]) + 1):
            rv = rv0_RM + (t - 1)
            for s in self.S_preserved:
                lR[(t, s)] = float(Scen_trim.get((rv, s), 0.0))
        self.scenario_data.data()["lR"] = lR

    def run_preprocessing(self):


        """
        Should we redo the clusters so that the scenarios that are no longer in S_preserved are removed?
        """

        self.prepare_scenario_data()
        self.preprocess_data()
        #self.allocate_lr_and_ld()
        self.allocate_ld()
        #self.allocate_lr()
        self.scenario_data = PreviousMarketResultsLoader(self.sim_ctx, self.scenario_data).load_results()
        #self.find_closest_dam_scenario() These two are also commented out bc hopefully not needed bc of Cristian
        #self.update_probabilities_and_scenarios()
        #self.update_clusters()  I think this is already done in instancemanager
        #self.truncate_remaining_vars()
        return self.scenario_data, self.abstract_model