import os
import math
import tempfile
from pyomo.environ import DataPortal, value, SolverFactory
import config_definition as cfg
from previous_results_loader import PreviousMarketResultsLoader
import importlib
import re
from model_builder import ModelBuilder

class PreProcessor:
    def __init__(self, sim_ctx):
        self.sim_ctx = sim_ctx
        self.scenario_data = DataPortal()
        self.abstract_model = self.load_model()
        self.S_preserved = None

    def load_model(self):
        """

        if self.sim_ctx.include_hydro:
            module_name = f"models.ec_{self.sim_ctx.market}_hydrogen_model"
        else:
            module_name = f"models.ec_{self.sim_ctx.market}_model"
        mdl = importlib.import_module(module_name)

        return mdl.model
        """
        builder = ModelBuilder(self.sim_ctx)
        model = builder.build_model()
        return model

    def prepare_scenario_data(self):
        sc = self.sim_ctx
        # Print messages like AMPL:
        print("\n########################")
        print(f"#### Instance {cfg.probl}-{sc.sim}")
        print(f"#### of Market {self.sim_ctx.market}")
        print("########################\n")

        print(f"scenfile path = {self.sim_ctx.pathscen}{sc.scenfile}")
        print(f"pathres        = {sc.pathres}")

        print(f"demfile path   = {cfg.pathdem}{sc.demfile}")
        print(f"pathres        = {sc.pathres}")

        abstract_model = self.abstract_model
    
        # Load market data
        market_file = os.path.join(cfg.PROJECT_ROOT, "data", cfg.market_datfile)
        print(f"[1/6] Loading market.dat from: {market_file}")
        try:
            self.scenario_data.load(filename=market_file, model=abstract_model)
            print(f"      ✓ Success")
        except Exception as e:
            print(f"      ✗ FAILED: {e}")
            raise
        
        # Load BESS data
        bess_file = os.path.join(cfg.PROJECT_ROOT, "data", cfg.BESS_datfile)
        print(f"[2/6] Loading BESS.dat from: {bess_file}")
        try:
            self.scenario_data.load(filename=bess_file, model=abstract_model)
            print(f"      ✓ Success")
        except Exception as e:
            print(f"      ✗ FAILED: {e}")
            raise
        
        # Load wind data
        wind_file = os.path.join(cfg.PROJECT_ROOT, "data", cfg.wind_datfile)
        print(f"[3/6] Loading wind.dat from: {wind_file}")
        try:
            self.scenario_data.load(filename=wind_file, model=abstract_model)
            print(f"      ✓ Success")
        except Exception as e:
            print(f"      ✗ FAILED: {e}")
            raise
        
        # Load hydro data (if enabled)
        if self.sim_ctx.include_hydro:
            hydro_file = os.path.join(cfg.PROJECT_ROOT, "data", cfg.hydro_datfile)
            print(f"[4a/6] Loading hydro.dat from: {hydro_file}")
            try:
                self.scenario_data.load(filename=hydro_file, model=abstract_model)
                print(f"       ✓ Success")
            except Exception as e:
                print(f"       ✗ FAILED: {e}")
                raise
            
            h2_file = os.path.join(cfg.PROJECT_ROOT, cfg.pathdem_h2, sc.demfile_h2)
            print(f"[4b/6] Loading demand_h2.dat from: {h2_file}")
            try:
                self.scenario_data.load(filename=h2_file, model=abstract_model)
                print(f"       ✓ Success")
            except Exception as e:
                print(f"       ✗ FAILED: {e}")
                raise
        
        # Load scenario data
        scen_file = os.path.join(cfg.PROJECT_ROOT, sc.pathscen, sc.scenfile)
        print(f"[5/6] Loading scenarios from: {scen_file}")
        print(f"      File exists: {os.path.exists(scen_file)}")
        try:
            load_path = self._prepare_pyomo_compatible_scenario_file(scen_file)
            self.scenario_data.load(filename=load_path, model=abstract_model)
            print(f"      ✓ Success")
        except Exception as e:
            print(f"      ✗ FAILED at scenario loading:")
            print(f"      Error: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            raise
        
        # Load demand data
        dem_file = os.path.join(cfg.PROJECT_ROOT, cfg.pathdem, sc.demfile)
        print(f"[6/6] Loading demand from: {dem_file}")
        print(f"      File exists: {os.path.exists(dem_file)}")
        try:
            self.scenario_data.load(filename=dem_file, model=abstract_model)
            print(f"      ✓ Success")
        except Exception as e:
            print(f"      ✗ FAILED: {e}")
            import traceback
            traceback.print_exc()
            raise

        print(f"\n✓ All files loaded successfully")

    def preprocess_data(self):
        # Before creating the instance
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


    def allocate_market_prices(self):

        ### lD allocation (necessary to define Ssd set in ec_DA_model.py which is necessary to build bidding curves)
        # Scen values are needed tof define lD values
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

        #lI
        # --- figure out the first RV of stage‑2 -----------------------------
        nRVSG_dict = self.scenario_data.data().get("nRVSG", {})  # maps stage -> num RVs

        # Define the stage where each IM level starts
        IM_stage_map = self.scenario_data["sgim"]  # example: IM1 at stage 3, IM2 at stage 9, IM3 at stage 15
        # --- copy 24 IM1 prices to lI ----------------------------
        lI_preserved = {}
        nT = int(self.scenario_data["nT"])
        for t in range(1, nT + 1):
            for i in self.scenario_data["IMT"][t]:
                rv0_IM = sum(int(nRVSG_dict.get(i, 0)) for i in range(1, IM_stage_map[i]))  + 1
                rv = rv0_IM + (t - 1)  # row that holds IM price for hour t
                for s in self.S_preserved:  # or self.scenario_data["S0"]
                    price = self.scenario_data.data()["Scen"].get((rv, s), 0.0)
                    lI_preserved[(i,t, s)] = float(price)

        self.scenario_data.data()["lI"] = lI_preserved


    def run_preprocessing(self):
        """
        Should we redo the clusters so that the scenarios that are no longer in S_preserved are removed?
        """
        self.prepare_scenario_data()
        self.preprocess_data()
        self.allocate_market_prices()
        self.scenario_data = PreviousMarketResultsLoader(self.sim_ctx, self.scenario_data).load_results()
        return self.scenario_data, self.abstract_model

    @staticmethod
    def _prepare_pyomo_compatible_scenario_file(scen_file):
        """
        Normalize 1-D wildcard param declarations that recent Pyomo versions
        can fail to parse in .dat files.
        """
        with open(scen_file, "r", encoding="utf-8") as f:
            raw_text = f.read()

        normalized_text = (
            raw_text.replace("param nRVSG [*] :=", "param nRVSG :=")
            .replace("param ScenF [*] :=", "param ScenF :=")
            .replace("param ScenO [*] :=", "param ScenO :=")
        )

        if normalized_text == raw_text:
            return scen_file

        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".dat", delete=False, encoding="utf-8"
        )
        with tmp:
            tmp.write(normalized_text)
        return tmp.name
