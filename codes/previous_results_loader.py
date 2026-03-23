from pyomo.environ import value
import config_definition as config
from pyomo.environ import DataPortal
import os
import bisect
from pathlib import Path
from simulation_context import prev_market
import re
class PreviousMarketResultsLoader:
    """
    Loading the results of the previous run
    The path for where the results are stored is already in config_definiton
    """

    def __init__(self, sim_ctx, scen_data):
        self.sim_ctx = sim_ctx
        self.scenario_data = scen_data
        self.S_preserved = self.scenario_data.data()["S"][None]  #This is kept for naming convention
        self.previous_vars = None

    @staticmethod
    def read_from_txt(filename, socv=False):
        """
        Generic function to read the results of the previous run. For files that are structured
        scen_no | probability | values
        """
        # initialize empty structure
        data = {}#{t: {} for t in range(1, 25)}
        scenarios = []
        with open(f'{filename}.txt') as f:
            for lineno, line in enumerate(f, start=1):
                parts = line.strip().split()
                if not parts:
                    continue  # skip empty lines
                s = int(parts[0])  # scenario index
                scenarios.append(s)
                values = list(map(float, parts[2:]))  # drop parts[1]=probability
                if socv:
                    for t, v in enumerate(values, start=0):
                        data[(t, s)] = v
                    continue
                if len(values) != 24:
                    raise ValueError(
                        f"Line {lineno}: expected 24 values after the probability, "
                        f"but got {len(values)} for scenario {s}"
                    )
                for t, v in enumerate(values, start=1):
                    data[(t, s)] = v

        return data, scenarios

    @staticmethod
    def get_sorted_bid_curve(ld,S, t, ascending = True):
        price_scen_pairs = [(value(ld[t, s]), s) for s in S]
        return sorted(price_scen_pairs, key=lambda x: x[0], reverse=not ascending)

    @staticmethod
    def get_interseption(lD, real_price, buying, S):
        closest_scenario = None
        if buying:
            counter = 0
            while lD[counter][0] >= real_price:
                if counter == len(S) - 1:
                    break
                counter = counter+1
                closest_scenario = lD[counter][1]
        else: #selling
            counter = 0
            while lD[counter][0] <= real_price:
                if counter == len(S) - 1:
                    break
                counter = counter+1
                closest_scenario = lD[counter][1]

        if closest_scenario == None:
            pass
        return  closest_scenario

    def load_dam_results(self, market="RM"):

        """
        This function loads the DAM results, meaning the bid pairs of energy and price, and using those, calculates
        the matched energy of the DAM, finding the scenarios, inbetween which the real price is, and depending on
        buying or selling, picks the conservative scenario.
        """

        #parent_path = self.sim_ctx.previous_results_path
        #parent_path = os.path.join(config.PROJECT_ROOT, parent_path)

        parent_path = Path(config.PROJECT_ROOT) / config.base_result_dir / config.famscen_all / "DA" / "market" / self.sim_ctx.sim / "DA"
        e_da_m_from_DAM_run, S = self.read_from_txt(parent_path / "eDA_m")
        e_da_p_from_DAM_run, _ = self.read_from_txt(parent_path / "eDA_p")
        ld_from_DAM_run, _ = self.read_from_txt(parent_path / "lD")
        ieDA_m_from_DAM_run, _ = self.read_from_txt(parent_path / "ieDA_m")
        ieDA_p_from_DAM_run, _ = self.read_from_txt(parent_path / "ieDA_p")

        # ToDo: Discuss if we want to go with the simple approach above or use what I am sketching out below so the
        # variables for each market are defined in the config and read into a dictionary instead of being defined here
        """
        dam_results = {}
        # Read and store values
        for var_name, file_suffix in self.previous_vars.items():
            dam_results[var_name], _ = self.read_from_txt(parent_path + "/" + file_suffix)

        # Special handling if one of them also returns a second value you need:
        dam_results["e_da_m_from_DAM_run"], S = self.read_from_txt(parent_path + "/eDA_m")
        """
        e_da_m_matched = {}
        e_da_p_matched = {}
        ieDA_m = {}
        ieDA_p = {}
        for t in range(1, self.scenario_data["nT"] + 1):
            real_price = self.scenario_data["lD"][t,self.S_preserved[0]] # scenario doesn't matter

            sorted_bid_curve = self.get_sorted_bid_curve(ld_from_DAM_run, S, t)
            # There are 5 cases that can occur:
            # Edge case: price is exactly equal to one of the bids (highly unlikely)
            if real_price in [i[0] for i in sorted_bid_curve]:
                s = [i[1] for i in sorted_bid_curve if i[0] == real_price][0]
                e_da_m_matched[t] = e_da_m_from_DAM_run[t,s]
                e_da_p_matched[t] = e_da_p_from_DAM_run[t,s]
                continue

            closest_lambda_plus = None
            closest_lambda_minus = None


            # 1: the real price is below the lowest price of the bid curve -> buy everything
            if sorted_bid_curve[0][0] > real_price:
                closest_lambda_plus = sorted_bid_curve[0][1]
                e_da_m_matched[t] = e_da_m_from_DAM_run[t,closest_lambda_plus]
                e_da_p_matched[t] = 0
                continue
            # 2: The real price is above the highest price of the bid curve -> buy nothing, sell everything
            if sorted_bid_curve[-1][0] < real_price:
                closest_lambda_minus = sorted_bid_curve[-1][1]
                e_da_p_matched[t] = e_da_p_from_DAM_run[t,closest_lambda_minus]
                e_da_m_matched[t] = 0
                continue

            # 3: the real price is somewhere inbetween the bid curve:
            else:
                i = 0
                while sorted_bid_curve[i][0] < real_price:
                    closest_lambda_plus = sorted_bid_curve[i+1][1]
                    closest_lambda_minus = sorted_bid_curve[i][1]
                    i = i + 1


            # Now we need to find out if we buy or sell
            if closest_lambda_minus and closest_lambda_plus:

                buying_lambda_minus = e_da_m_from_DAM_run[t, closest_lambda_minus]
                buying_lambda_plus = e_da_m_from_DAM_run[t, closest_lambda_plus]
                if (buying_lambda_plus > 0) and (buying_lambda_minus > 0):
                    e_da_m_matched[t] = e_da_m_from_DAM_run[t, closest_lambda_plus]
                    e_da_p_matched[t] = 0
                else:
                    x=1

                selling_lambda_minus = e_da_p_from_DAM_run[t, closest_lambda_minus]
                selling_lambda_plus = e_da_p_from_DAM_run[t, closest_lambda_plus]
                if (selling_lambda_plus > 0) and (selling_lambda_minus > 0):
                    e_da_p_matched[t] = e_da_p_from_DAM_run[t, closest_lambda_minus]
                    e_da_m_matched[t] = 0

                if buying_lambda_plus + selling_lambda_minus == 0:
                    #nothing matched
                    e_da_p_matched[t] = 0
                    e_da_m_matched[t] = 0


            # Final scenario: unmatched
            if ieDA_m_from_DAM_run[t, closest_lambda_minus] + ieDA_m_from_DAM_run[t, closest_lambda_minus] + \
                    ieDA_p_from_DAM_run[t, closest_lambda_plus] + ieDA_p_from_DAM_run[t, closest_lambda_plus] == 0:
                # No block was accepted in either neighboring price → real_price was outside the curve.
                e_da_p_matched[t] = 0
                e_da_m_matched[t] = 0

        e_da_m = {}
        e_da_p = {}
        for t in range(1, self.scenario_data["nT"] + 1):
            for q in range(1, self.scenario_data["nQ"] + 1):
                for s in self.S_preserved:
                    e_da_m[(t, q, s)] = e_da_m_matched[t]
                    e_da_p[(t, q, s)] = e_da_p_matched[t]
                    ieDA_p[(t, q, s)] = ieDA_p_from_DAM_run[t,S[0]] # Because the values are the same for all scenarios of DA in the RM data
                    ieDA_m[(t, q, s)] = ieDA_m_from_DAM_run[t,S[0]]
        self.scenario_data["eDA_p"] = e_da_p
        self.scenario_data["eDA_m"] = e_da_m
        self.scenario_data["ieDA_p"] = ieDA_p
        self.scenario_data["ieDA_m"] = ieDA_m
        #return self.scenario_data


    def load_rm_results(self):
        """
        Function to load the RM results for the IM1 model to run
        """
        #parent_path = self.sim_ctx.previous_results_path  #f'{config.dam_results_folder}/market/{self.sim_ctx.sim}/DA'
        #parent_path = os.path.join(config.PROJECT_ROOT, parent_path)
        parent_path = Path(config.PROJECT_ROOT) / config.base_result_dir / config.famscen_all / "RM" / "market" / self.sim_ctx.sim / "RM"
        rU_from_rm_run, S = self.read_from_txt(parent_path / "rU")
        rD_from_rm_run, _ = self.read_from_txt(parent_path/ "rD")
        lR_from_rm_run, _ = self.read_from_txt(parent_path / "lR")

        matched_rU = {}
        matched_rD = {}

        for t in range(1, self.scenario_data["nT"] + 1):

            real_price = self.scenario_data["lR"][t,self.S_preserved[0]] # scenario doesn't matter
            # There is a single price for up and down reserve
            sorted_bid_curve = self.get_sorted_bid_curve(lR_from_rm_run, S, t)
            sorted_bid_curve_prices_only = [i[0] for i in sorted_bid_curve]
            idx = bisect.bisect_right(sorted_bid_curve_prices_only, real_price) - 1  # last price ≤ real
            if idx >= 0:
                scenario = sorted_bid_curve[idx][1]
                matched_rU[t] = rU_from_rm_run[t, scenario]
                if abs(matched_rU[t]) < 1e-8:
                    matched_rU[t] = 0
                matched_rD[t] = rD_from_rm_run[t, scenario]
                if abs(matched_rD[t]) < 1e-8:
                    matched_rD[t] = 0

            else:
                matched_rU[t] = 0
                matched_rD[t] = 0
        rU = {}
        rD = {}
        lR_penalty = {}
        for t in range(1, self.scenario_data["nT"] + 1):
            for q in range(1, self.scenario_data["nQ"] + 1):
                for s in self.S_preserved:
                    rU[(t, q, s)] = matched_rU[t]
                    rD[(t, q, s)] = matched_rD[t]
                    lR_penalty[(t, q, s)] = 1.5 * self.scenario_data["lR"][t, q, self.S_preserved[0]] # scenario doesn't matter

        self.scenario_data["rU"] = rU
        self.scenario_data["rD"] = rD
        self.scenario_data["lR_penalty"] = lR_penalty

    @staticmethod
    def matched_volume(one_hour_curve, real_price):

        sells = [(p, sid, v) for p, sid, v in one_hour_curve if v > 0]
        buys = [(p, sid, v) for p, sid, v in one_hour_curve if v < 0]
        buys = sorted(buys, key=lambda x: x[0])
        #  SELL side
        if sells and real_price >= sells[0][0]:  # price high enough
            # bids are sorted ↑ so the last one ≤ P_star is the marginal
            idx = bisect.bisect_right([p for p, _, _ in sells], real_price) - 1
            return sells[idx][2], sells[idx][1]  # (volume, scen)

        # BUY side
        if buys and real_price <= buys[0][0]:  # price low enough
            # buy list is sorted ↓ (highest price first)
            idx = bisect.bisect_left([p for p, _, _ in buys], real_price)
            try:
                return buys[idx][2], buys[idx][1]  # negative volume
            except IndexError:
                print(
                    "DEBUG buys IndexError:",
                    "real_price =", real_price,
                    "prices =", prices,
                    "idx =", idx,
                    "len(buys) =", len(buys),
                    flush=True,
                )

        # no block accepted
        return 0.0, None


    def load_im_results(self):
        # Because eIM is a single constraint for 3 different markets, we need to load in the data into the variable,
        # and then, after creating the instance, fix the previous IM ones for IM2 and IM3
        prev_market_ = prev_market(self.sim_ctx.market)
        parent_path = Path(config.PROJECT_ROOT) / config.base_result_dir / config.famscen_all / prev_market_ / "market" / self.sim_ctx.sim / "IM"
        im_no = re.search(r'\d+', self.sim_ctx.market)[0]
        im_no = int(im_no)


        matched_eim1 = {}
        last_matched_scen = None
        for i in range(1, im_no):
            eIM_from_im1, S = self.read_from_txt(parent_path / f"eIM_{i}")
            lI_from_im1_run, _ = self.read_from_txt(parent_path / f"lI_{i}")
            for t in range(1, self.scenario_data["nT"] + 1):
            #for t in range(12,25):
                real_price = self.scenario_data["lI"][i,t,self.S_preserved[0]] # scenario doesn't matter
                sorted_bid_curve = self.get_sorted_bid_curve(lI_from_im1_run, S, t)
                sorted_bid_curve_prices_only = [i[0] for i in sorted_bid_curve]
                sorted_curve_with_energy = [(lI_from_im1_run[t,s], s, eIM_from_im1[t,s]) for s in S]
                vol,scen = self.matched_volume(sorted_curve_with_energy, real_price)
                if scen and scen !=  (1, None):
                    last_matched_scen = scen
                matched_eim1[i,t] = vol

        eIM_prev = {}
        nQ = 4  # Number of subperiods per hour
        for i in range(1, im_no):
            for t in range(1, self.scenario_data["nT"] + 1):
                for q in range(1, nQ + 1):  # Replicate for each subperiod
                    for s in self.S_preserved:
                        eIM_prev[(i, t, q, s)] = matched_eim1[i,t]
                for s in self.S_preserved:
                    eIM_prev[i,t,s] = matched_eim1[i,t]

        #self.scenario_data["eIM"] = eIM1
        self.sim_ctx.eIM_prev= eIM_prev

        if im_no == 3:

            parent_path = Path(
                config.PROJECT_ROOT) / config.base_result_dir / config.famscen_all / prev_market_ / "market" / self.sim_ctx.sim
            ru_penalty_from_im2, S = self.read_from_txt(parent_path / "RM" / f"rU_penalty")
            rd_penalty_from_im2, _ = self.read_from_txt(parent_path / "RM" / f"rD_penalty")
            rU_B_from_im2, _ = self.read_from_txt(parent_path / "RM" / f"rU_B")
            rD_B_from_im2, _ = self.read_from_txt(parent_path / "RM" / f"rD_B")
            rU_FD_from_im2, _ = self.read_from_txt(parent_path / "RM" / f"rU_FD")
            rD_FD_from_im2, _ = self.read_from_txt(parent_path / "RM" / f"rD_FD")

            pib_p_from_im2, _ = self.read_from_txt(parent_path / "IB" / f"pIB_p")
            pib_m_from_im2, _ = self.read_from_txt(parent_path / "IB" / f"pIB_m")

            parent_path = Path(
                config.PROJECT_ROOT) / config.base_result_dir / config.famscen_all / prev_market_ / "ec" / self.sim_ctx.sim

            var_fd_from_im2, _ = self.read_from_txt(parent_path / "FD" / "var_fd")
            var_afd_p_from_im2, _ = self.read_from_txt(parent_path / "FD" / "var_afd_p")
            var_afd_m_from_im2, _  = self.read_from_txt(parent_path / "FD" / "var_afd_m")
            dv_from_im2, _ = self.read_from_txt(parent_path / "BESS" / f"dV")
            cv_from_im2, _= self.read_from_txt(parent_path / "BESS" / f"cV")
            idv_from_im2, _ = self.read_from_txt(parent_path / "BESS" / f"idV")
            socv_from_im2, _ = self.read_from_txt(parent_path / "BESS" / f"socV", socv=True)

            var_fd = {}
            var_afd_p = {}
            var_afd_m = {}
            dv = {}
            cv = {}
            idv = {}
            socv = {}
            ru_penalty = {}
            rd_penalty = {}
            ru_b = {}
            rd_b = {}
            ru_fd = {}
            rd_fd = {}
            pib_p = {}
            pib_m = {}

            prev_vars = {}

            if last_matched_scen == None:
                last_matched_scen = S[0]
            nQ = 4  # Number of subperiods per hour
            for t in range(1, self.scenario_data["nT"] + 1):
                for q in range(1, nQ + 1):  # Replicate for each subperiod
                    for s in  self.scenario_data["S"]:
                        var_fd[(t, q, s)] = var_fd_from_im2[t, last_matched_scen]
                        var_afd_p[(t, q, s)] = var_afd_p_from_im2[t,last_matched_scen]
                        var_afd_m[(t, q, s)] = var_afd_m_from_im2[t,last_matched_scen]
                        dv[(t, q, s)] = dv_from_im2[t,last_matched_scen]
                        cv[(t, q, s)] = cv_from_im2[t,last_matched_scen]
                        idv[(t, q, s)] = idv_from_im2[t,last_matched_scen]
                        socv[(t, q, s)] = socv_from_im2[t,last_matched_scen]
                        ru_penalty[(t, q, s)] = ru_penalty_from_im2[t,last_matched_scen]
                        rd_penalty[(t, q, s)] = rd_penalty_from_im2[t,last_matched_scen]
                        ru_b[(t, q, s)] = rU_B_from_im2[t,last_matched_scen]
                        rd_b[(t, q, s)] = rD_B_from_im2[t,last_matched_scen]
                        ru_fd[(t, q, s)] = rU_FD_from_im2[t,last_matched_scen]
                        rd_fd[(t, q, s)] = rD_FD_from_im2[t,last_matched_scen]
                        pib_p[(t, q, s)] = pib_p_from_im2[t,last_matched_scen]
                        pib_m[(t, q, s)] = pib_m_from_im2[t,last_matched_scen]

            #special case for socv because it is defined from 0-24:
            for s in self.scenario_data["S"]:
                socv[(0, 0, s)] = socv_from_im2[0,S[0]]

            prev_vars["var_fd"] = var_fd
            prev_vars["var_afd_p"] = var_afd_p
            prev_vars["var_afd_m"] = var_afd_m
            prev_vars["dv"] = dv
            prev_vars["cv"] = cv
            prev_vars["idv"] = idv
            prev_vars["socv"] = socv
            prev_vars["ru_penalty"] = ru_penalty
            prev_vars["rd_penalty"] = rd_penalty
            prev_vars["ru_b"] = ru_b
            prev_vars["rd_b"] = rd_b
            prev_vars["ru_fd"] = ru_fd
            prev_vars["rd_fd"] = rd_fd
            prev_vars["pib_p"] = pib_p
            prev_vars["pib_m"] = pib_m
            self.sim_ctx.prev_vars = prev_vars

    def load_scen0(self):
        scen0_data = DataPortal()
        scen0_data.load(filename=os.path.join(config.PROJECT_ROOT, self.sim_ctx.pathscen, self.sim_ctx.scenfile))

    def load_im3_matched(self):
        """
        special function to calculate and load IM3 results when doing EMS optimization. The difference as opposo to the other IM is that for IM3, we take the resuts from the
        current sim and not sim-1 like for all other markets when doing EMS. Also for the real price we use ScenO not Scen0
        """
        matched_eim1 = {}
        parent_path = Path(config.PROJECT_ROOT) / config.base_result_dir / config.famscen_all / "IM3" / "market" / self.sim_ctx.sim / "IM"
        eIM_from_im3, S = self.read_from_txt(parent_path / f"eIM_3")
        lI_from_im3_run, _ = self.read_from_txt(parent_path / f"lI_3")
        nRVSG_dict = self.scenario_data.data().get("nRVSG", {})
        rv0_IM3 = sum(int(nRVSG_dict.get(i,0)) for i in range(self.scenario_data["sgim"][3])) + 1
        for t_ in range(1, self.scenario_data["nT"] + 1):
        #for t in range(12,25):
            rv = rv0_IM3 + (t_-1)
            real_price = self.scenario_data["ScenO"].get(rv,0) # important, here we take ScenO  (O not zero) to get the observed values
            sorted_curve_with_energy = [(lI_from_im3_run[t_,s_], s_, eIM_from_im3[t_,s_]) for s_ in S]
            vol,scen = self.matched_volume(sorted_curve_with_energy, real_price)
            matched_eim1[t_] = vol
            for q in range(1, self.scenario_data["nQ"] + 1):
                for s_ in self.S_preserved:
                    self.sim_ctx.eIM_prev[(3, t_, q, s_)] = matched_eim1[t_]  
                  

    def load_results_ems(self):
        parent_path = self.sim_ctx.previous_results_path
        parent_path_DA = parent_path / "DA"
        parent_path_RM = parent_path / "RM"
        parent_path_IM = parent_path / "IM"
        e_da_m_from_DAM_run, S_DA = self.read_from_txt(parent_path_DA / "eDA_m")
        e_da_p_from_DAM_run, _ = self.read_from_txt(parent_path_DA / "eDA_p")
        ld_from_DAM_run, _ = self.read_from_txt(parent_path_DA / "lD")
        ieDA_m_from_DAM_run, _ = self.read_from_txt(parent_path_DA / "ieDA_m")
        ieDA_p_from_DAM_run, _ = self.read_from_txt(parent_path_DA / "ieDA_p")  
        rU_from_rm_run, S_RM = self.read_from_txt(parent_path_RM / "rU")
        rD_from_rm_run, _ = self.read_from_txt(parent_path_RM/ "rD")
        lR_from_rm_run, _ = self.read_from_txt(parent_path_RM / "lR")
        eIM_from_im1, _ = self.read_from_txt(parent_path_IM / f"eIM_1")
        eIM_from_im2, S_IM2 = self.read_from_txt(parent_path_IM / f"eIM_2")
        lI_1_from_im2_run, _ = self.read_from_txt(parent_path_IM / f"lI_1")
        lI_2_from_im2_run, _ = self.read_from_txt(parent_path_IM / f"lI_2")
        data_eDA_m = {}
        data_eDA_p = {}
        data_lD = {}
        data_ieDA_m = {}
        data_ieDA_p = {}
        data_rU = {}
        data_rD = {}
        data_lR = {}
        data_lI_1 = {}
        data_lI_2 = {}

        idx_da = S_DA[0]
        idx_rm = S_RM[0]
        idx_im2 = S_IM2[0]
        for s in self.S_preserved:
            for t in range(1, self.scenario_data["nT"] + 1):
                for q in range(1, self.scenario_data["nQ"] + 1):
                    data_eDA_m[(t, q, s)] = e_da_m_from_DAM_run[t, idx_da]
                    data_eDA_p[(t, q, s)] = e_da_p_from_DAM_run[t, idx_da]
                    data_lD[(t, q, s)] = ld_from_DAM_run[t, idx_da]
                    data_ieDA_m[(t, q, s)] = ieDA_m_from_DAM_run[t, idx_da]
                    data_ieDA_p[(t, q, s)] = ieDA_p_from_DAM_run[t, idx_da]

                    data_rU[(t, q, s)] = rU_from_rm_run[t, idx_rm]
                    data_rD[(t, q, s)] = rD_from_rm_run[t, idx_rm]
                    data_lR[(t, q, s)] = lR_from_rm_run[t, idx_rm]

                    self.sim_ctx.eIM_prev[(1, t, q, s)] = eIM_from_im1[t, idx_im2] #bc eIM can only be fixed after the istance is 
                    self.sim_ctx.eIM_prev[(2, t, q, s)] = eIM_from_im2[t, idx_im2]
                    data_lI_1[(t, q, s)] = lI_1_from_im2_run[t, idx_im2]
                    data_lI_2[(t, q, s)] = lI_2_from_im2_run[t, idx_im2]

                    """
                    IMPORTANT: IM3 is cleared on day D As well, so we can only use its results starting at hour 12!
                    Until then, we only have the anticipated IM3 volume from the IM2 model.
                    """

                    if t >= self.scenario_data.data("TIM")[3][0]:  #If we are loading IM3 as well
                        self.load_im3_matched()

        self.scenario_data["eDA_m"] = data_eDA_m
        self.scenario_data["eDA_p"] = data_eDA_p
        self.scenario_data["lD"] = data_lD
        self.scenario_data["ieDA_m"] = data_ieDA_m
        self.scenario_data["ieDA_p"] = data_ieDA_p
        self.scenario_data["rU"] = data_rU
        self.scenario_data["rD"] = data_rD
        self.scenario_data["lR"] = data_lR
        self.scenario_data["lI_1"] = data_lI_1
        self.scenario_data["lI_2"] = data_lI_2
    

    def load_results(self):
        if self.sim_ctx.market == "DA":
            return self.scenario_data
        if self.sim_ctx.market == "EMS":
            self.load_results_ems()

        if self.sim_ctx.market == "RM":
            #self.previous_vars = config.DA_PARAMS
            self.load_dam_results()
        if self.sim_ctx.market == "IM1":
            #self.previous_vars = config.RM_PARAMS
            self.load_dam_results(market="IM1")
            self.load_rm_results()

        if self.sim_ctx.market in  ["IM2", "IM3"]:
            self.load_dam_results(market="IM2")
            self.load_rm_results()
            self.load_im_results()

        return self.scenario_data

