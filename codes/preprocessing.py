import os
import math
import time
import pyomo.environ as pyo
from pyomo.environ import DataPortal, value, SolverFactory
#from codes.ec_run import lD_preserved
from ec_model import model as abstract_model
import config_definition as config

class PreProcessor:
    def __init__(self, sim_ctx):
        self.sim_ctx = sim_ctx
        self.scenario_data = DataPortal()

        self.S_preserved = None

    def prepare_scenario_data(self):
        sc = self.sim_ctx
        # Print messages like AMPL:
        print("\n########################")
        print(f"#### Instance {config.probl}-{sc.sim}")
        print("########################\n")

        print(f"scenfile path = {config.pathscen}{sc.scenfile}")
        print(f"pathres        = {sc.pathres}")

        print(f"demfile path   = {config.pathdem}{sc.demfile}")
        print(f"pathres        = {sc.pathres}")


        # Load the "base" data
        self.scenario_data.load(filename=os.path.join("..", "data", config.market_datfile), model=abstract_model)
        self.scenario_data.load(filename=os.path.join("..", "data", config.BESS_datfile), model=abstract_model)
        self.scenario_data.load(filename=os.path.join("..", "data", config.wind_datfile), model=abstract_model)

        # Then load scenario & demand data
        self.scenario_data.load(filename=os.path.join("..", config.pathscen, sc.scenfile), model=abstract_model)
        self.scenario_data.load(filename=os.path.join("..", config.pathdem, sc.demfile), model=abstract_model)


        print(f"\nT = {self.scenario_data['nT']}, nS = {self.scenario_data['nS']}, nIM = {self.scenario_data['nIM']}")


    def preprocess_data(self):
        "Before creating the instance"
        # Some Data Preprocess needed before creating the instance because these values are used to build sets in model.py, so they must be defined before creating the instance

        sc = self.sim_ctx

        ### S and Prob allocation (S is used in a lot of sets definition in ec_model.py, so it must be known before creating the instance, prob is used in the objective function)
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


    def allocate_lr_and_ld(self):

        ### lD allocation (necessary to define Ssd set in ec_model.py which is necessary to build bidding curves)
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

    def find_closest_dam_scenario(self):
        best_s, best_d = None, 1e20


        #ToDo: replace hardcoded scenarios
        for s in self.S_preserved:
            d = math.sqrt(sum((self.scenario_data.data()["lD"][rv, s] - config.DA_PRICE_OBS[rv] )**2 for rv in
                          range(1, int(self.scenario_data["nT"]) +1 )))

            if d < best_d:
                best_s, best_d = s, d

        c_dict = self.scenario_data.data()["c"]  # {(sg,k): [leaf IDs]}
        x=2

        kRM = None
        for (sg, k), cluster in c_dict.items():
            if sg == 1 and best_s in cluster:  # stage‑2 node whose cluster contains best_s
                kRM = k
                break
        self.scenario_data.data()["kRM"] = kRM


    def update_proabilities(self):
        """
         Considering that we now found the cluster that contains the scenarios,
         that are descendents of the closest DAM scenario, we can set the probabilities
         of the other ones to 0
         """

        c_dict = self.scenario_data.data()["c"]
        kRM = self.scenario_data.data()["kRM"]
        cluster_closest_to_real_dam = c_dict[(1, kRM)]

        self.scenario_data.data()["S"] = {None: cluster_closest_to_real_dam}
        self.S_preserved = cluster_closest_to_real_dam

        """
        for s in self.scenario_data.data()["S"][None]:
            if s not in cluster_closest_to_real_dam:
                self.scenario_data.data()["Prob"][s]= 0
        """
        for s, P in self.scenario_data.data()["Prob"].items():
            if s not in cluster_closest_to_real_dam:
                self.scenario_data.data()["Prob"][s] = 0



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

    def run_preprocessing(self):
        self.prepare_scenario_data()
        self.preprocess_data()
        self.allocate_lr_and_ld()
        self.find_closest_dam_scenario()
        self.update_proabilities()
        self.update_clusters()
        return self.scenario_data