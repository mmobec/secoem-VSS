from pyomo.environ import value
import config_definition as config
import os

class PreviousMarketResultsLoader:
    """
    Loading the results of the previous run
    The path for where the results are stored is already in config_definiton
    Later, this might be expanded to be a more general PreviousRunResultLoader class than can load results of DAM,
    RM, IM1, ...,
    """
    def __init__(self, sim_ctx, scen_data):
        self.sim_ctx = sim_ctx
        self.scenario_data = scen_data
        self.S_preserved = self.scenario_data.data()["S"][None]  #This is kept for naming convention

    @staticmethod
    def read_from_txt(filename):
        """
        This function is used to read in the results of the DAM run of the DAM model
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

    def load_dam_results(self):

        """
        This function loads the DAM results, meaning the bid pairs of energy and price, and using those, calculates
        the matched energy of the DAM, finding the scenarios, inbetween which the real price is, and depending on
        buying or selling, picks the conservative scenario.
        """

        parent_path = self.sim_ctx.previous_results_path  #f'{config.dam_results_folder}/market/{self.sim_ctx.sim}/DA'
        parent_path = os.path.join("..", parent_path)
        e_da_m_from_DAM_run, S = self.read_from_txt(parent_path+"/eDA_m")
        e_da_p_from_DAM_run, _ = self.read_from_txt(parent_path+"/eDA_p")
        ld_from_DAM_run, _ = self.read_from_txt(parent_path+"/lD")
        ieDA_m_from_DAM_run, _ = self.read_from_txt(parent_path+"/ieDA_m")
        ieDA_p_from_DAM_run, _ = self.read_from_txt(parent_path+"/ieDA_p")

        e_da_m_matched = {}
        e_da_p_matched = {}
        ieDA_m = {}
        ieDA_p = {}
        for t in range(1, self.scenario_data["nT"] + 1):
            real_price = self.scenario_data["lD"][t,self.S_preserved[0]] # scenario doesn't matter

            sorted_bid_curve = self.get_sorted_bid_curve(ld_from_DAM_run, S, t)

            # Edge case: price is exactly equal to one of the bids (highly unlikely)
            if real_price in [i[0] for i in sorted_bid_curve]:
                s = [i[1] for i in sorted_bid_curve if i[0] == real_price][0]
                e_da_m_matched[t] = e_da_m_from_DAM_run[t,s]
                e_da_p_matched[t] = e_da_p_from_DAM_run[t,s]
                continue

            closest_lambda_plus = None
            closest_lambda_minus = None

            # There are 5 cases that can occur:
            # 1: the real price is below the lowest price of the bid curve -> buy everything
            if sorted_bid_curve[0][0] > real_price:
                closest_lambda_minus = sorted_bid_curve[0][1]
                e_da_m_matched[t] = e_da_m_from_DAM_run[t,closest_lambda_minus]
                e_da_p_matched[t] = 0
                continue
            # 2: The real price is above the highest price of the bid curve -> buy nothing, sell everything
            if sorted_bid_curve[-1][0] < real_price:
                closest_lambda_plus = sorted_bid_curve[-1][1]
                e_da_p_matched[t] = e_da_p_from_DAM_run[t,closest_lambda_plus]
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


            # Final scenario: unmatched
            if ieDA_m_from_DAM_run[t, closest_lambda_minus] + ieDA_m_from_DAM_run[t, closest_lambda_minus] + \
                    ieDA_p_from_DAM_run[t, closest_lambda_plus] + ieDA_p_from_DAM_run[t, closest_lambda_plus] == 0:
                # No block was accepted in either neighboring price → real_price was outside the curve.
                e_da_p_matched[t] = 0
                e_da_m_matched[t] = 0

        e_da_m = {}
        e_da_p = {}
        for t in range(1, self.scenario_data["nT"] + 1):
            for s in self.S_preserved:
                e_da_m[t, s] = e_da_m_matched[t]
                e_da_p[t, s] = e_da_p_matched[t]
                ieDA_p[t,s] = ieDA_p_from_DAM_run[t,S[0]] # Because the values are the same for all scenarios of DA in the RM data
                ieDA_m[t,s] = ieDA_m_from_DAM_run[t,S[0]]
        self.scenario_data["eDA_p"] = e_da_p
        self.scenario_data["eDA_m"] = e_da_m
        self.scenario_data["ieDA_p"] = ieDA_p
        self.scenario_data["ieDA_m"] = ieDA_m
        #return self.scenario_data


    def load_results(self):
        if self.sim_ctx.market == "DA":
            pass
        if self.sim_ctx.market == "RM":
            self.load_dam_results()
        return self.scenario_data

