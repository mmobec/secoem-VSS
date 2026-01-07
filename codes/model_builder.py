import pyomo.environ as pyo
import config_definition as cfg


class ModelBuilder:
    def __init__(self, sim_ctx):
        self.sim_ctx = sim_ctx
        self.model = pyo.AbstractModel()
        self.use_hydro = self.sim_ctx.include_hydro

    def add_fundamentals(self):
        model = self.model

        # ----------------------------------------------------------
        # 2. Fundamental Elements
        # ----------------------------------------------------------

        # >>> Time periods:
        model.nT = pyo.Param(within=pyo.PositiveIntegers)       # number of time periods
        model.T = pyo.RangeSet(1, model.nT)                 # set of time periods
        model.T0 = pyo.RangeSet(0, model.nT)                # T union {0}

        # >>> Intraday markets:
        model.nIM = pyo.Param(within=pyo.PositiveIntegers)      # number of intraday markets
        model.IM = pyo.RangeSet(1, model.nIM)               # set of intraday markets

        # For sets of time periods in each intraday market:
        model.TIM = pyo.Set(model.IM, ordered=True)          # time periods in IM "i"
        model.IMT = pyo.Set(model.T, ordered=True)           # intraday markets that include time "t"
        model.sgim = pyo.Param(model.IM, within=pyo.PositiveIntegers)   # stage associated to each IM "i"

        # >>> Scenario tree and Electricity market parameters:
        model.nS = pyo.Param(within=pyo.NonNegativeIntegers)     # numodel. of scenarios
        model.nSG = pyo.Param(within=pyo.NonNegativeIntegers)    # numodel. of stages

        # Full scenario set and preserved set
        model.S0 = pyo.RangeSet(1, model.nS)                 # complete set of scenarios
        model.S = pyo.Set(within=model.S0, ordered=True)      # preserved scenario (Prob>0)
        # We could have put mutable = True and define it after creating the instance but it would have been uncorrect as S is then used to define other sets

        # Stage sets
        model.SG = pyo.RangeSet(1, model.nSG)
        model.SG0 = pyo.Set(initialize=lambda m: [0] + list(range(1, pyo.value(m.nSG)+1)), ordered=True)

        # Scenario clusters c {SG0, S0}: # In Pyomo, we can define this as a two-dimensional set:
        def c_init(model, sg, s): # Then I will modify this cluster after creating the instance in ec_run.py
            return sorted(set())
        model.c = pyo.Set(model.SG0, model.S0, initialize=c_init, within=model.S0)

        model.nRVSG = pyo.Param(model.SG, within=pyo.NonNegativeIntegers, default=0) # Number of random variables at each stage
        model.nRV = pyo.Param(initialize=lambda m: sum(m.nRVSG[sg] for sg in m.SG)) # total number of random variables = sum of nRVSG
        model.fRVSG = pyo.Param(model.SG, initialize=lambda m, i: 1 + sum(m.nRVSG[sg] for sg in range(1, i))) # fRVSG = index of first RV of each stage

        # Probabilities and random variables
        model.Prob0 = pyo.Param(model.S0)       # scenario's probabilities (including zero values)
        model.Prob  = pyo.Param(model.S, mutable=True)        # preserved scenario probabilities

        # Complete and preserved scenario sets
        model.Scen0 = pyo.Param(pyo.RangeSet(1, model.nRV), model.S0, within=pyo.Reals, default=0.0)
        model.Scen = pyo.Param(pyo.RangeSet(1, model.nRV), model.S, within=pyo.Reals, default=0.0)

        # ----------------------------------------------------------
        # 3. Flexible Demand
        # ----------------------------------------------------------

        # Sets
        model.nFI = pyo.Param(within=pyo.NonNegativeIntegers)   # set of time intervals where a fraction of demand cf has to be met.
        model.FI = pyo.RangeSet(1, model.nFI)                   # set of intervals for demand

        # Operational Parameters
        model.FD   = pyo.Param(model.T, within=pyo.NonNegativeReals)   # Central demand [MWh]
        model.FD_L = pyo.Param(model.T, within=pyo.NonNegativeReals)   # Lower bound on flexible demand
        model.FD_U = pyo.Param(model.T, within=pyo.NonNegativeReals)   # Upper bound on flexible demand
        model.TF_L = pyo.Param(model.FI, within=pyo.PositiveIntegers)  # First time step of interval
        model.TF_U = pyo.Param(model.FI, within=pyo.PositiveIntegers)  # Last time step of interval
        model.coef_FD = pyo.Param(model.FI, within=pyo.Reals)          # fraction of central demand that must be met
        model.C_FD = pyo.Param(within=pyo.Reals)                       # cost per unit of flexible demand
        model.RUFD = pyo.Param(model.T, within=pyo.NonNegativeReals)   # Upwards reserve limit for FD
        model.RDFD = pyo.Param(model.T, within=pyo.NonNegativeReals)   # Downwards reserve limit for FD

        # ----------------------------------------------------------
        # 4. Wind Farm
        # ----------------------------------------------------------

        model.sgpw = pyo.Param(pyo.RangeSet(1, model.nT))   # stage associated to wind and PV production each hour
        model.Pavg     = pyo.Param(within=pyo.Reals)    # Wind nominal power [MW]
        model.pW = pyo.Param(model.T, model.S, within=pyo.NonNegativeReals, mutable=True)  # wind production
        model.max_pW = pyo.Param(within=pyo.NonNegativeReals, mutable=True)                # maximum wind capacity

        # ----------------------------------------------------------
        # 5. Solar PV
        # ----------------------------------------------------------

        model.Pavg_PV  = pyo.Param(within=pyo.Reals)    # PV nominal power [MW]
        model.pPV = pyo.Param(model.T, model.S, within=pyo.NonNegativeReals, mutable=True)
        model.max_pPV = pyo.Param(within=pyo.NonNegativeReals, mutable=True)

        # ----------------------------------------------------------
        # 6. Battery Energy Storage System
        # ----------------------------------------------------------

        model.Emax   = pyo.Param(within=pyo.NonNegativeReals)  # BESS capacity [MWh]
        model.Dmax   = pyo.Param(within=pyo.NonNegativeReals)  # BESS max charge/discharge rate [MW]
        model.RTE    = pyo.Param(within=pyo.NonNegativeReals)  # BESS round-trip efficiency
        model.SOCmin = pyo.Param(within=pyo.NonNegativeReals)  # BESS minimum SOC
        model.SOCmax = pyo.Param(within=pyo.NonNegativeReals)  # BESS maximum SOC
        model.SOCini = pyo.Param(within=pyo.NonNegativeReals, mutable=True)  #  !!! BESS initial SOC It's mutable because every day has to be re-initialized
        model.SOCfin = pyo.Param(within=pyo.NonNegativeReals)  # BESS final SOC

        # =============================================================================
        # Parameters not used in the model but useful for Post-Processing in ec_run.py
        # =============================================================================
        # Below you'll see mutable = True, it means that values are filled after creating the instance (but before calling the solver). This can be done if none of these values are used to build sets in model.py.

        # Wind Farm
        model.mean_pW = pyo.Param(model.T, within=pyo.NonNegativeReals, mutable=True)      # average wind
        model.sigma_pW = pyo.Param(model.T, within=pyo.NonNegativeReals, mutable=True, default=0.0)

        # PV Farm
        model.mean_pPV = pyo.Param(model.T, within=pyo.NonNegativeReals, mutable=True)     # average solar

        # Day-Ahead market
        model.mean_lD = pyo.Param(model.T, within=pyo.Reals, mutable=True)        # average day-ahead price
        model.PDA_LB = pyo.Param(within=pyo.NonNegativeReals)  # Minimum bid size [MWh]
        # Reserve market
        model.mean_lR = pyo.Param(model.T, within=pyo.Reals, mutable=True)          # average reserve price

        # Infraday market
        model.mean_lI = pyo.Param(model.IM, model.T, within=pyo.Reals, mutable=True) # average IMs price
        model.lIB  = pyo.Param(model.T, model.S, within=pyo.Reals, mutable=True)             # imbalances price
        model.mean_lPIB = pyo.Param(model.T, within=pyo.Reals, mutable=True)
        model.mean_lNIB = pyo.Param(model.T, within=pyo.Reals, mutable=True)
        model.mean_lIB  = pyo.Param(model.T, within=pyo.Reals, mutable=True)

        # Parameters for the VSS Calculation
        model.ScenF = pyo.Param(pyo.RangeSet(1, model.nRV), within=pyo.Reals)           # Forecasted scenario
        model.ScenO = pyo.Param(pyo.RangeSet(1, model.nRV), within=pyo.Reals)           # Observed scenario
        model.ScenE = pyo.Param(pyo.RangeSet(1, model.nRV), within=pyo.Reals, mutable=True, default=0.0) # Expected scenario
        # Nearest Tree Scenario Parameters
        model.min_dTO = pyo.Param(within=pyo.Reals, mutable=True, default=10**10)
        model.sOR = pyo.Param(within=pyo.NonNegativeIntegers, mutable=True)

        # Scenario Clustering and Probabilities
        def SSG_init(model, sg):
            return sorted(set())  # Returns an empty set for each stage
        model.SSG = pyo.Set(model.SG0, initialize=SSG_init, within=model.S0)

        # Prob. of cluster c[sg,sc].
        model.probc = pyo.Param(model.SG0, model.S, within=pyo.NonNegativeReals, mutable=True, default=0.0)
        # Define indexed sets for problem and simulations
        model.PROB = pyo.Set(initialize=['ec'])  # This should be a fixed set of problems
        model.SIMS = pyo.Set(initialize=[f"{i:03d}" for i in range(1, 366)])  # Extend as needed

        # Elapsed Time Parameters
        model.time = pyo.Param(model.PROB, model.SIMS, mutable=True, default=0.0)
        model.num_scen = pyo.Param(model.PROB, model.SIMS, mutable=True, default=0.0)

        # Objective Function Components
        model.obj_fun = pyo.Param(model.PROB, model.SIMS, mutable=True, default=0.0)
        model.obj_DA_income = pyo.Param(model.PROB, model.SIMS, mutable=True, default=0.0)
        model.obj_RM_income = pyo.Param(model.PROB, model.SIMS, mutable=True, default=0.0)
        model.obj_IM_income = pyo.Param(model.PROB, model.SIMS, mutable=True, default=0.0)
        model.obj_IB_income = pyo.Param(model.PROB, model.SIMS, mutable=True, default=0.0)
        model.obj_IB_costs = pyo.Param(model.PROB, model.SIMS, mutable=True, default=0.0)
        model.obj_IB_net = pyo.Param(model.PROB, model.SIMS, mutable=True, default=0.0)
        model.obj_FD_costs = pyo.Param(model.PROB, model.SIMS, mutable=True, default=0.0)


    def _add_DA_exclusive_set(self):
        model = self.model
        model.Ssd = pyo.Set(
            initialize=lambda m: [
            (t, l, j)
            for t in m.T
            for l in m.S
            for j in m.S
            if (pyo.value(m.lD[t, l]) <= pyo.value(m.lD[t, j]) and j != l)
            ]
        )



    def _add_RM_exclusive_set(self):
        model = self.model
        model.SsR = pyo.Set(
        initialize=lambda m: [
            (t, l, j)
            for t in m.T
            for l in m.S
            for j in m.S
            if (pyo.value(m.lR[t, l]) <= pyo.value(m.lR[t, j]) and j != l)
            ]
        )


    def _add_IM_exclusive_set(self):
        model = self.model
        market_no = int(self.sim_ctx.market[-1])
        model.SsI = pyo.Set(
        initialize=lambda m: [
            (t, l, j)
            for t in m.TIM[market_no]
            for l in m.S
            for j in m.S
            if (pyo.value(m.lI[market_no,t, l]) <= pyo.value(m.lI[market_no,t, j]) and j != l)
            ]
        )



    def add_market_participation(self):
        """
        Here, parameters and variables related to market participation are defined.
        The reason that eIM stays a variable during every model, is that the fixing approach is different. At IM2 for example, IM1 results are fixed after the instance creation,
        because that is the only way to fix the results of IM1, and let the other ones stay free variables.
        As for the other markets, the revealed markets for each market are turned into parameters.
        """
        model = self.model
        # DA
        model.lD = pyo.Param(model.T, model.S, within=pyo.Reals, mutable = True)    # !!! Day-ahead prices TO BE DEFINED BEFORE CREATING INSTANCE because they re used to create Ssd set
        # RM
        model.lR = pyo.Param(model.T, model.S, within=pyo.Reals, mutable=True)  # secondary reserve price
        model.TSR = pyo.Param(within=pyo.NonNegativeReals)        # time response of SR
        model.rU_B = pyo.Var(model.T, model.S, within=pyo.NonNegativeReals)    # BESS upward reserve
        model.rD_B = pyo.Var(model.T, model.S, within=pyo.NonNegativeReals)    # BESS downward reserve
        model.rU_FD = pyo.Var(model.T, model.S, within=pyo.NonNegativeReals)   # FD upward reserve
        model.rD_FD = pyo.Var(model.T, model.S, within=pyo.NonNegativeReals)   # FD downward reserve
        # IM
        model.eIM = pyo.Var(model.IM, model.T, model.S)
        model.lI = pyo.Param(model.IM, model.T, model.S, default=0.0, within=pyo.Reals, mutable=True)  
        model.maxTIM = pyo.Param(within=pyo.Reals, default=0.2)
        # IB
        model.lPIB = pyo.Param(model.T, model.S, within=pyo.Reals, mutable=True)  # positive imbalance price
        model.lNIB = pyo.Param(model.T, model.S, within=pyo.Reals, mutable=True)  # negative imbalance price
        model.PIB_p = pyo.Param(model.T, model.S, within=pyo.Reals, mutable=True, default=0.0)            # upper bound on positive imbalance
        model.PIB_m = pyo.Param(model.T, model.S, within=pyo.Reals, mutable=True, default=0.0)             # upper bound on negative imbalance
        
        if self.sim_ctx.market == "DA":  
            self._add_DA_exclusive_set()
            # Variables
            model.eDA_p = pyo.Var(model.T, model.S, within=pyo.NonNegativeReals)   # sold energy #Set to Mutable!
            model.eDA_m = pyo.Var(model.T, model.S, within=pyo.NonNegativeReals)   # bought energy #Set to Mutable!
            model.ieDA_p = pyo.Var(model.T, model.S, within=pyo.Binary)            # binary for selling bid
            model.ieDA_m = pyo.Var(model.T, model.S, within=pyo.Binary)            # binary for buying bid
        else:
            # Now parameters
            model.eDA_p = pyo.Param(model.T, model.S, within=pyo.NonNegativeReals, mutable=True)   # sold energy #Set to Mutable!
            model.eDA_m = pyo.Param(model.T, model.S, within=pyo.NonNegativeReals, mutable=True)   # bought energy #Set to Mutable!
            model.ieDA_p = pyo.Param(model.T, model.S, within=pyo.Binary)            # binary for selling bid
            model.ieDA_m = pyo.Param(model.T, model.S, within=pyo.Binary)            # binary for buying bid
            
        if self.sim_ctx.market == "RM":
            self._add_RM_exclusive_set()
        

        if self.sim_ctx.market in ["DA", "RM"]:
            model.rU = pyo.Var(model.T, model.S, within=pyo.NonNegativeReals)      # upward reserve
            model.rD = pyo.Var(model.T, model.S, within=pyo.NonNegativeReals)      # downward reserve
        else:
            model.rU = pyo.Param(model.T, model.S, within=pyo.NonNegativeReals)      # upward reserve
            model.rD = pyo.Param(model.T, model.S, within=pyo.NonNegativeReals)      # downward reserve

        if "IM" in self.sim_ctx.market:
            model.lR_penalty = pyo.Param(model.T, model.S, within=pyo.Reals, mutable=True)   # penalty price for undelivered reserve
            model.rU_penalty = pyo.Var(model.T, model.S, within=pyo.NonNegativeReals) # penalty terms undelivered rU and rD
            model.rD_penalty = pyo.Var(model.T, model.S, within=pyo.NonNegativeReals) 

            self._add_IM_exclusive_set()


        

    def add_variables(self):
        """
        As oppose to the implementation where each market has it's own model, here, everything stays a variable and after the instance is created,
        the previous market's results are fixed using var.fix() instead of switching them to paramters
        """
        model = self.model
        # 2. Flexible Demand
        model.var_fd = pyo.Var(model.T, model.S, within=pyo.NonNegativeReals)      # Flexible Demand [MW]
        model.var_afd_p = pyo.Var(model.T, model.S, within=pyo.NonNegativeReals)   # Positive displacement
        model.var_afd_m = pyo.Var(model.T, model.S, within=pyo.NonNegativeReals)   # Negative displacement

        # 6. Battery Energy Storage System
        model.dV = pyo.Var(model.T, model.S, within=pyo.NonNegativeReals)          # Discharge rate [MW]
        model.cV = pyo.Var(model.T, model.S, within=pyo.NonNegativeReals)          # Charge rate [MW]
        model.idV = pyo.Var(model.T, model.S, within=pyo.Binary)                   # Charge/discharge state (binary)
        model.socV = pyo.Var(model.T0, model.S, within=pyo.NonNegativeReals, bounds = (model.SOCmin,model.SOCmax))

        # 8.4 System Imbalances
        model.pIB_p = pyo.Var(model.T, model.S, within=pyo.NonNegativeReals)   # positive imbalance
        model.pIB_m = pyo.Var(model.T, model.S, within=pyo.NonNegativeReals)   # negative imbalance

        # Slack Variables for models from RM forward

        if self.model != "DA":
            model.IB_pos_slack = pyo.Var(model.T, model.S,within=pyo.NonNegativeReals, bounds=(0,200))
            model.IB_neg_slack = pyo.Var(model.T, model.S, within=pyo.NonNegativeReals, bounds=(0,200))

    def add_objective(self):
        # Because the rule needs to be a function
        def EECSW_rule(m):
            # Initialize the expression
            obj_expr = 0.0
            # DA component
            term_da = sum(
                m.Prob[s] * m.lD[t, s] * (m.eDA_p[t, s] - m.eDA_m[t, s])
                for s in m.S for t in m.T
            )
            obj_expr += term_da
            #RM component, with undeliverable reserve peanlty for markets after RM
            if "IM" in self.sim_ctx.market:  
                term_rm = sum(
                    m.Prob[s] * (
                        m.lR[t, s] * (m.rD[t, s] + m.rU[t, s]) 
                        - m.lR_penalty[t, s] * (m.rU_penalty[t, s] + m.rD_penalty[t, s])
                    )
                    for s in m.S for t in m.T
                )
            else:
                # Standard RM revenue without penalties
                term_rm = sum(
                    m.Prob[s] * m.lR[t, s] * (m.rD[t, s] + m.rU[t, s])
                    for s in m.S for t in m.T
                )
            obj_expr += term_rm
            # IM term
            term_im = sum(
                m.Prob[s] * m.lI[i, t, s] * m.eIM[i, t, s]
                for t in m.T
                for i in m.IMT[t]  # Only iterate over IMs that exist for this hour
                for s in m.S
            )
            obj_expr += term_im

            term_pib = sum(
                m.Prob[s] * m.lPIB[t, s] * m.pIB_p[t, s]
                for s in m.S for t in m.T
            )
            obj_expr += term_pib

            term_nib = sum(
                m.Prob[s] * m.lNIB[t, s] * m.pIB_m[t, s]
                for s in m.S for t in m.T
            )
            obj_expr -= term_nib  # Subtract cost

            term_flex_demand = sum(
                m.Prob[s] * m.C_FD * (m.var_afd_p[t, s] + m.var_afd_m[t, s])
                for s in m.S for t in m.T
            )
            obj_expr -= term_flex_demand # Subtract cost

            # Slack Variable Penalties (Only for non-DA modes)
            if self.sim_ctx.market != "DA":
                term_slack = sum(
                    m.Prob[s] * m.imbalanceSlackPenalty * (m.IB_pos_slack[t, s] + m.IB_neg_slack[t, s])
                    for s in m.S for t in m.T
                )
                obj_expr -= term_slack

            obj_expr -= m.lambda_risk * m.CVAR
            return obj_expr
        
        self.model.EECSW = pyo.Objective(rule=EECSW_rule, sense=pyo.maximize)
        #self.model.debug_obj_limit = pyo.Constraint(expr=self.model.EECSW <= 1e9) 

    def _add_common_constraints(self):
        model = self.model

        # -------------------
        # 2. Flexible Demand
        # -------------------

        # FD_L[t] <= var_fd[t, s] - TSR * rU_FD[t, s];
        def FlexDem_LB_rule(m, t, s):
            return m.FD_L[t] <= m.var_fd[t, s] - m.TSR * m.rU_FD[t, s]
        model.FlexDem_LB = pyo.Constraint(model.T, model.S, rule=FlexDem_LB_rule)

        # var_fd[t, s] + TSR * rD_FD[t, s] <= FD_U[t];
        def FlexDem_UB_rule(m, t, s):
            return m.var_fd[t, s] + m.TSR * m.rD_FD[t, s] <= m.FD_U[t]
        model.FlexDem_UB = pyo.Constraint(model.T, model.S, rule=FlexDem_UB_rule)

        # rD_FD[t, s] <= RDFD[t];
        def FlexDemP_DReserve_rule(m, t, s):
            return m.rD_FD[t, s] <= m.RDFD[t]
        model.FlexDemP_DReserve = pyo.Constraint(model.T, model.S, rule=FlexDemP_DReserve_rule)

        # rU_FD[t, s] <= RUFD[t];
        def FlexDemP_UReserve_rule(m, t, s):
            return m.rU_FD[t, s] <= m.RUFD[t]
        model.FlexDemP_UReserve = pyo.Constraint(model.T, model.S, rule=FlexDemP_UReserve_rule)

        # DailyDem: sum{t in T} var_fd[t, s] = sum{t in T} FD[t];
        def DailyDem_rule(m, s):
            return sum(m.var_fd[t, s] for t in m.T) == sum(m.FD[t] for t in m.T)
        model.DailyDem = pyo.Constraint(model.S, rule=DailyDem_rule)

        # InterDem: sum_{t=TF_L[f]..TF_U[f]} var_fd[t, s] >= coef_FD[f]* sum_{t=TF_L[f]..TF_U[f]} FD[t];
        def InterDem_rule(m, f, s):
            # gather time steps t in [TF_L[f], TF_U[f]]
            t_in_range = [t for t in m.T if m.TF_L[f] <= t <= m.TF_U[f]]
            return sum(m.var_fd[t, s] for t in t_in_range) >= m.coef_FD[f] * sum(m.FD[t] for t in t_in_range)
        model.InterDem = pyo.Constraint(model.FI, model.S, rule=InterDem_rule)

        # FD[t] - var_fd[t, s] = var_afd_p[t, s] - var_afd_m[t, s];

        def FlexDemDisplace_rule(m, t, s):
            return m.FD[t] - m.var_fd[t, s] == m.var_afd_p[t, s] - m.var_afd_m[t, s]
        model.FlexDemDisplace = pyo.Constraint(model.T, model.S, rule=FlexDemDisplace_rule)

        # -------------------
        # 5. Battery System
        # -------------------

        #### BESS opeartion
        # dV[t,s] <= Dmax * idV[t,s];
        def VPP_state_dV_rule(m, t, s):
            return m.dV[t, s] <= m.Dmax * m.idV[t, s]
        model.VPP_state_dV = pyo.Constraint(model.T, model.S, rule=VPP_state_dV_rule)

        # cV[t,s] <= Dmax * (1 - idV[t,s]);
        def VPP_state_cV_rule(m, t, s):
            return m.cV[t, s] <= m.Dmax * (1 - m.idV[t, s])
        model.VPP_state_cV = pyo.Constraint(model.T, model.S, rule=VPP_state_cV_rule)

        # socV[t,s] = socV[t-1,s] + (cV[t,s] - dV[t,s]/RTE)/Emax;
        def SOCV_rule(m, t, s):
            if t == m.T0.first():
                # skip t=1 because we define an initial condition separately
                return pyo.Constraint.Skip
            return m.socV[t, s] == m.socV[t-1, s] + (m.cV[t, s] - m.dV[t, s]/m.RTE)/m.Emax
        model.SOCV = pyo.Constraint(model.T, model.S, rule=SOCV_rule)

        # socV[first(T0), s] = SOCini;
        def SOCV_ini_rule(m, s):
            # first(T0) is typically 0
            return m.socV[m.T0.first(), s] == m.SOCini
        model.SOCV_ini = pyo.Constraint(model.S, rule=SOCV_ini_rule)

        # socV[nT, s] = SOCfin;
        def SOCV_fin_rule(m, s):
            return m.socV[m.nT, s] == m.SOCfin
        model.SOCV_fin = pyo.Constraint(model.S, rule=SOCV_fin_rule)

        #### BESS relation to reserve market
        # rD_B[t,s] + cV[t,s] - dV[t,s] <= Dmax;
        def VPP_RD2s_rule(m, t, s):
            return m.rD_B[t, s] + m.cV[t, s] - m.dV[t, s] <= m.Dmax
        model.VPP_RD2s = pyo.Constraint(model.T, model.S, rule=VPP_RD2s_rule)

        # rU_B[t,s] - cV[t,s] + dV[t,s] <= Dmax;
        def VPP_RU2s_rule(m, t, s):
            return m.rU_B[t, s] - m.cV[t, s] + m.dV[t, s] <= m.Dmax
        model.VPP_RU2s = pyo.Constraint(model.T, model.S, rule=VPP_RU2s_rule)

        # SOCmin <= socV[t,s] - TSR*rU_B[t,s]/(RTE*Emax);
        def VPP_RU_SOCV_rule(m, t, s):
            return m.SOCmin <= m.socV[t, s] - m.TSR * m.rU_B[t, s] / (m.RTE * m.Emax)
        model.VPP_RU_SOCV = pyo.Constraint(model.T, model.S, rule=VPP_RU_SOCV_rule)

        # socV[t,s] + TSR*rD_B[t,s]/Emax <= SOCmax;
        def VPP_RD_SOCV_rule(m, t, s):
            return m.socV[t, s] + m.TSR*m.rD_B[t, s]/m.Emax <= m.SOCmax
        model.VPP_RD_SOCV = pyo.Constraint(model.T, model.S, rule=VPP_RD_SOCV_rule)


    def _add_da_constraints(self):
        if self.sim_ctx.market != "DA":
            return
        
        model = self.model
        def DA_sell_bid_LB_rule(m, t, s):
            return m.PDA_LB * m.ieDA_p[t, s] <= m.eDA_p[t, s]
        model.DA_sell_bid_LB = pyo.Constraint(model.T, model.S, rule=DA_sell_bid_LB_rule)

        def DA_sell_bid_UB_rule(m, t, s):
            return m.eDA_p[t, s] <= (m.max_pW + m.max_pPV + m.Dmax - m.FD_L[t]) * m.ieDA_p[t, s]
        model.DA_sell_bid_UB = pyo.Constraint(model.T, model.S, rule=DA_sell_bid_UB_rule)

        def DA_buy_bid_LB_rule(m, t, s):
            return m.PDA_LB * m.ieDA_m[t, s] <= m.eDA_m[t, s]
        model.DA_buy_bid_LB = pyo.Constraint(model.T, model.S, rule=DA_buy_bid_LB_rule)

        def DA_buy_bid_UB_rule(m, t, s):
            return m.eDA_m[t, s] <= (m.Dmax + m.FD_U[t]) * m.ieDA_m[t, s]
        model.DA_buy_bid_UB = pyo.Constraint(model.T, model.S, rule=DA_buy_bid_UB_rule)

        # Constraint to Ensure Either Buying or Selling, Not Both
        def DA_buy_or_sell_rule(m, t, s):
            return m.ieDA_m[t, s] + m.ieDA_p[t, s] <= 1
        model.DA_buy_or_sell = pyo.Constraint(model.T, model.S, rule=DA_buy_or_sell_rule)


    def _add_reserve_constraints(self):
            model = self.model

            if self.sim_ctx.market in ["DA", "RM"]:       # for DA and RM we don't consider undeliverable resrve
                def RM_components_U_rule(m, t, s):
                    return m.rU[t, s] == m.rU_B[t, s] + m.rU_FD[t, s]
                model.RM_components_U = pyo.Constraint(model.T, model.S, rule=RM_components_U_rule)
                def RM_components_D_rule(m, t, s):
                    return m.rD[t, s] == m.rD_B[t, s] + m.rD_FD[t, s]
                model.RM_components_D = pyo.Constraint(model.T, model.S, rule=RM_components_D_rule)

            elif "IM" in self.sim_ctx.market:
                def RM_components_U_rule(m, t, s):
                    return m.rU[t, s] == m.rU_B[t, s] + m.rU_FD[t, s] + m.rU_penalty[t, s]
                model.RM_components_U = pyo.Constraint(model.T, model.S, rule=RM_components_U_rule)
                def RM_components_D_rule(m, t, s):
                    return m.rD[t, s] == m.rD_B[t, s] + m.rD_FD[t, s] + m.rD_penalty[t, s]
                model.RM_components_D = pyo.Constraint(model.T, model.S, rule=RM_components_D_rule)


    def _add_im_constraints(self):
        model = self.model
        def _cap20(m, t, s):
            if self.sim_ctx.market == "DA": 
                D = (m.eDA_p[t, s]) + (m.eDA_m[t, s])   # for DA, we keep the DA/IM ratio to the defined value in market.dat
                return m.maxTIM * D
            else:
                EPS = 1e-9 
                D = pyo.value(m.eDA_p[t, s]) + pyo.value(m.eDA_m[t, s])  # OK only if fixed/Param
                return m.maxTIM * D if D > EPS else m.FD_U[t]
        
        model.eIM_pos = pyo.Var(model.IM, model.T, model.S,within=pyo.NonNegativeReals)
        model.eIM_neg = pyo.Var(model.IM, model.T, model.S, within=pyo.NonNegativeReals)

        def link_posneg_rule(m, i, t, s):
            return m.eIM[i, t, s] == m.eIM_pos[i, t, s] - m.eIM_neg[i, t, s]
        model.IM_link_posneg = pyo.Constraint(model.IM, model.T, model.S, rule=link_posneg_rule)

        # -cap ≤ Σ_i eIM ≤ +cap
        def IM_bounds_1_rule_pos(m, t, s):
            return sum((m.eIM_pos[i, t, s] + m.eIM_neg[i,t,s]) for i in m.IMT[t]) <=  _cap20(m, t, s)
        model.IM_bounds_1_pos = pyo.Constraint(model.T, model.S, rule=IM_bounds_1_rule_pos)

        # Per-step bounds: -cap ≤ eIM[i] ≤ +cap
        def IM_bounds_3_rule(m, i, t, s):
            return m.eIM[i, t, s] >= -_cap20(m, t, s)
        model.IM_bounds_3 = pyo.Constraint(model.IM, model.T, model.S, rule=IM_bounds_3_rule)

        def IM_bounds_4_rule(m, i, t, s):
            return m.eIM[i, t, s] <= _cap20(m, t, s)
        model.IM_bounds_4 = pyo.Constraint(model.IM, model.T, model.S, rule=IM_bounds_4_rule)


    def _add_monotonicity_constraints(self):
        market = self.sim_ctx.market 
        model = self.model
        if market == "DA":
            def DA_bid_mono_1_rule(m, t, l, k):
                return m.eDA_p[t, l] <= m.eDA_p[t, k]
            model.DA_bid_mono_1 = pyo.Constraint(model.Ssd, rule=DA_bid_mono_1_rule)

            def DA_bid_mono_2_rule(m, t, l, k):
                return m.eDA_m[t, l] >= m.eDA_m[t, k]
            model.DA_bid_mono_2 = pyo.Constraint(model.Ssd, rule=DA_bid_mono_2_rule)

        elif market == "RM":
            def RM_bid_mono_1_rule(m, t, l, k):
                return m.rU[t, l] <= m.rU[t, k]
            model.RM_bid_mono_1 = pyo.Constraint(model.SsR, rule=RM_bid_mono_1_rule)

            def RM_bid_mono_2_rule(m, t, l, k):
                return m.rD[t, l] <= m.rD[t, k]
            model.RM_bid_mono_2 = pyo.Constraint(model.SsR, rule=RM_bid_mono_2_rule)

        elif "IM" in market:
            curr_im_no = int(self.sim_ctx.market[-1])
            def IM_bid_mono_1_rule(m, t, l, k):
                return m.eIM[curr_im_no,t, l] <= m.eIM[curr_im_no,t, k]
            model.IM_bid_mono_1_rule = pyo.Constraint(model.SsI, rule=IM_bid_mono_1_rule)


    def _add_imbalance_constraints(self):
        model = self.model
        #ToDo: Hydrogen here
        def Imbalances_rule(m, t, s):
            lhs = m.pIB_p[t, s] - m.pIB_m[t, s]
            rhs = (
                m.eDA_m[t, s]
                + m.pW[t, s]
                + m.pPV[t, s]
                + m.dV[t, s]
                - m.eDA_p[t, s]
                - sum(m.eIM[i, t, s] for i in m.IMT[t])
                - m.var_fd[t, s]
                - m.cV[t, s]
            )
            return lhs == rhs
        if self.sim_ctx.market == "IM3": 
            model.Imbalances = pyo.Constraint(range(12,25), model.S, rule=Imbalances_rule)    #not a pretty solution bc hardcoded.. however this is necessary otherwise IM3 is infeasible
        else:
            model.Imbalances = pyo.Constraint(model.T, model.S, rule=Imbalances_rule)

        if self.sim_ctx.market == "DA":
            def IB_pos_UB_rule(m, t, s):
                return m.pIB_p[t, s] <= m.PIB_p[t, s]
            model.IB_pos_UB = pyo.Constraint(model.T, model.S, rule=IB_pos_UB_rule)
            # pIB_m[t,s] <= PIB_m[t,s];
            def IB_neg_UB_rule(m, t, s):
                return m.pIB_m[t, s] <= m.PIB_m[t, s]
            model.IB_neg_UB = pyo.Constraint(model.T, model.S, rule=IB_neg_UB_rule)  

        elif (self.sim_ctx.market == "RM") or ("IM" in self.sim_ctx.market):
            # For RM and IM, we consider the imbalance slack variable to ensure feasibility
            model.imbalanceSlackPenalty = pyo.Param(default=100,mutable=True)
            def IB_pos_UB_rule(m, t, s):
                return m.pIB_p[t, s] <= pyo.value(m.PIB_p[t, s]) + m.IB_pos_slack[t, s]
            model.IB_pos_UB = pyo.Constraint(model.T, model.S, rule=IB_pos_UB_rule)

            def IB_neg_UB_rule(m, t, s):
                return m.pIB_m[t, s] <= pyo.value(m.PIB_m[t, s]) + m.IB_neg_slack[t, s]
            model.IB_neg_UB = pyo.Constraint(model.T, model.S, rule=IB_neg_UB_rule)


    def _add_risk_aversion(self):
        model = self.model
        model.alpha = pyo.Param(initialize=0.90, mutable=True)  # confidence level
        model.lambda_risk = pyo.Param(initialize=25, mutable=False)  # risk aversion weight

        model.eta_IM = pyo.Var()                       # VaR-like level for IM loss
        model.z_IM = pyo.Var(model.S, within=pyo.NonNegativeReals)  # tail excesses

        def im_loss(m, s):    #return sum(
            #    (m.eIM_pos[i, t, s] + m.eIM_neg[i,t,s]) for t in m.T for i in m.IMT[t])
            return sum(
                (m.eIM_pos[i, t, s] + m.eIM_neg[i,t,s]) for t in m.T for i in m.IMT[t])

        def CVaR_IM_excess_rule(m, s):
            return m.z_IM[s] >= im_loss(m, s) - m.eta_IM

        model.CVaR_IM_excess = pyo.Constraint(model.S, rule=CVaR_IM_excess_rule)

        def CVAR_rule(m):
            return m.eta_IM + (1.0 / (1.0 - m.alpha)) * sum(
                m.Prob[s] * m.z_IM[s] for s in m.S
            )

        model.CVAR = pyo.Expression(rule=CVAR_rule)     


    def add_constraints(self):
        self._add_common_constraints()
        self._add_da_constraints()
        self._add_reserve_constraints()
        self._add_im_constraints()
        self._add_monotonicity_constraints()
        self._add_im_constraints()
        self._add_risk_aversion()
        self._add_imbalance_constraints()

    @staticmethod
    def consecutive_scenarios(model, sg, k):
        if (sg, k) not in model.c.index_set():
            return []
        # Sort using the same numeric key!
        scenario_list = sorted([l for l in model.c[sg, k] if l in model.S],
                            key=lambda x: int(x))
        return [(scenario_list[i], scenario_list[i+1]) for i in range(len(scenario_list)-1)]


    
    def _build_stage1_nac_index(self, model):
        """
        Builds a single index set for all day-ahead & reserve variables that share
        the same stage logic and indexing (t, s).
        We'll store tuples: (var_name, t, k, l, l_next).
        """
        market = self.sim_ctx.market
        if "IM" in market: #Not needed for IM
            return
        
        if market == "DA":
            day_ahead_reserve_vars = [
                "eDA_p", "eDA_m", "ieDA_p", "ieDA_m",
                "rU", "rU_B", "rU_FD", #"rU_EL", "rU_FC",
                "rD", "rD_B", "rD_FD"]#, "rD_EL", "rD_FC"]
            stage = 1
        elif market == "RM":
            day_ahead_reserve_vars = [
            "rU", "rU_B", "rU_FD",
            "rD", "rD_B", "rD_FD"]
            stage = 2

        idx = []
        for var_name in day_ahead_reserve_vars:
            var_obj = getattr(model, var_name)
            for t in model.T:
                for k in model.S0:
                    # stage=1 for these
                    for (l, l_next) in self.consecutive_scenarios(model, stage, k):
                        # skip if not in domain
                        if (t, l) in var_obj and (t, l_next) in var_obj:
                            idx.append((var_name, t, k, l, l_next))
        return idx
    

    def _add_stage1_nac(self):
        model = self.model
        if "IM" in self.sim_ctx.market: #Not needed for IM
            return
        
        def stage1_nac_rule(m, var_name, t, k, l, l_next):
            var_obj = getattr(m, var_name)
            return var_obj[t, l] == var_obj[t, l_next]
        model.NAC_stage1_index = pyo.Set(dimen=5, initialize=self._build_stage1_nac_index)
        model.NAC_stage1 = pyo.Constraint(model.NAC_stage1_index, rule=stage1_nac_rule)


    def _add_im_nac(self):
        market = self.sim_ctx.market
        model = self.model
        #if market == "DA":
         #   return
        
        #elif market == "RM":
         #   return

        if "IM" in market:
            market_no = int(market[-1])
        else: 
            market_no = -1

        def _build_nac_eIM_index(model):
            idx = []
            for i in [i for i in model.IM if i >= market_no]:  #meaning the NAC are defined for the current and next IM, not for the ones already revealed
                for t in model.TIM[i]:
                    for k in model.S0:
                        # Use sgim[i] directly for current IM (recourse), else sgim[i] - 1
                        sg_for_i = model.sgim[i] if i == market_no else model.sgim[i] - 1
                        if (sg_for_i, k) in model.c.index_set():
                            for (l, l_next) in self.consecutive_scenarios(model, sg_for_i, k):
                                if l in model.S and l_next in model.S:
                                    idx.append((i, t, k, l, l_next))
            return idx
        def _NAC_eIM_rule(m,i, t, k, l, l_next):
            if (i, t, l) not in m.eIM or (i, t, l_next) not in m.eIM:
                return pyo.Constraint.Skip
            return m.eIM[i, t, l] == m.eIM[i, t, l_next]

        model.NAC_eIM_index = pyo.Set(dimen=5, initialize=_build_nac_eIM_index)
        model.NAC_eIM = pyo.Constraint(model.NAC_eIM_index, rule=_NAC_eIM_rule)


    def _add_imbalance_nac(self):
        model = self.model

        def _build_nac_imbal_index(model):
            """
            We'll unify pIB_p and pIB_m in one NAC set.
            We'll store (var_name, t, k, l, l_next).
            """
            imbal_vars = ["pIB_p", "pIB_m"]
            idx = []
            for var_name in imbal_vars:
                var_obj = getattr(model, var_name)
                for t in model.T:
                    sg_for_t = model.sgpw[t]
                    for k in model.S0:
                        if (sg_for_t, k) in model.c.index_set():
                            for (l, l_next) in self.consecutive_scenarios(model, sg_for_t, k):
                                if (t, l) in var_obj and (t, l_next) in var_obj:
                                    idx.append((var_name, t, k, l, l_next))
            return idx

        def _nac_imbal_rule(m, var_name, t, k, l, l_next):
            var_obj = getattr(m, var_name)
            return var_obj[t, l] == var_obj[t, l_next]

        model.NAC_imbal_index = pyo.Set(dimen=5, initialize=_build_nac_imbal_index)
        model.NAC_imbal = pyo.Constraint(model.NAC_imbal_index, rule=_nac_imbal_rule)


    def _add_ec_asset_nac(self):
        model = self.model
        market = self.sim_ctx.market
        if "IM" in market:
            market_no = int(market[-1])
        else:
            market_no = -1      #placeholder for DA and RM. This variable is only used to check if IM == IM[-1]
        if market in  ["DA", "RM"]:
            ec_asset_var = [
                "var_fd", "var_afd_p", "var_afd_m",
                "dV", "cV", "idV", "socV"]

        elif "IM" in market:
                ec_asset_var = [
                "var_fd", "var_afd_p", "var_afd_m",
                "dV", "cV", "idV", "socV",
                "rU_B", "rU_FD",
                "rU_FD", "rD_FD"]

        def _build_nac_ac_asset_index(model):
            """
            We'll unify flexible demand + battery in one NAC set, referencing c[sgpw[t]-1, k].
            We'll store (var_name, t, k, l, l_next).
            """
            idx = []
            for var_name in ec_asset_var:
                var_obj = getattr(model, var_name)
                for t in model.T:
                    if (t < model.TIM[model.nIM].first()) and (market_no == model.nIM): #For IM3, we don't need nac for the first 10h, because they are revealed already
                        continue
                    sg_for_t_minus1 = model.sgpw[t] - 1
                    if sg_for_t_minus1 < 0:
                        continue
                    if (sg_for_t_minus1, None) not in model.c.index_set():
                        # We'll handle the check inside the loop
                        pass
                    for k in model.S0:
                        if (sg_for_t_minus1, k) in model.c.index_set():
                            for (l, l_next) in self.consecutive_scenarios(model, sg_for_t_minus1, k):
                                if (t, l) in var_obj and (t, l_next) in var_obj:
                                    idx.append((var_name, t, k, l, l_next))
            return idx

        def _nac_ec_asset_rule(m, var_name, t, k, l, l_next):
            var_obj = getattr(m, var_name)
            return var_obj[t, l] == var_obj[t, l_next]

        model.NAC_fd_battery_index = pyo.Set(dimen=5, initialize=_build_nac_ac_asset_index)
        model.NAC_fd_battery = pyo.Constraint(model.NAC_fd_battery_index, rule=_nac_ec_asset_rule)

    def add_NAC(self):
        self._add_stage1_nac()
        self._add_imbalance_nac()
        self._add_ec_asset_nac()

    def build_model(self):
        self.add_fundamentals()
        self.add_market_participation()
        self.add_variables()
        self.add_objective()
        self.add_constraints()
        self.add_NAC()
        return self.model


