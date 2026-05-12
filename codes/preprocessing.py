import os
import math
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
        print("\n########################")
        print(f"#### Instance {cfg.probl}-{sc.sim}")
        print(f"#### of Market {self.sim_ctx.market}")
        print("########################\n")

        print(f"scenfile path = {self.sim_ctx.pathscen}{sc.scenfile}")
        print(f"pathres        = {sc.pathres}")

        print(f"demfile path   = {cfg.pathdem}{sc.demfile}")
        print(f"pathres        = {sc.pathres}")

        abstract_model = self.abstract_model
        self.scenario_data.load(filename=os.path.join(cfg.PROJECT_ROOT, "data", cfg.market_datfile), model=abstract_model)
        self.scenario_data.load(filename=os.path.join(cfg.PROJECT_ROOT, "data", cfg.BESS_datfile), model=abstract_model)
        self.scenario_data.load(filename=os.path.join(cfg.PROJECT_ROOT, "data", cfg.wind_datfile), model=abstract_model)
        if self.sim_ctx.include_hydro:
            self.scenario_data.load(filename=os.path.join(cfg.PROJECT_ROOT, "data", cfg.hydro_datfile), model=abstract_model)
            self.scenario_data.load(filename=os.path.join(cfg.PROJECT_ROOT, cfg.pathdem_h2, sc.demfile_h2), model=abstract_model)

        self.scenario_data.load(filename=os.path.join(cfg.PROJECT_ROOT, sc.pathscen, sc.scenfile), model=abstract_model)
        self.scenario_data.load(filename=os.path.join(cfg.PROJECT_ROOT, cfg.pathdem, sc.demfile), model=abstract_model)

        print(f"\nT = {self.scenario_data['nT']}, nS = {self.scenario_data['nS']}, nIM = {self.scenario_data['nIM']}")

    def preprocess_data(self):
        sc = self.sim_ctx

        Prob0_raw = self.scenario_data.data().get("Prob0", {})
        self.S_preserved = [s for s in Prob0_raw if Prob0_raw[s] > 0]
        Prob_preserved = {s: Prob0_raw[s] for s in self.S_preserved}
        print(f"Probabilities at Day {sc.sim}: {Prob_preserved}")
        print(f"Preserved Scenarios (S): {self.S_preserved}")
        print(f"Sum of Probabilities: {sum(Prob_preserved.values())}")
        self.scenario_data.data()["S"] = {None: self.S_preserved}
        self.scenario_data.data()["Prob"] = Prob_preserved

    def _stage_first_rv(self, stage):
        nrvsg = self.scenario_data.data().get("nRVSG", {})
        return 1 + sum(int(nrvsg.get(sg, 0)) for sg in range(1, int(stage)))

    def _stage_quarter_rv(self, stage, t, q, first_t=1):
        nQ = int(self.scenario_data["nQ"])
        hour_offset = int(t) - int(first_t)
        return self._stage_first_rv(stage) + hour_offset * nQ + (int(q) - 1)

    def allocate_market_prices(self):
        scen0_raw = self.scenario_data.data().get("Scen0", {})
        scen_preserved = {}
        nRV_value = sum(self.scenario_data.data()["nRVSG"].values())
        for rv in range(1, nRV_value + 1):
            for s in self.S_preserved:
                scen_preserved[(rv, s)] = scen0_raw.get((rv, s), 0.0)
        self.scenario_data.data()["Scen"] = scen_preserved

        nT = int(self.scenario_data["nT"])
        nQ = int(self.scenario_data["nQ"])

        lD_preserved = {}
        for t in range(1, nT + 1):
            for q in range(1, nQ + 1):
                rv = self._stage_quarter_rv(1, t, q)
                for s in self.S_preserved:
                    lD_preserved[(t, q, s)] = float(self.scenario_data.data()["Scen"].get((rv, s), 0.0))
        self.scenario_data.data()["lD"] = lD_preserved

        lR_preserved = {}
        for t in range(1, nT + 1):
            for q in range(1, nQ + 1):
                rv = self._stage_quarter_rv(2, t, q)
                for s in self.S_preserved:
                    lR_preserved[(t, q, s)] = float(self.scenario_data.data()["Scen"].get((rv, s), 0.0))
        self.scenario_data.data()["lR"] = lR_preserved

        im_stage_map = self.scenario_data["sgim"]
        lI_preserved = {}
        for i in range(1, int(self.scenario_data["nIM"]) + 1):
            first_t = min(self.scenario_data["TIM"][i])
            for t in self.scenario_data["TIM"][i]:
                for q in range(1, nQ + 1):
                    rv = self._stage_quarter_rv(im_stage_map[i], t, q, first_t=first_t)
                    for s in self.S_preserved:
                        lI_preserved[(i, t, q, s)] = float(self.scenario_data.data()["Scen"].get((rv, s), 0.0))
        self.scenario_data.data()["lI"] = lI_preserved

        ib_stage = self.scenario_data["nSG"]
        ib_block_size = nT * nQ
        ib_stage_rvs = int(self.scenario_data.data()["nRVSG"].get(ib_stage, 0))
        if ib_stage_rvs < 2 * ib_block_size:
            raise ValueError(
                f"Stage {ib_stage} must contain at least {2 * ib_block_size} IB price RVs "
                f"({ib_block_size} for lPIB and {ib_block_size} for lNIB), found {ib_stage_rvs}."
            )
        lPIB_preserved = {}
        lNIB_preserved = {}
        for t in range(1, nT + 1):
            for q in range(1, nQ + 1):
                rv_lpib = self._stage_quarter_rv(ib_stage, t, q)
                rv_lnib = rv_lpib + ib_block_size
                for s in self.S_preserved:
                    lPIB_preserved[(t, q, s)] = float(self.scenario_data.data()["Scen"].get((rv_lpib, s), 0.0))
                    lNIB_preserved[(t, q, s)] = float(self.scenario_data.data()["Scen"].get((rv_lnib, s), 0.0))
        self.scenario_data.data()["lPIB"] = lPIB_preserved
        self.scenario_data.data()["lNIB"] = lNIB_preserved

        # En allocate_market_prices, después de calcular lIB_preserved
        sample_times = [t for t in [1, 12, 24] if t <= nT]
        sample_scenarios = self.S_preserved[:3]
        sample_lPIB = [(t, q, s, lPIB_preserved[(t, q, s)])
                       for t in sample_times for q in [1] for s in sample_scenarios]
        sample_lNIB = [(t, q, s, lNIB_preserved[(t, q, s)])
                       for t in sample_times for q in [1] for s in sample_scenarios]
        print("lPIB sample values:", sample_lPIB)
        print("lNIB sample values:", sample_lNIB)

        # Y también para lD para comparar
        sample_lD = [(t, q, s, lD_preserved[(t, q, s)])
                    for t in sample_times for q in [1] for s in sample_scenarios]
        print("lD sample values:", sample_lD)

    def run_preprocessing(self):
        """
        Should we redo the clusters so that the scenarios that are no longer in S_preserved are removed?
        """
        self.prepare_scenario_data()
        self.preprocess_data()
        self.allocate_market_prices()
        self.scenario_data = PreviousMarketResultsLoader(self.sim_ctx, self.scenario_data).load_results()
        return self.scenario_data, self.abstract_model
