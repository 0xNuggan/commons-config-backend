import os
import pandas as pd
import numpy as np


#These numbers are fixed from the hatch results (all in thousands except the token price)
TOTAL_HATCH_FUNDING = 1571.22357 
TOTAL_INITIAL_TECH_SUPPLY= 2035.918945 
HATCH_FINAL_TECH_PRICE = 0.754743 


class BondingCurveInitializer:

    def __init__(self, reserve_balance=100, opening_price=5, initial_supply=100):
        self.opening_price = opening_price
        self.initial_supply = initial_supply
        self.initial_balance = reserve_balance

    def reserve_ratio(self):
        return self.initial_balance / (self.opening_price * self.initial_supply)
    
    #Returns the token price given a specific supply
    def get_price(self, supply):
        return (supply ** ((1 / self.reserve_ratio()) - 1) * self.opening_price) / (
            self.initial_supply ** ((1 / self.reserve_ratio()) - 1)
        )

    #Returns the collateral balance price given a specific supply
    def get_balance(self, supply):
        return (
            self.reserve_ratio() * self.get_price(supply) * supply
        )

    #Returns supply at a specific balance. THIS IS AN APPROXIMATION only meant for visualizing scenarios
    def get_supply(self, balance):
        supply_ref = 0
        while self.get_balance(supply_ref) <  balance:
            supply_ref = supply_ref + 10

        df = self.curve_over_balance(supply_ref-10, supply_ref, 100000)
        df_rounded = df.round(3)
        
        index= int(df.index.where(df_rounded['balanceInThousands'] >= balance).dropna()[0])
        price = df.at[index, "price"]

        supply = balance/(price* self.reserve_ratio())
        

        return supply

    #For drawing the bonding curve. Range shows how many times the initial supply you make the graph for, steps how many subdivisions
    def curve_over_supply(self, range_begin=0, range_end=1000, steps=500):
        x = np.linspace(range_begin, range_end, steps)
        y = self.get_price(x)

        return pd.DataFrame(zip(x, y), columns=["supplyInThousands", "price"])
    
    def curve_over_balance(self, range_begin=0, range_end=1000, steps=500):
        supply_list = np.linspace(range_begin, range_end, steps)
        x = self.get_balance(supply_list)
        y = self.get_price(supply_list)

        return pd.DataFrame(zip(x, y), columns=["balanceInThousands", "price"])



class BondingCurve(BondingCurveInitializer):

    def __init__(self, reserve_balance=100, opening_price=5, initial_supply=100, entry_tribute=0.05, exit_tribute=0.05):
        super().__init__(reserve_balance, opening_price, initial_supply)
        self.current_supply = self.initial_supply
        self.current_balance = self.get_balance(self.initial_supply)
        self.entry_tribute = entry_tribute
        self.exit_tribute = exit_tribute

    def set_new_supply(self, new_supply):
        self.current_supply = new_supply
        self.current_balance = self.get_balance(new_supply)

    #Returns how much wxDAI you get from selling TEC. Informative, doesn't change state
    def sale_return(self, bonded):
        return self.current_balance * (
            (bonded / self.current_supply + 1) ** (1 / self.reserve_ratio()) - 1
        )

    #Returns how much TEC you get from purchasing with wxDAI. Informative, doesn't change state
    def purchase_return(self, collateral):
        return self.current_supply * (
            (collateral / self.current_balance + 1) ** (self.reserve_ratio()) - 1
        )



class BondingCurveHandler():
    '''
    The handler for the Bonding Curve. All interaction happens through this.

    The constrctor receives following args:

    commons_percentage: float between 0-0.95. Percentage of funds that get substracted from the total funding to go to the commons pool
    ragequit_amount: float, wxDai in thousands . Amount of reserve returned to ragequitters before the bonding curve gets initialized
    opening_price: float. No real limit but, expected to be between 1 and 4
    entry_tribute: float between 0-0.99. Percentage of funds substracted on buy (mint) operations before interacting with the bonding curve
    exit_tribute: float between 0-0.99. Percentage of funds substracted on sell (burn) operations after interacting with the boding curve
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
                 scenario_reserve_balance,
                 steplist,
                 zoom_graph=0,
                 plot_mode=0):

        #parse the steplist (which gets read as string) into the right format
        steplist_parsed = []
        if steplist != "":
            for step in steplist:
                buf = str(step).strip('][').split(', ')
                buf[0] = (float(buf[0]) / 1000)
                buf[1] = buf[1].strip("'")
                steplist_parsed.append(buf)

        params_valid = self.check_param_validity( 
                 commons_percentage,
                 ragequit_amount,
                 opening_price,
                 entry_tribute,
                 exit_tribute,
                 initial_buy,
                 float(scenario_reserve_balance),
                 steplist_parsed,
                 int(zoom_graph),
                 int(plot_mode)
                 )
        #The numbers for initial supply and taken from the constants
        self.bonding_curve = self.create_bonding_curve(commons_percentage=commons_percentage, ragequit_amount=ragequit_amount, opening_price=opening_price, entry_tribute= entry_tribute, exit_tribute= exit_tribute, initial_buy=initial_buy)
        
        #If there is an initial buy, perform it here  
        self.steps_table = pd.DataFrame()  
        if initial_buy > 0: 
            #the buy-in gets saved as "step zero"
            self.steps_table = self.steps_table.append(self.generate_outputs_table(bondingCurve= self.bonding_curve, steplist= [[initial_buy, "wxDai"]]))
            self.steps_table["step"] = 0


        #set the current supply to the point where the scenarios are going to happen (if it isn't the launch situation)
        # if it's the launch situation, the supply change from the buy in has already been saved before
        # rounded a bit to make sure it gets triggered when necessary
        adjusted_start_balance = round((TOTAL_HATCH_FUNDING * (1- commons_percentage)), 3)
        if(round(scenario_reserve_balance, 3) != adjusted_start_balance):
            scenario_supply= self.bonding_curve.get_supply(float(scenario_reserve_balance))
            self.bonding_curve.set_new_supply(scenario_supply)
        
        #calculate the scenarios
        self.steps_table = self.steps_table.append(self.generate_outputs_table(bondingCurve= self.bonding_curve, steplist= steplist_parsed))
        self.zoom_graph = zoom_graph
        self.plot_mode = plot_mode
    

    def get_data(self):

        [min_range, max_range] = self.get_scenario_range(steps_table= self.steps_table, zoom_graph=self.zoom_graph)

        clean_figure_data = self.get_data_augmented_bonding_curve(bondingCurve= self.bonding_curve, min_range=min_range, max_range=max_range, plot_mode=self.plot_mode).to_dict(orient='list')
        clean_figure_data['reserveRatio'] = self.bonding_curve.reserve_ratio()
        
        figure_bonding_curve= {"chartData": {}}
        figure_milestone_table =self.get_milestone_table(self.bonding_curve) 
        
        if self.steps_table.empty:
            figure_bonding_curve['chartData'] = clean_figure_data
            figure_bonding_curve['milestoneTable'] = figure_milestone_table
            return figure_bonding_curve
        else: 
            figure_buy_sell_table =self.steps_table.loc[:,["step", "currentPriceParsed", "currentSupplyParsed","amountInParsed", "tributeCollectedParsed", "amountOutParsed", "newPriceParsed", "slippage"]].to_dict(orient='list')
            extended_figure_data = clean_figure_data
            #get single points with full coordinates
            extended_figure_data['singlePoints'] = self.get_single_point_coordinates(self.steps_table)
            #get linspace from every step.
            extended_figure_data['stepLinSpaces'] = self.get_step_linspaces(self.bonding_curve, self.steps_table)

            #For debugging purposes
            #print(self.steps_table.loc[:,["step", "currentPrice", "currentSupply", "currentBalance", "amountIn", "tributeCollected", "amountOut", "newPrice", "newSupply", "newBalance", "slippage"]])

            figure_bonding_curve['chartData'] = extended_figure_data
            figure_bonding_curve['stepTable'] = figure_buy_sell_table
            figure_bonding_curve['milestoneTable'] = figure_milestone_table

            return figure_bonding_curve

    def create_bonding_curve(self, commons_percentage=0.5, ragequit_amount=100,  opening_price=3, entry_tribute=0.05, exit_tribute=0.05, initial_buy=0):
        
        initial_supply = TOTAL_INITIAL_TECH_SUPPLY - (ragequit_amount / HATCH_FINAL_TECH_PRICE)
        hatch_funding= TOTAL_HATCH_FUNDING  - ragequit_amount  - initial_buy

        initial_reserve = hatch_funding * (1 - commons_percentage)
        
        bCurve = BondingCurve(initial_reserve, opening_price, initial_supply, entry_tribute, exit_tribute)

        return bCurve

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
            #current_supply_parsed = str(format(current_supply, '.2f')) + "k TEC"
            current_supply_parsed = round(current_supply*1000, 2) 

            current_price = bondingCurve.get_price(current_supply)
            #current_price_parsed = str(format(current_price, '.2f')) + " wxDAI"
            current_price_parsed = round(current_price, 2)

            current_balance = float(bondingCurve.current_balance)
            #current_balance_parsed = str(format(current_balance, '.2f')) + " wxDAI"
            current_balance_parsed = round(current_balance*1000, 2) 

            amount_in = step[0]
            token_type = "wxDAI" if step[1] == "wxDai" else step[1] #to avoid the most obvious error. TO DO: in-depth validation of the steplist...
            
            amount_in_parsed = str(format(amount_in*1000, '.2f')) + " " +  str(token_type)
            #amount_in_parsed = str(round(amount_in, 2)) + "k " + str(token_type)
        
            amount_out = 0
            amount_out_parsed = ""
            new_supply = 0
            tribute_collected = 0
            if token_type == "wxDAI":
                # take tribute and buy
                tribute_collected = amount_in * bondingCurve.entry_tribute
                amountAfterTribute = amount_in - tribute_collected

                amount_out = bondingCurve.purchase_return(amountAfterTribute)
                amount_out_parsed = str(format(amount_out*1000, '.2f')) + " TEC"
                #amount_out_parsed = round(amount_out*1000, 2)
                
                #tribute_collected_parsed = str(format(tribute_collected, '.2f')) + "k wxDAI"
                tribute_collected_parsed = round(tribute_collected*1000, 2)

                slippage = (amount_in - tribute_collected)/bondingCurve.get_price(current_supply) - amount_out
                slippage_pct = slippage / ((amount_in - tribute_collected)/bondingCurve.get_price(current_supply))
                slippage_pct = str(format((slippage_pct*100), '.2f')) + "%"

                new_supply = max(
                    0, current_supply + amount_out
                )
            elif token_type == "TEC":
                #this section works, but all the -1 mults are a bit of a mess. 
                # sell and take tribute
                amount_in = amount_in * -1 #because we are reducing the supply (burning)
                amountBeforeTribute = bondingCurve.sale_return(amount_in)            

                tribute_collected = amountBeforeTribute * bondingCurve.exit_tribute  #since it is a sale, the number returned is negative
                #tribute_collected_parsed = str(format((tribute_collected * -1), '.2f')) + "k wxDAI"
                tribute_collected_parsed = round((tribute_collected*-1000), 2)

                amount_out = (amountBeforeTribute - tribute_collected) #we leave it negative for the supply calculations down below
                amount_out_parsed = str(format((amount_out*-1000), '.2f')) + " wxDAI" 
                #amount_out_parsed = str(round((amount_out*-1), 2)) + "k wxDAI"

                slippage = ((amount_in*(1-bondingCurve.exit_tribute))*bondingCurve.get_price(current_supply) - amount_out) *-1
                slippage_pct = slippage / ((amount_in*(1-bondingCurve.exit_tribute))*bondingCurve.get_price(current_supply)) *-1
                slippage_pct = str(format((slippage_pct*100), '.2f')) + "%"
                
                new_supply = max(
                    0, (current_supply + amount_in),
                )


            new_price = bondingCurve.get_price(new_supply)
            #new_price_parsed = str(format(new_price, '.2f')) + " wxDAI"
            new_price_parsed = round(new_price, 2)

            #new_supply_parsed = str(format(new_supply, '.2f')) + "k TEC"
            new_supply_parsed = round(new_supply*1000, 2) 

            new_balance = bondingCurve.get_balance(new_supply)
            #new_balance_parsed = str(format(new_balance, '.2f')) + " wxDAI"
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

            # update current supply and balance 
            bondingCurve.set_new_supply(new_supply)

        #print(outputTable)
        return outputTable

    def get_data_augmented_bonding_curve(self, bondingCurve, min_range, max_range, plot_mode=0):
        
        if plot_mode == 0:
            curve_draw = bondingCurve.curve_over_balance(min_range, max_range)
        elif plot_mode == 1:
            curve_draw = bondingCurve.curve_over_supply(min_range, max_range)
        
        return curve_draw

    def get_single_point_coordinates(self, steps_table):

        coord_list= []
        
        for index, row in steps_table.iterrows():
            #point = {'x' : row['currentBalance'], 'y': row['currentPrice'], 'pointSupply': row['currentSupply']}
            point = {'x' : row['currentBalance'], 'y': row['currentPrice']}
            coord_list.append(point)          
        
        last_row = steps_table.iloc[-1]
        #last_point = {'x' : last_row['newBalance'], 'y': last_row['newPrice'], 'pointSupply': row['newSupply']}
        last_point = {'x' : last_row['newBalance'], 'y': last_row['newPrice']}
        coord_list.append(last_point) 

        return coord_list

    def get_step_linspaces(self, bondingCurve, steps_table):

        linspace_list = []

        for index, row in steps_table.iterrows():
            lin_step_df = bondingCurve.curve_over_balance(bondingCurve.get_supply(row['currentBalance']), bondingCurve.get_supply(row['newBalance']), steps=100)
            lin_step_df = lin_step_df.rename(columns={"balanceInThousands": "x", "price": "y"})
            lin_step = lin_step_df.to_dict(orient='list')
            #print("Interval:" + str(row['currentBalance']) + " - " + str(row['newBalance']))
            linspace_list.append(lin_step)

        return linspace_list


    def get_scenario_range(self, steps_table, zoom_graph=0):

        if steps_table.empty :
            min_range = 0
            max_range = 500
        else:
            min_range = 0 if  zoom_graph == 0 else ( min(steps_table['currentSupply'].min(), steps_table['newSupply'].min()) - 50)
            max_range = steps_table['newSupply'].max() + (200 if zoom_graph == 0 else 50)


        return [min_range, max_range]

    def get_milestone_table(self, bCurve):
        balance_list  = [250, 500, 1000, 2000, 3000, 5000, 10000]
        price_list = []
        supply_list = []

        for bal in balance_list:
            sup = bCurve.get_supply(bal)
            supply_list.append(sup)
            price_list.append(bCurve.get_price(sup))
        
        #print(balance_list)
        #print(price_list)
        #print(supply_list)

        table_data = { "balance": balance_list, "supply": supply_list, "price": price_list}

        return table_data

    def check_param_validity(self, commons_percentage, ragequit_amount, opening_price, entry_tribute, exit_tribute, initial_buy,  scenario_reserve_balance,  steplist, zoom_graph, plot_mode):
        if commons_percentage < 0 or commons_percentage > 0.95:
            raise ValueError("Error: Invalid Commons Percentage Parameter.")
        if ragequit_amount < 0:
            raise ValueError("Error: Invalid Ragequit Amount Parameter.")
        if opening_price <=0:
            raise ValueError("Error: Invalid Initial Price Parameter.")
        if entry_tribute < 0 or entry_tribute >= 1:
            raise ValueError("Error: Invalid Entry Tribute Parameter.")
        if exit_tribute < 0 or exit_tribute >= 1:
            raise ValueError("Error: Invalid Exit Tribute Parameter.")
        if initial_buy < 0 or initial_buy > (TOTAL_HATCH_FUNDING - ragequit_amount):
            raise ValueError("Error: The Initial Buy is either negative or bigger than the remaining Hatch Funding after Ragequits.")
        if scenario_reserve_balance <= 0:
            raise ValueError("Error: Invalid  Hatch Scenario Funding Parameter.")
        if not isinstance(steplist, list):
            #TO DO: in-depth validation of the steplist
            raise ValueError("Error: Invalid Steplist Parameter.")
        if not (zoom_graph == 0 or zoom_graph == 1):
            raise ValueError("Error: Invalid Graph Zoom Parameter.")
        if not (plot_mode == 0 or plot_mode == 1):
            raise ValueError("Error: Invalid Plot Mode Parameter.")
        
        return True

    