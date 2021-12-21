import os
import pandas as pd
import numpy as np


# These numbers are fixed from the hatch results (all in thousands except the token price)
TOTAL_HATCH_FUNDING = 1571.22357
TOTAL_INITIAL_TECH_SUPPLY = 2035.918945
HATCH_FINAL_TECH_PRICE = 0.754743


#################
#
#
# This is an alternative version of th bonding curve simulation. It discards the possibility to "set" balance scenarios and in exchange keeps an active state.
# It is a roguh draft, and while it seems to work, there was no testing involved and it is very slow. Would need a revision before any serious use.
#
#
#################


class BondingCurve:

    def __init__(self, reserve_balance=100, opening_price=5, initial_supply=100, entry_tribute=0.05, exit_tribute=0.05):

        # Basic ABC configuration
        self.OPENING_PRICE = opening_price
        self.INITIAL_SUPPLY = initial_supply
        self.INITIAL_BALANCE = reserve_balance
        self.RESERVE_RATIO = self.INITIAL_BALANCE / \
            (self.OPENING_PRICE * self.INITIAL_SUPPLY)

        # State of  the ABC
        self.current_supply = self.INITIAL_SUPPLY
        self.current_balance = self.INITIAL_BALANCE
        self.collected_tribute = 0
        self.entry_tribute = entry_tribute
        self.exit_tribute = exit_tribute

    # Returns the token price given a specific supply. If none is given, current supply is used
    def get_price(self, supply=None):
        if supply == None:
            supply = self.current_supply

        return (supply ** ((1 / self.RESERVE_RATIO) - 1) * self.OPENING_PRICE) / (
            self.INITIAL_SUPPLY ** ((1 / self.RESERVE_RATIO) - 1)
        )

    # Returns the collateral balance price given a specific supply.. If none is given, current supply is used
    def get_balance(self, supply=None):
        if supply == None:
            return self.get_balance
        else:
            return (
                self.RESERVE_RATIO * self.get_price(supply) * supply
            )

    # Returns supply at a specific balance. . If none is given, an approximation is calculated (only meant for visualizing purposes)
    def get_supply(self, balance=None):
        if balance == None:
            return self.current_supply
        else:
            supply_ref = 0
            while self.get_balance(supply_ref) < balance:
                supply_ref = supply_ref + 10

            # increase number of steps for higher precision, but with increased calculation time
            df = self.curve_over_balance(supply_ref-10, supply_ref, 100000)
            df_rounded = df.round(3)

            index = int(df.index.where(
                df_rounded['balanceInThousands'] >= balance).dropna()[0])
            price = df.at[index, "price"]

            supply = balance/(price * self.RESERVE_RATIO)

            return supply

    # Performs a sale. Returns how much wxDAI you get from selling TEC and the amount of tribute wxDAI collected
    def sell_tokens(self, bonded):

        # sell and take tribute
        amount_in = bonded * -1  # because we are reducing the supply (burning)
        amountBeforeTribute = self.current_balance * \
            ((amount_in / self.current_supply + 1) ** (1 / self.RESERVE_RATIO) - 1)
        amountBeforeTribute *= -1

        # since it is a sale, the number returned was negative
        tribute_collected = (amountBeforeTribute * self.exit_tribute)
        # we leave it negative for the supply calculations down below
        amount_out = (amountBeforeTribute - tribute_collected)

        self.current_supply -= bonded
        self.current_balance -= amountBeforeTribute
        self.collected_tribute += tribute_collected

        return amount_out, tribute_collected

    # Performs a purchase. Returns how much TEC you get from purchasing with wxDAI and the amount of tribute wxDAI collected.
    def purchase_tokens(self, collateral):

        purchase_tribute = collateral * self.entry_tribute
        amount_in = collateral - purchase_tribute

        amount_minted = self.current_supply * \
            ((amount_in / self.current_balance + 1) ** (self.RESERVE_RATIO) - 1)

        self.current_balance += amount_in
        self.current_supply += amount_minted
        self.collected_tribute += purchase_tribute

        return amount_minted, purchase_tribute

    # For drawing the bonding curve. Range shows how many times the initial supply you make the graph for, steps how many subdivisions

    def curve_over_supply(self, range_begin=0, range_end=1000, steps=500):
        x = np.linspace(range_begin, range_end, steps)
        y = []
        for val in x:
            y.append(self.get_price(val))

        return pd.DataFrame(zip(x, y), columns=["supplyInThousands", "price"])

    # For drawing the bonding curve. Range shows how many times the initial supply you make the graph for, steps how many subdivisions
    def curve_over_balance(self, range_begin=0, range_end=1000, steps=500):
        supply_list = np.linspace(range_begin, range_end, steps)
        x = []
        y = []
        for val in supply_list:
            x.append(self.get_balance(val))
            y.append(self.get_price(val))

        return pd.DataFrame(zip(x, y), columns=["balanceInThousands", "price"])


class BondingCurveHandler():
    '''
    The handler for the Bonding Curve. All interaction happens through this.

    The constrctor receives following args:

    commons_percentage: float between 0-0.95. Percentage of funds that get substracted from the total funding to go to the commons pool
    ragequit_amount: float . Amount of reserve returned to ragequitters before the bonding curve gets initialized
    opening_price: float. No real limit but, expected to be between 1 and 4
    entry_tribute: float between 0-0.99. Percentage of funds substracted on buy (mint) operations before interacting with the bonding curve
    exit_tribute: float between 0-0.99. Percentage of funds substracted on sell (burn) operations after interacting with the boding curve
    initial_buy: float. Allows to represent an initial buy-in from the TEC in the scenario calculations
    virtual_supply: optional. Float, defaults to TOTAL_INITIAL_TECH_SUPPLY. Allows generating the bonding curve from a supply number different than the real one (eg to model lockups)
    virtual_balance: optional. Float, defaults to TOTAL_HATCH_FUNDING. Allows generating the bonding curve from a balance  number different than the real one (eg to model locked liquidity)
    steplist: list with format [["AMOUNT", "TOKEN"],["AMOUNT", "TOKEN"]]. Set of buy/sell operations applied to the bonding curve.
    zoom_graph=0: optional. value 0 or 1. To specify if the draw function should show the whole curve(0) or "zoom in" into the area where operations are happening (1)
    plot_mode=0: optional. value 0 or 1. Not in the scope of this iteration. Specifies if the draw function should plot the price against the balance (0) or the supply (1)

    '''

    def __init__(self,
                 commons_percentage,
                 ragequit_amount,
                 opening_price,
                 entry_tribute,
                 exit_tribute,
                 initial_buy,
                 steplist,
                 virtual_supply=1,
                 virtual_balance=1,
                 zoom_graph=0,
                 plot_mode=0,
                 include_milestones=0):

        # scale input numbers down by 1000 for the bonding curve calculations
        ragequit_amount = ragequit_amount / 1000
        initial_buy = initial_buy / 1000

        virtual_supply = TOTAL_INITIAL_TECH_SUPPLY if virtual_supply == 1 else (
            virtual_supply / 1000)
        virtual_balance = TOTAL_HATCH_FUNDING if virtual_balance == 1 else (
            virtual_balance / 1000)

        # parse the steplist (which gets read as string) into the right format and scale the values
        steplist_parsed = []
        if steplist != "":
            for step in steplist:
                buf = str(step).strip('][').split(', ')
                buf[0] = (float(buf[0].strip("'")) / 1000)
                buf[1] = buf[1].strip("'")
                steplist_parsed.append(buf)

         # Determine initial supply and balance based on input
        self.initialization_supply, self.initialization_balance, self.commons_reserve = self.get_initialization_values(
            received_supply=virtual_supply, received_balance=virtual_balance, commons_percentage=commons_percentage, initial_buy=initial_buy, ragequit_amount=ragequit_amount)

        params_valid = self.check_param_validity(
            commons_percentage,
            ragequit_amount,
            opening_price,
            entry_tribute,
            exit_tribute,
            initial_buy,
            float(self.commons_reserve),
            steplist_parsed,
            float(self.initialization_supply),
            float(self.initialization_balance),
            int(zoom_graph),
            int(plot_mode)
        )

        # Initialize the bonding curve
        self.bonding_curve = BondingCurve(
            self.initialization_balance, opening_price, self.initialization_supply, entry_tribute, exit_tribute)

        # If there is an initial buy, perform it here
        self.steps_table = pd.DataFrame()
        if initial_buy > 0:
            # the buy-in gets saved as "step zero"
            self.steps_table = self.steps_table.append(self.generate_outputs_table(
                bondingCurve=self.bonding_curve, steplist=[[initial_buy, "wxDai"]]))
            self.steps_table["step"] = 0

        # calculate the scenarios
        self.steps_table = self.steps_table.append(self.generate_outputs_table(
            bondingCurve=self.bonding_curve, steplist=steplist_parsed))
        self.zoom_graph = zoom_graph
        self.plot_mode = plot_mode
        self.include_milestones = include_milestones

    def get_data(self):

        [min_range, max_range] = self.get_scenario_range(
            steps_table=self.steps_table, zoom_graph=self.zoom_graph)

        clean_figure_data = self.get_data_augmented_bonding_curve(
            bondingCurve=self.bonding_curve, min_range=min_range, max_range=max_range, plot_mode=self.plot_mode).to_dict(orient='list')
        clean_figure_data['reserveRatio'] = self.bonding_curve.RESERVE_RATIO

        figure_bonding_curve = {"chartData": {}}

        if self.include_milestones == 1:
            figure_milestone_table = self.get_milestone_table(
                self.bonding_curve)
            figure_bonding_curve['milestoneTable'] = figure_milestone_table

        figure_initial_fund_allocation = self.get_allocation_table(
            self.steps_table, self.initialization_balance, self.commons_reserve)
        figure_bonding_curve['fundAllocations'] = figure_initial_fund_allocation

        if self.steps_table.empty:
            figure_bonding_curve['chartData'] = clean_figure_data
            return figure_bonding_curve
        else:
            figure_buy_sell_table = self.steps_table.loc[:, ["step", "currentPriceParsed", "currentSupplyParsed", "currentBalanceParsed",
                                                             "amountInParsed", "tributeCollectedParsed", "amountOutParsed", "newPriceParsed", "slippage"]].to_dict(orient='list')
            extended_figure_data = clean_figure_data
            # get single points with full coordinates
            extended_figure_data['singlePoints'] = self.get_single_point_coordinates(
                self.steps_table)
            # get linspace from every step.
            extended_figure_data['stepLinSpaces'] = self.get_step_linspaces(
                self.bonding_curve, self.steps_table)

            # For debugging purposes
            # print(self.steps_table.loc[:,["step", "currentPrice", "currentSupply", "currentBalance", "amountIn", "tributeCollected", "amountOut", "newPrice", "newSupply", "newBalance", "slippage"]])

            figure_bonding_curve['chartData'] = extended_figure_data
            figure_bonding_curve['stepTable'] = figure_buy_sell_table

            return figure_bonding_curve

    def generate_outputs_table(self, bondingCurve, steplist):

        column_names = [
            "step",
            "currentPrice",
            "currentPriceParsed",
            "currentSupply",
            "currentSupplyParsed",
            "currentBalance",
            "currentBalanceParsed",
            "amountIn",
            "amountInParsed",
            "tributeCollected",
            "tributeCollectedParsed",
            "amountOut",
            "amountOutParsed",
            "newPrice",
            "newPriceParsed",
            "newSupply",
            "newSupplyParsed",
            "newBalance",
            "newBalanceParsed",
            "slippage",
        ]
        outputTable = pd.DataFrame(columns=column_names)

        for index, step in enumerate(steplist):

            current_supply = float(bondingCurve.current_supply)
            # current_supply_parsed = str(format(current_supply, '.2f')) + "k TEC"
            current_supply_parsed = round(current_supply*1000, 2)

            current_price = bondingCurve.get_price(current_supply)
            # current_price_parsed = str(format(current_price, '.2f')) + " wxDAI"
            current_price_parsed = round(current_price, 2)

            current_balance = float(bondingCurve.current_balance)
            # current_balance_parsed = str(format(current_balance, '.2f')) + " wxDAI"
            current_balance_parsed = round(current_balance*1000, 2)

            amount_in = step[0]
            # to avoid the most obvious error. TO DO: in-depth validation of the steplist...
            token_type = "wxDAI" if step[1] == "wxDai" else step[1]

            amount_in_parsed = str(
                format(amount_in*1000, '.2f')) + " " + str(token_type)
            # amount_in_parsed = str(round(amount_in, 2)) + "k " + str(token_type)

            amount_out = 0
            amount_out_parsed = ""
            new_supply = 0
            tribute_collected = 0
            if token_type == "wxDAI":
                # take tribute and buy
                amount_out, tribute_collected = bondingCurve.purchase_tokens(
                    amount_in)

                amount_out_parsed = str(
                    format(amount_out*1000, '.2f')) + " TEC"
                tribute_collected_parsed = round(tribute_collected*1000, 2)

                slippage = (amount_in - tribute_collected) / \
                    current_price - amount_out
                slippage_pct = slippage / \
                    ((amount_in - tribute_collected)/current_price)
                slippage_pct = str(format((slippage_pct*100), '.2f')) + "%"

                new_supply = bondingCurve.current_supply
            elif token_type == "TEC":

                amount_out, tribute_collected = bondingCurve.sell_tokens(
                    amount_in)

                amount_out_parsed = str(
                    format((amount_out*1000), '.2f')) + " wxDAI"
                tribute_collected_parsed = round((tribute_collected*1000), 2)
                # amount_out_parsed = str(round((amount_out*-1), 2)) + "k wxDAI"

                slippage = ((amount_in*(1-bondingCurve.exit_tribute))
                            * current_price - amount_out) * -1
                slippage_pct = slippage / \
                    ((amount_in*(1-bondingCurve.exit_tribute))*current_price) * -1
                slippage_pct = str(format((slippage_pct*100), '.2f')) + "%"

                new_supply = bondingCurve.current_supply

            new_price = bondingCurve.get_price(new_supply)
            # new_price_parsed = str(format(new_price, '.2f')) + " wxDAI"
            new_price_parsed = round(new_price, 2)

            # new_supply_parsed = str(format(new_supply, '.2f')) + "k TEC"
            new_supply_parsed = round(new_supply*1000, 2)

            new_balance = bondingCurve.current_balance
            # new_balance_parsed = str(format(new_balance, '.2f')) + " wxDAI"
            new_balance_parsed = round(new_balance*1000, 2)

            # add to Dataframe
            outputTable.loc[len(outputTable.index)] = [
                (index+1),
                current_price,
                current_price_parsed,
                current_supply,
                current_supply_parsed,
                current_balance,
                current_balance_parsed,
                amount_in,
                amount_in_parsed,
                tribute_collected,
                tribute_collected_parsed,
                amount_out,
                amount_out_parsed,
                new_price,
                new_price_parsed,
                new_supply,
                new_supply_parsed,
                new_balance,
                new_balance_parsed,
                slippage_pct,
            ]

        # print(outputTable)
        return outputTable

    def get_data_augmented_bonding_curve(self, bondingCurve, min_range, max_range, plot_mode=0):

        if plot_mode == 0:
            curve_draw = bondingCurve.curve_over_balance(min_range, max_range)
        elif plot_mode == 1:
            curve_draw = bondingCurve.curve_over_supply(min_range, max_range)

        return curve_draw

    def get_initialization_values(self, received_supply, received_balance, commons_percentage, initial_buy, ragequit_amount):
        initialization_supply = -1
        initialization_balance = -1

        if (received_supply == TOTAL_INITIAL_TECH_SUPPLY):
            # no virtual supply, use real data
            initialization_supply = TOTAL_INITIAL_TECH_SUPPLY - \
                (ragequit_amount / HATCH_FINAL_TECH_PRICE)
        else:
            # we just use the virtual supply
            initialization_supply = received_supply

        if(received_balance == TOTAL_HATCH_FUNDING):
            # no virtual balance, use real data
            initialization_balance = (
                TOTAL_HATCH_FUNDING - ragequit_amount - initial_buy) * (1 - commons_percentage)
            commons_reserve = (
                TOTAL_HATCH_FUNDING - ragequit_amount - initial_buy) * commons_percentage
        else:
            # we just use the virtual balance
            initialization_balance = received_balance
            commons_reserve = (
                TOTAL_HATCH_FUNDING - ragequit_amount - initial_buy) * commons_percentage

        return initialization_supply, initialization_balance, commons_reserve

    def get_single_point_coordinates(self, steps_table):

        coord_list = []

        for index, row in steps_table.iterrows():
            # point = {'x' : row['currentBalance'], 'y': row['currentPrice'], 'pointSupply': row['currentSupply']}
            point = {'x': row['currentBalance'], 'y': row['currentPrice']}
            coord_list.append(point)

        last_row = steps_table.iloc[-1]
        # last_point = {'x' : last_row['newBalance'], 'y': last_row['newPrice'], 'pointSupply': row['newSupply']}
        last_point = {'x': last_row['newBalance'], 'y': last_row['newPrice']}
        coord_list.append(last_point)

        return coord_list

    def get_step_linspaces(self, bondingCurve, steps_table):

        linspace_list = []

        for index, row in steps_table.iterrows():
            lin_step_df = bondingCurve.curve_over_balance(bondingCurve.get_supply(
                row['currentBalance']), bondingCurve.get_supply(row['newBalance']), steps=100)
            lin_step_df = lin_step_df.rename(
                columns={"balanceInThousands": "x", "price": "y"})
            lin_step = lin_step_df.to_dict(orient='list')
            # print("Interval:" + str(row['currentBalance']) + " - " + str(row['newBalance']))
            linspace_list.append(lin_step)

        return linspace_list

    def get_scenario_range(self, steps_table, zoom_graph=0):

        if steps_table.empty:
            min_range = 0
            max_range = 500
        else:
            minimum = min(steps_table['currentSupply'].min(
            ), steps_table['newSupply'].min())
            maximum = max(steps_table['newSupply'].max(
            ), steps_table['newSupply'].max())
            min_range = 0 if zoom_graph == 0 else minimum * 0.975
            max_range = maximum * 1.01 if zoom_graph == 0 else maximum * 1.001
            # max_range = maximum * 1.025 if zoom_graph == 0 else maximum * 1.01
        # print("min: " + str(min_range))
        # print("max: " + str(max_range))
        return [min_range, max_range]

    def get_milestone_table(self, bCurve):
        balance_list = [10, 50, 100, 200, 300, 400, 500, 600, 700, 800, 900,
                        1_000, 1_250, 1_500, 1_750, 2_000, 2_500, 3_000, 3_500,
                        4_000, 5_000, 7_500, 10_000, 15_000, 20_000, 50_000,
                        100_000]
        price_list = []
        supply_list = []

        for bal in balance_list:
            sup = bCurve.get_supply(bal)
            supply_list.append(sup)
            price_list.append(bCurve.get_price(sup))

        table_data = {"balance": [i * 1000 for i in balance_list],
                      "supply": [i * 1000 for i in supply_list], "price": price_list,
                      "mktCap": [supply_list[i] * price_list[i]*1000 for i in range(len(supply_list))]}

        # print(table_data)

        return table_data

    def get_allocation_table(self, steps_table, initial_reserve, common_pool):
        reserve_after = initial_reserve
        pool_after = common_pool

        # apply buy-in if present
        if not steps_table.empty and 0 in steps_table["step"].values:
            buy_row = steps_table.loc[steps_table['step'] == 0]

            reserve_after = buy_row.at[0, "newBalance"]
            pool_after = pool_after + buy_row.at[0, "tributeCollected"]

        table_data = {"commonPoolBefore": common_pool*1000, "reserveBalanceBefore": initial_reserve *
                      1000, "commonPoolAfter": pool_after*1000, "reserveBalanceAfter": reserve_after*1000}

        # print(table_data)

        return table_data

    # very basic validity check. TO DO expand balance and steplist checking

    def check_param_validity(self, commons_percentage, ragequit_amount, opening_price, entry_tribute, exit_tribute, initial_buy,  initial_commons_reserve, steplist, initial_supply, initial_balance, zoom_graph, plot_mode):
        if initial_buy < 0 or initial_buy > (TOTAL_HATCH_FUNDING - ragequit_amount):
            raise ValueError(
                "Error: The Initial Buy is either negative or bigger than the remaining Hatch Funding after Ragequits.")
        if commons_percentage < 0 or commons_percentage >= 1:
            raise ValueError(
                "Error: Commons Percentage Parameter out of bounds.")
        if ragequit_amount < 0:
            raise ValueError("Error: Invalid Ragequit Amount Parameter.")
        if opening_price <= 0:
            raise ValueError("Error: Invalid Initial Price Parameter.")
        if initial_supply <= 0:
            raise ValueError("Error: Intial Supply would be negative.")
        if initial_balance <= 0:
            raise ValueError("Error: Invalid  Balance would be negative.")
        if entry_tribute < 0 or entry_tribute >= 1:
            raise ValueError("Error: Invalid Entry Tribute Parameter.")
        if exit_tribute < 0 or exit_tribute >= 1:
            raise ValueError("Error: Invalid Exit Tribute Parameter.")
        if initial_commons_reserve <= 0:
            raise ValueError(
                "Error: The Initial commons reserve balance is zero or less")
        if not isinstance(steplist, list):
            # TO DO: in-depth validation of the steplist
            raise ValueError("Error: Invalid Steplist Parameter.")
        if not (zoom_graph == 0 or zoom_graph == 1):
            raise ValueError("Error: Invalid Graph Zoom Parameter.")
        if not (plot_mode == 0 or plot_mode == 1):
            raise ValueError("Error: Invalid Plot Mode Parameter.")
        # check resulting reserve ratio
        res_rat = initial_balance / \
            (opening_price * initial_supply)
        if res_rat <= 0.01 or res_rat >= 1:
            raise ValueError(
                "Error: The resulting reserve ratio is outside the range of 1% - 100%")

        return True
