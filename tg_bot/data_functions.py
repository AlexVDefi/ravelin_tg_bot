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
import threading


class BlockchainData:
    def __init__(self, network, dex, token_address):
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

        # Token properly formatted for web3
        self.token = (Web3.toChecksumAddress(token_address))

        # Load ERC20 token contract
        self.erc20_contract = self.w3.eth.contract(address=self.token, abi=self.erc20_abi)

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

        self.gasLimit = 400000

    def get_block_at_timestamp(self, unix_timestamp):
        sleep(0.5)
        block = requests.get("https://api.bscscan.com/api?module=block&action=getblocknobytime&timestamp="
                             +str(unix_timestamp)+"&closest=before&apikey=2F82NDY1TEIF1M3TSVCCSAWCCJ9GWUHRIZ")
        block = json.loads(block.content)
        block = block["result"]
        return int(block)

    def get_current_block(self):
        block = Web3.eth.block_number
        return block

    def get_estimated_gas(self):
        pass
        #w3_transactions.get_buffered_gas_estimate(web3=self.w3, transaction=)

    async def get_token_price_in_usdc(self):
        # Use 0.001 BNB to base USDC and Token amountsOut
        amount_in = Web3.toWei(1, 'ether')

        # Get decimals for Stablecoin and Token
        stable_decimals = self.get_stable_decimals()
        token_decimals = self.get_token_decimals()

        # Format to correct Wei unit based on decimals
        for i in self.wei_file:
            if i['DECIMALS'] == str(stable_decimals):
                stable_decimals = i['UNIT']
            if i['DECIMALS'] == str(token_decimals):
                token_decimals = i['UNIT']

        # Get current price of BNB in USD
        usdc_out = self.router_contract.functions.getAmountsOut(
            amount_in, [self.native_address, self.stable_address]).call()[1]
        usdc_out = Web3.fromWei(usdc_out, stable_decimals)

        # Get current price of Token in BNB
        amountsOut = self.router_contract.functions.getAmountsOut(
            amount_in, [self.native_address, self.token]).call()[1]
        amountsOut = Web3.fromWei(amountsOut, token_decimals)

        # Calculate Token price in USDC
        real_price = float(usdc_out) / float(amountsOut)

        # Convert to readable format
        if real_price > 1:
            formatted_price = ("{:0.4f}".format(real_price))
        elif real_price <1 and real_price != 0:
            formatted_price = ("{:0.18f}".format(real_price))
        else:
            formatted_price = ("{:0.1f}".format(real_price))

        return formatted_price

    def get_token_balance(self, unix_timestamp, address):
        # Load balance check contract
        balance_check_contract = self.w3.eth.contract(
            address=self.token, abi=self.balance_check_abi)

        # Get decimals for Stablecoin and Token
        token_decimals = self.get_token_decimals()

        # Format to correct Wei unit based on decimals
        for i in self.wei_file:
            if i['DECIMALS'] == str(token_decimals):
                token_decimals = i['UNIT']

        # Get amount of Tokens held in wallet and convert to readable format
        # balance = balance_check_contract.functions.balanceOf(self.account.address).call({'from': self.token})
        block = self.get_block_at_timestamp(unix_timestamp)
        print(block)
        balance = balance_check_contract.functions.balanceOf(Web3.toChecksumAddress(address)).call({'from': self.token}, block)
        token_amount = Web3.fromWei(balance, token_decimals)

        # Format owned Tokens so low amounts have 18 decimals and high amounts have 2 decimals
        if token_amount >1:
            tokens_owned = ("{:0.2f}".format(token_amount))
        elif token_amount <1 and token_amount != 0:
            tokens_owned = ("{:0.18f}".format(token_amount))
        else:
            tokens_owned = ("{:0.1f}".format(token_amount))

        return tokens_owned

    def get_native_balance(self):
        # Get amount of Native held in wallet
        balance = self.w3.eth.getBalance(self.account.address)

        token_amount = Web3.fromWei(balance, 'ether')

        if token_amount >1:
            tokens_owned = ("{:0.2f}".format(token_amount))
        elif token_amount <1 and token_amount != 0:
            tokens_owned = ("{:0.18f}".format(token_amount))
        else:
            tokens_owned = ("{:0.1f}".format(token_amount))

        return tokens_owned

    def get_native_price_in_usdc(self):
        # Get decimals for Stablecoin and Token
        stable_decimals = self.get_stable_decimals()
        print(stable_decimals)

        # Format to correct Wei unit based on decimals
        for i in self.wei_file:
            if i['DECIMALS'] == str(stable_decimals):
                stable_decimals = i['UNIT']

        amount_in = Web3.toWei(1, "ether")
        print(amount_in)

        # Get current price of Native in Stablecoin
        usdc_out = self.router_contract.functions.getAmountsOut(
            amount_in, [self.native_address, self.stable_address]).call()[1]
        print(usdc_out)
        usdc_out = Web3.fromWei(usdc_out, stable_decimals)

        # Calculate Token price in Stablecoin
        real_price = float(usdc_out)

        # Convert to readable format
        formatted_price = ("{:0.18f}".format(real_price))

        return formatted_price

    def get_token_name(self):
        token_name = self.erc20_contract.functions.symbol().call()
        return token_name

    def get_token_decimals(self):
        token_decimals = self.erc20_contract.functions.decimals().call()
        return token_decimals

    def get_stable_decimals(self):
        stable_decimals = self.stable_contract.functions.decimals().call()
        return stable_decimals