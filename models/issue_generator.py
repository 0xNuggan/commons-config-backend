import pandas as pd
import requests
import json
import os
from dotenv import load_dotenv
from pymongo import MongoClient

from models.data.issue_submission_data import issue_data, advanced_settings_data
from models.token_lockup import TokenLockupModel
from models.conviction_voting import ConvictionVotingModel
from models.augmented_bonding_curve import BondingCurveHandler

load_dotenv() 

class IssueGeneratorModel:
    def __init__(self,
                 raw_body={},
                 title=None,
                 token_lockup=None,
                 abc=None,
                 tao_voting=None,
                 conviction_voting=None,
                 advanced_settings=None,
                 overall_strategy=None):
        self.raw_body = raw_body
        self.issue_number = 0
        self.title = title if title is not None else "TEC Config Dashboard Proposal test"
        self.overall_strategy = overall_strategy if overall_strategy is not None else ""
        self.token_lockup = token_lockup if token_lockup is not None else {
            "openingPrice": 5,
            "tokenFreeze": 20,
            "tokenThaw": 15,
            "strategy": ""
        }
        self.abc = abc if abc is not None else {
            "commonsTribute": 0.25,
            "ragequitAmount": 60,
            "initialBuy": 200,
            "openingPrice":1.65,
            "reserveBalance": 1571.22357,
            "entryTribute": 0.05,
            "exitTribute": 0.15,
            "hatchScenarioFunding": 1571.22357,
            "stepList": [[5000, "wxDai"], [100000, "wxDai"], [3000, "TEC"]],
            "zoomGraph": 0,
            "strategy": ""
        }
        self.tao_voting = tao_voting if tao_voting is not None else {
            "supportRequired": 40,
            "minimumQuorum": 10,
            "voteDuration": 7,
            "delegatedVotingPeriod": 3,
            "quietEndingPeriod": 2,
            "quietEndingExtension": 1,
            "executionDelay": 1,
            "strategy": ""
        }
        self.conviction_voting = conviction_voting if conviction_voting is not None else {
            "convictionGrowth": 2,
            "minimumConviction": 0.01,
            "votingPeriodDays": 7,
            "spendingLimit": 0.2,
            "strategy": ""
        }
        self.advanced_settings = advanced_settings

    def format_output_issue(self):
        token_lockup_model = TokenLockupModel(
            opening_price=self.token_lockup.get("openingPrice", ""),
            token_freeze_period=self.token_lockup.get("tokenFreeze", ""),
            token_thaw_period=self.token_lockup.get("tokenThaw", ""),
        )
        token_lockup_output = token_lockup_model.get_data().get("output", "")
        token_lockup_table = token_lockup_output.get("table", "")

        commons_percentage = self.abc.get("commonsTribute", 0.05)
        opening_price = self.abc.get("openingPrice", 3)
        entry_tribute = self.abc.get("entryTribute", 0.05)
        exit_tribute = self.abc.get("entryTribute", 0.05)
        scenario_reserve_balance = self.abc.get("reserveBalance", 1571.22357)
        steplist = self.abc.get("stepList", "")
        zoom_graph = self.abc.get("zoomGraph", 0)
        initial_buy = self.abc.get("initialBuy", 0)
        ragequit_amount = self.abc.get("ragequitAmount", 100)
    

        augmented_bonding_curve_model = BondingCurveHandler(
                        commons_percentage=commons_percentage,
                        ragequit_amount=ragequit_amount,
                        opening_price=opening_price,
                        entry_tribute=entry_tribute,
                        exit_tribute=exit_tribute,
                        scenario_reserve_balance=scenario_reserve_balance,
                        initial_buy=initial_buy,
                        steplist=steplist,
                        zoom_graph=zoom_graph)
        augmented_bonding_curve_output = augmented_bonding_curve_model.get_data()

        conviction_voting_model = ConvictionVotingModel(
            conviction_growth=self.conviction_voting.get("convictionGrowth", ""),
            minimum_conviction=self.conviction_voting.get("minimumConviction", ""),
            voting_period_days=self.conviction_voting.get("votingPeriodDays", ""),
            spending_limit=self.conviction_voting.get("spendingLimit", ""),
        )
        conviction_voting_output = conviction_voting_model.get_data().get("output", "")
        conviction_voting_table = conviction_voting_output.get("table", "")

        formated_abc_steps = ""
        abc_step_table = augmented_bonding_curve_output["stepTable"]
        for idx in range(len(abc_step_table['step'])):
            if idx > 0:
                formated_abc_steps += "| **Step {step}** | {current_price} | {amount_in} | {tribute_collected} | {amount_out} | {new_price} | {price_slippage} |\n".format(
                    step=abc_step_table["step"][idx],
                    current_price=abc_step_table["currentPriceParsed"][idx],
                    amount_in=abc_step_table["amountInParsed"][idx],
                    tribute_collected=abc_step_table["tributeCollectedParsed"][idx],
                    amount_out=abc_step_table["amountOutParsed"][idx],
                    new_price=abc_step_table["newPriceParsed"][idx],
                    price_slippage=abc_step_table["slippage"][idx]
                )

        formated_advanced_settings_data = advanced_settings_data.format(
            issue_number=self.issue_number,
            commons_pool_amount=self.advanced_settings.get("commonPoolAmount", ""),
            hny_liquidity=self.advanced_settings.get("HNYLiquidity", ""),
            garden_liquidity=self.advanced_settings.get("gardenLiquidity", ""),
            virtual_supply=self.advanced_settings.get("virtualSupply", ""),
            virtual_balance="{:,}".format(self.advanced_settings.get("virtualBalance", "")),
            transferability=self.advanced_settings.get("transferability", ""),
            token_name=self.advanced_settings.get("tokenName", ""),
            token_symbol=self.advanced_settings.get("tokenSymbol", ""),
            proposal_deposit=self.advanced_settings.get("proposalDeposit", ""),
            challenge_deposit=self.advanced_settings.get("challengeDeposit", ""),
            settlement_period=self.advanced_settings.get("settlementPeriod", ""),
            minimum_effective_supply=100 * self.advanced_settings.get("minimumEffectiveSupply", ""),
            hatchers_rage_quit=self.advanced_settings.get("ragequitAmount", ""),
            initial_buy=self.advanced_settings.get("initialBuy", ""),
        )

        formated_output = issue_data.format(
            issue_number=self.issue_number,
            overall_strategy=self.overall_strategy,

            token_lockup_strategy=self.token_lockup.get("strategy", ""),
            token_freeze_period=self.token_lockup.get("tokenFreeze", ""),
            token_thaw_period=self.token_lockup.get("tokenThaw", ""),
            opening_price=self.token_lockup.get("openingPrice", ""),
            tokens_released=["{0:.2f}".format(100 * item) for item in token_lockup_table["tokensReleased"]],
            price_floor=["{0:.2f}".format(item) for item in token_lockup_table["price"]],

            abc_strategy=self.abc.get("strategy", ""),
            commons_tribute="{0:.2f}".format(100 * self.abc.get("commonsTribute", "")),
            commons_tribute_remainder="{0:.2f}".format(100 - 100 * self.abc.get("commonsTribute", "")),
            entry_tribute="{0:.2f}".format(100 * self.abc.get("entryTribute", "")),
            exit_tribute="{0:.2f}".format(100 * self.abc.get("exitTribute", "")),
            reserve_ratio="{0:.2f}".format(100 * augmented_bonding_curve_output["chartData"]["reserveRatio"]),
            step=augmented_bonding_curve_output["stepTable"]["step"],
            current_price=augmented_bonding_curve_output["stepTable"]["currentPriceParsed"],
            amount_in=augmented_bonding_curve_output["stepTable"]["amountInParsed"],
            tribute_collected=augmented_bonding_curve_output["stepTable"]["tributeCollectedParsed"],
            amount_out=augmented_bonding_curve_output["stepTable"]["amountOutParsed"],
            new_price=augmented_bonding_curve_output["stepTable"]["newPriceParsed"],
            price_slippage=augmented_bonding_curve_output["stepTable"]["slippage"],
            common_pool_before="{0:.2f}".format(augmented_bonding_curve_output["fundAllocations"]["commonPoolBefore"]),
            reserve_balance_before="{0:.2f}".format(augmented_bonding_curve_output["fundAllocations"]["reserveBalanceBefore"]),
            common_pool_after="{0:.2f}".format(augmented_bonding_curve_output["fundAllocations"]["commonPoolAfter"]),
            reserve_balance_after="{0:.2f}".format(augmented_bonding_curve_output["fundAllocations"]["reserveBalanceAfter"]),
            abc_steps=formated_abc_steps,
            abc_reserve=augmented_bonding_curve_output["milestoneTable"].get("balance", ""),
            abc_supply=augmented_bonding_curve_output["milestoneTable"].get("supply", ""),
            abc_price=augmented_bonding_curve_output["milestoneTable"].get("price", ""),

            tao_voting_strategy=self.tao_voting.get("strategy", ""),
            support_required=self.tao_voting.get("supportRequired", ""),
            minimum_quorum=self.tao_voting.get("minimumQuorum", ""),
            double_conviction_growth_days=2*self.tao_voting.get("voteDuration", ""),
            vote_duration_days=self.tao_voting.get("voteDuration", ""),
            delegated_voting_days=self.tao_voting.get("delegatedVotingPeriod", ""),
            quiet_ending_days=self.tao_voting.get("quietEndingPeriod", ""),
            quiet_ending_extension_days=self.tao_voting.get("quietEndingExtension", ""),
            execution_delay_days=self.tao_voting.get("executionDelay", ""),
            vote_duration_days_1_extension=self.tao_voting.get("voteDuration", "") + self.tao_voting.get("quietEndingExtension", ""),
            vote_duration_days_2_extensions=self.tao_voting.get("voteDuration", "") + (2 * self.tao_voting.get("quietEndingExtension", "")),
            review_duration_days=self.tao_voting.get("voteDuration", "") - self.tao_voting.get("delegatedVotingPeriod", ""),
            review_duration_days_1_extension=self.tao_voting.get("voteDuration", "") - self.tao_voting.get("delegatedVotingPeriod", "") + self.tao_voting.get("quietEndingExtension", ""),
            review_duration_days_2_extensions=self.tao_voting.get("voteDuration", "") - self.tao_voting.get("delegatedVotingPeriod", "") + (2 * self.tao_voting.get("quietEndingExtension", "")),
            execute_proposal_duration_days=self.tao_voting.get("voteDuration", "") + self.tao_voting.get("executionDelay", ""),
            execute_proposal_duration_days_1_extension=self.tao_voting.get("voteDuration", "") + self.tao_voting.get("executionDelay", "") + self.tao_voting.get("quietEndingExtension", ""),
            execute_proposal_duration_days_2_extensions=self.tao_voting.get("voteDuration", "") + self.tao_voting.get("executionDelay", "") + (2 * self.tao_voting.get("quietEndingExtension", "")),

            conviction_voting_strategy=self.conviction_voting.get("strategy", ""),
            conviction_growth_days=self.conviction_voting.get("convictionGrowth", ""),
            minimum_conviction=100 * self.conviction_voting.get("minimumConviction", ""),
            relative_spending_limit=100 * self.conviction_voting.get("spendingLimit", ""),
            effective_supply=conviction_voting_table["totalEffectiveSupply"],
            requested_amount=conviction_voting_table["requestedAmount"],
            amount_common_pool=conviction_voting_table["amountInCommonPool"],
            min_tokens_pass=conviction_voting_table["minTokensToPass"],
            tokens_pass_2_weeks=conviction_voting_table["tokensToPassIn2Weeks"],

            has_advanced_settings="Yes" if self.advanced_settings else "No",
            advanced_settings_section=formated_advanced_settings_data if self.advanced_settings else ""
        )
        return formated_output

    def save_parameters_database(self, issue_number):
        MONGODB_CLIENT = os.getenv("MONGODB_CLIENT")
        client = MongoClient(MONGODB_CLIENT)
        db = client.get_database("test_tec_params_db")
        test_params_db = db.test_params
        self.raw_body["issue_number"] = issue_number
        issue_data = self.raw_body

        test_params_db.insert_one(issue_data)

    def generate_output(self):
        PARAMS_BOT_AUTH_TOKEN = os.getenv("PARAMS_BOT_AUTH_TOKEN")
        headers = {'Content-Type': 'application/json', 'Authorization': PARAMS_BOT_AUTH_TOKEN}
        r_issue_data = requests.get('https://api.github.com/search/issues?q=repo:CommonsBuild/test-issues-config-dashboard')
        self.issue_number = 1 + r_issue_data.json().get("total_count", "")
        data = {"title": self.title, "body": self.format_output_issue()}
        
        r = requests.post('https://api.github.com/repos/CommonsBuild/test-issues-config-dashboard/issues', data=json.dumps(data), headers=headers)

        if r.status_code == 201:
            issue_number = r.json().get("number", "")
            self.save_parameters_database(issue_number=issue_number)
 
        return {"status": r.status_code, "url": r.json().get("html_url", "")}
