from web3 import Web3
from web3.middleware import geth_poa_middleware
import datetime
from os.path import dirname as up
import json
import os
import requests
import re
from time import sleep, time
import asyncio
from concurrent.futures import ThreadPoolExecutor


class BlockchainData:
    def __init__(self, network, dex):
        # Load config file and ABI's
        parent_dir = os.path.abspath(up(__file__))
        filepath = os.path.join(up(parent_dir), 'binaries')
        configFile = filepath + "/config.json"
        networkFile = filepath + "/network_info.json"
        avaxABI = filepath + "/avax_abi.json"
        pcsABI = filepath + "/psc_abi.json"
        balanceABI = filepath + "/balance_abi.json"
        erc20ABI = filepath + "/erc20_abi.json"
        treasuryABI = filepath + "/treasury_abi.json"
        ravpoolABI = filepath + "/ravpool_abi.json"
        rsharepoolABI = filepath + "/rsharepool_abi.json"
        routersFile = filepath + "/routers.json"
        currencyFile = filepath + "/currency_adds.json"
        weiFile = filepath + "/wei_values.json"

        with open(networkFile) as f:
            self.network_info = json.load(f)
        with open(routersFile) as f:
            self.router_info = json.load(f)
        with open(configFile) as f:
            self.config = json.load(f)
        with open(pcsABI) as f:
            self.pcs_abi = json.load(f)
        with open(avaxABI) as f:
            self.avax_abi = json.load(f)
        with open(balanceABI) as f:
            self.balance_check_abi = json.load(f)
        with open(erc20ABI) as f:
            self.erc20_abi = json.load(f)
        with open(currencyFile) as f:
            self.currency_file = json.load(f)
        with open(weiFile) as f:
            self.wei_file = json.load(f)
        with open(treasuryABI) as f:
            self.treasury_abi = json.load(f)
        with open(ravpoolABI) as f:
            self.ravpool_abi = json.load(f)
        with open(rsharepoolABI) as f:
            self.rsharepool_abi = json.load(f)

        for net_info in self.network_info:
            if net_info["NETWORK"] == network:
                self.rpc_url = net_info["RPC"]
                self.chainId = net_info["CHAIN"]
                self.native_address = Web3.toChecksumAddress(net_info["NATIVE"][1])
                self.native_token = net_info["NATIVE"][0]
                self.stablecoin = net_info["STABLE"][1]

        for routers in self.router_info:
            if routers["NETWORK"] == network and routers["DEX"] == dex:
                self.router_address = Web3.toChecksumAddress(routers["ROUTER"])
                self.router_abi = routers["ABI"]

        if not self.router_address:
            self.router_address = Web3.toChecksumAddress(dex)
            self.router_abi = "PCS"

        if self.router_abi == "PCS":
            self.router_abi = self.pcs_abi
        elif self.router_abi == "AVAX":
            self.router_abi = self.avax_abi

        # Connect to RPC
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)

        # Load Router Contract
        self.router_contract = self.w3.eth.contract(
            address=self.router_address, abi=self.router_abi)

        # Stablecoin address
        self.stable_address = Web3.toChecksumAddress(
            self.stablecoin)

        # Ravelin specifics
        self.treasury_contract = self.w3.eth.contract(address=Web3.toChecksumAddress("0x351bDAC12449974e98C9bd2FBa572EdE21C1b7C4"),
                                                      abi=self.treasury_abi)
        self.boardroom_address = Web3.toChecksumAddress("0x618C166262282DcB6Cdc1bFAB3808e2fa4ADFEc2")

        self.rav_address = Web3.toChecksumAddress("0x9B7c74Aa737FE278795fAB2Ad62dEFDbBAedFBCA")
        self.rav_contract = self.w3.eth.contract(address=self.rav_address, abi=self.erc20_abi)

        self.rshare_address = Web3.toChecksumAddress("0xD81E377E9cd5093CE752366758207Fc61317fC70")
        self.rshare_contract = self.w3.eth.contract(address=self.rshare_address, abi=self.erc20_abi)

        self.ravpool_address = Web3.toChecksumAddress("0x9F6fFbE7BE08784bFe2297eBEb80E0F21bF72F3F")
        self.ravpool_contract = self.w3.eth.contract(address=self.ravpool_address, abi=self.ravpool_abi)

        self.rsharepool_address = Web3.toChecksumAddress("0xa85B4e44A28B5F10b3d5751A68e03E44B53b7e89")
        self.rsharepool_contract = self.w3.eth.contract(address=self.rsharepool_address, abi=self.rsharepool_abi)

        self.rav_lp_address = Web3.toChecksumAddress("0xd65005ef5964b035b3a2a1e79ddb4522196532de")
        self.rav_lp_contract = self.w3.eth.contract(address=self.rav_lp_address, abi=self.erc20_abi)

        self.rshare_lp_address = Web3.toChecksumAddress("0x73bc306Aa2D393ff5aEb49148b7B2C9a8E5d39c8")
        self.rshare_lp_contract = self.w3.eth.contract(address=self.rshare_lp_address, abi=self.erc20_abi)

        self.stable_contract = self.w3.eth.contract(address=self.stable_address, abi=self.erc20_abi)

        self.amount_in = Web3.toWei(1, 'ether')
        self.gasLimit = 400000

    def get_prices(self, token):
        decimals = "ether"
        token_name = ""
        if token == self.stable_address:
            decimals = "mwei"
            token_name = "ADA"
        elif token == self.rshare_address:
            token_name = "RSHARE"
        elif token == self.rav_address:
            token_name = "RAV"

        usdc_out = self.router_contract.functions.getAmountsOut(
            self.amount_in, [self.native_address, token]).call()[1]
        usdc_out = Web3.fromWei(usdc_out, decimals)

        return {token_name: float(usdc_out)}

    def get_balances(self, address):
        token = ""
        name = ""
        if address == self.rav_lp_address or address == self.rshare_lp_address:
            token = self.native_address
            if address == self.rav_lp_address:
                name = "RAV_LP_ADA"
            else:
                name = "RSHARE_LP_ADA"
        elif address == self.rsharepool_address or address == self.boardroom_address:
            token = self.rshare_address
            if address == self.rsharepool_address:
                name = "RSHAREPOOL_BALANCE"
            else:
                name = "BOARDROOM_BALANCE"
        balance = int(Web3.fromWei(self.w3.eth.contract(
            address=token, abi=self.balance_check_abi).functions.balanceOf(
            address).call({'from': token}), "ether"))

        return {name: balance}

    def get_total_supply(self, address):
        name = ""
        if address == self.rav_lp_contract:
            name = "RAV_LP_TOTAL"
        elif address == self.rshare_lp_contract:
            name = "RSHARE_LP_TOTAL"
        elif address == self.rav_contract:
            name = "RAV_TOTAL"
        elif address == self.rshare_contract:
            name = "RSHARE_TOTAL"
        total_supply = Web3.fromWei(address.functions.totalSupply().call(), "ether")

        return {name: total_supply}

    async def get_ravelin_stats(self):
        # Get current price of BNB in USD
        price_result_list = []
        tokens = [self.stable_address, self.rav_address, self.rshare_address]
        with ThreadPoolExecutor(max_workers=3) as executor:
            for i in tokens:
                prices = executor.submit(self.get_prices, i)
                price_result_list.append(prices)
        prices = []
        for j in price_result_list:
            new_result = j.result(timeout=60)
            prices.append(new_result)

        for i in prices:
            if "ADA" in i.keys():
                usdc_out = i['ADA']
            if "RAV" in i.keys():
                ravOut = i['RAV']
            if "RSHARE" in i.keys():
                rshareOut = i['RSHARE']

        balance_result_list = []
        balance_addresses = [self.rav_lp_address, self.rshare_lp_address, self.rsharepool_address, self.boardroom_address]
        with ThreadPoolExecutor(max_workers=4) as executor:
            for i in balance_addresses:
                balances = executor.submit(self.get_balances, i)
                balance_result_list.append(balances)
        balances_list = []
        for j in balance_result_list:
            new_result = j.result(timeout=60)
            balances_list.append(new_result)
        for i in balances_list:
            if "RAV_LP_ADA" in i.keys():
                rav_lp_ada = i['RAV_LP_ADA']
            if "RSHARE_LP_ADA" in i.keys():
                rshare_lp_ada = i['RSHARE_LP_ADA']
            if "RSHAREPOOL_BALANCE" in i.keys():
                rshare_pool_balance = i["RSHAREPOOL_BALANCE"]
            if "BOARDROOM_BALANCE" in i.keys():
                boardroom_balance = i['BOARDROOM_BALANCE']

        total_supply_contracts = [self.rav_lp_contract, self.rshare_lp_contract, self.rav_contract, self.rshare_contract]
        total_supply_result_list = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            for i in total_supply_contracts:
                total_supply = executor.submit(self.get_total_supply, i)
                total_supply_result_list.append(total_supply)
        total_supply_list = []
        for j in total_supply_result_list:
            new_result = j.result(timeout=60)
            total_supply_list.append(new_result)
        for i in total_supply_list:
            if "RAV_LP_TOTAL" in i.keys():
                rav_lp_supply = i['RAV_LP_TOTAL']
            if "RSHARE_LP_TOTAL" in i.keys():
                rshare_lp_supply = i['RSHARE_LP_TOTAL']
            if "RAV_TOTAL" in i.keys():
                rav_circulating = int(i["RAV_TOTAL"])
            if "RSHARE_TOTAL" in i.keys():
                rshare_total = int(i['RSHARE_TOTAL'])

        # Calculate Token price in USDC
        real_rav = "{:0.4f}".format(float(usdc_out) / float(ravOut))
        real_rshare = "{:0.4f}".format(float(usdc_out) / float(rshareOut))
        real_ada = "{:0.4f}".format(float(usdc_out))

        # Get LP token prices
        rav_lp_price = "{:0.4f}".format(float(rav_lp_ada) * float(real_ada) * 2 / float(rav_lp_supply))
        rshare_lp_price = "{:0.4f}".format(float(rshare_lp_ada) * float(real_ada) * 2 / float(rshare_lp_supply))

        # RSHARE circulating
        rshare_circulating = rshare_total - rshare_pool_balance

        # RSHARE locked in br
        rshare_locked_pct = "{:0.1f}".format(boardroom_balance / rshare_circulating * 100)

        # TVL
        rshare_tvl = float(rshare_lp_supply) * float(rshare_lp_price)
        rav_tvl = float(rav_lp_supply) * float(rav_lp_price)
        boardroom_tvl = float(boardroom_balance) * float(real_rshare)
        total_tvl = "{:0.2f}".format(rshare_tvl + rav_tvl + boardroom_tvl)

        # Epochs
        next_epoch = self.treasury_contract.functions.nextEpochPoint().call()
        countdown = datetime.datetime.utcfromtimestamp(next_epoch) - datetime.datetime.utcnow()
        s = countdown.total_seconds()
        hours, remainder = divmod(s, 3600)
        minutes, seconds = divmod(remainder, 60)
        current_epoch = self.treasury_contract.functions.epoch().call()
        next_epoch = '{:02}h {:02}m {:02}s'.format(int(hours), int(minutes), int(seconds))

        # Peg
        peg = "{:0.3f}".format(float(Web3.fromWei(self.treasury_contract.functions.getRAVUpdatedPrice().call(), "ether")))

        # APRs
        rshare_per_day = float(Web3.fromWei(self.rsharepool_contract.functions.rSharePerSecond().call(), "ether")) * 86400
        rav_mada_alloc = 0.6 * rshare_per_day
        rav_mada_daily_roi = "{:0.2f}".format(1 / rav_tvl * rav_mada_alloc * float(real_rshare) / 1 * 100)

        rshare_mada_alloc = 0.4 * rshare_per_day
        rshare_mada_daily_roi = "{:0.2f}".format(1 / rshare_tvl * rshare_mada_alloc * float(real_rshare) / 1 * 100)

        if rav_circulating < 200000:
            expansion_rate = 0.045
        elif rav_circulating < 400000:
            expansion_rate = 0.04
        elif rav_circulating < 600000:
            expansion_rate = 0.035
        elif rav_circulating < 1000000:
            expansion_rate = 0.03
        elif rav_circulating < 2000000:
            expansion_rate = 0.02
        elif rav_circulating < 5000000:
            expansion_rate = 0.015
        else:
            expansion_rate = 0.01

        boardroom_daily_alloc = float(rav_circulating) * float(expansion_rate) * 4
        boardroom_daily_roi = "{:0.2f}".format(1 / float(boardroom_tvl) * boardroom_daily_alloc * float(real_rav) * 100)

        return {"rav_price": real_rav, "rshare_price": real_rshare, "ada_price": real_ada, "tvl": total_tvl, "next_epoch": next_epoch,
                "current_epoch": current_epoch, "rav_mada_apr": rav_mada_daily_roi, "rshare_mada_apr": rshare_mada_daily_roi,
                "boardroom_apr": boardroom_daily_roi, "circulating_rav": rav_circulating, "circulating_rshare": rshare_circulating,
                "rshare_locked_pct": rshare_locked_pct, "rshare_locked": int(boardroom_balance), "peg": peg}