import os
import ccxt
import json
import logging
import logging.handlers
import time
import decimal
import requests
from dotenv import load_dotenv

class MEXCScanner:
    def __init__(self):
        load_dotenv()
        self.logger = self._get_logger(__name__)
        self.client = self._library_connect()

    def _get_logger(self, name):
        """
        Create and configure a logger with file and console handlers.

        Args:
            name (str): The name of the logger.

        Returns:
            logging.Logger: The configured logger.

        """
        formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [MODULE::%(module)s] [MESSAGE]:: %(message)s')
        
        # Configure the file handler for logging to a file with rotating file names
        file_handler = logging.handlers.TimedRotatingFileHandler("../logs/mexc/mexc_scanner.log", when="midnight")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        
        # Configure the console handler for logging to the console
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(formatter)
        
        # Create a logger and add the file handler and console handler
        logger = logging.getLogger(name)
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        logger.setLevel(logging.INFO)
        
        return logger

    def _library_connect(self):
        API_KEY = os.getenv('MEXC_API_KEY')
        API_SECRET = os.getenv('MEXC_API_SECRET_KEY')
        handle = ccxt.mexc3({
            'apiKey': API_KEY,
            'secret': API_SECRET,
            'enableRateLimit': True
        })
        handle.load_markets()
        
        self.logger.info("Client library successfully connected")
        return handle

    def get_account_balance(self, currency):
        """
        Retrieve the available balance of a specific currency in the account.

        Args:
            client: The client object for interacting with the exchange.
            currency (str): The currency symbol to retrieve the balance for.

        Returns:
            float or str: The available balance of the currency as a float if it exists, or an error message as a string.
        """
        self.logger.info("Retrieving account details")
        # Fetch the account information
        acct_info = self.client.spotPrivateGetAccount() 
        self.logger.info("acctInfo: {}".format(acct_info))
        
        # Use a list comprehension to extract the available balance for the specified currency
        available_balances = [asset['free'] for asset in acct_info["balances"] if asset['asset'] == currency]
        if available_balances:
            # Log the available balance for testing purposes
            self.logger.info('Available balance: {}'.format(available_balances[0]))
            # Return the available balance as a float
            return float(available_balances[0])
        
        # If the currency is not found in the account balances, return an error message
        return "Currency balance not found"

    def get_symbol_detail(self, symbol):
        """
        Retrieve the details of a specific symbol.

        Args:
            client: The client object for interacting with the exchange.
            symbol (str): The symbol to retrieve the details for.

        Returns:
            dict or None: The details of the symbol as a dictionary if it exists, or None if not found.
        """
        symbol_list = self.client.spotPublicGetExchangeInfo()['symbols'] 
        
        # Use a list comprehension to filter the symbol list based on the specified symbol
        symbol_details = [n for n in symbol_list if n['symbol'] == symbol]
        if symbol_details:
            return symbol_details[0]
        
        # If the symbol is not found, return None
        return None

    def extract_unique_trade_signals(self, list_A, list_B):
        trade_signals_B = {trade['trade_signal'] for trade in list_B}
        unique_trades = [trade for trade in list_A if trade['trade_signal'] not in trade_signals_B]
        return unique_trades

    def dump(self, potential_trades):
        """
        Dump the potential trades to a JSON file, while removing duplicates.

        Args:
            potential_trades (list): List of potential trades.

        Returns:
            None
        """
    
        file_path = "/root/snipeBot/mexc_potential_trades.json"
        with open(file_path, "r") as trade_file:
            data = json.load(trade_file)
            unique_trade_signals = self.extract_unique_trade_signals(potential_trades, data)
            data.extend(unique_trade_signals)
        with open(file_path, "w") as trade_file:
            json.dump(data, trade_file)

    def filter_pairs(self, pairs):
        """
        Filter symbols with multiple pairs and choose only one pair from each symbol.
        Removes ETF pairs from the list.

        Args:
            client: The client object for interacting with the exchange.
            pairs (list): List of trading pairs.

        Returns:
            list: Filtered list of pairs, with one pair per symbol and without ETF pairs.
        """
        
        filtered_pairs = []
        symbols = []
        for pair in pairs:
            symbol_detail = self.get_symbol_detail(pair)
            self.logger.debug(symbol_detail)
            if symbol_detail is None or symbol_detail['symbol'] is None:
                continue
            base_asset = symbol_detail['baseAsset']
            
            # Check if the base asset has already been encountered
            if base_asset not in symbols:
                symbols.append(base_asset)
                filtered_pairs.append(pair)
                
        self.logger.debug("Pairs before filtering for ETF assets: {}".format(filtered_pairs))

        # Filter out ETF pairs
        filtered_pairs = self.filter_etf_pairs(filtered_pairs)
        
        return filtered_pairs

    def filter_etf_pairs(self, pairs):
        """
        Filter out ETF pairs from the given list of pairs.

        Args:
            pairs (list): List of trading pairs.

        Returns:
            list: Filtered list of pairs without ETF pairs.
        """
        # Create a new list to store the filtered pairs
        filtered_pairs = []
        
        # Iterate over each pair in the original list
        for pair in pairs:
            # Check if the pair contains "3L" or "3S"
            if "3L" not in pair and "3S" not in pair:
                # Add the pair to the filtered list if it's not an ETF pair
                filtered_pairs.append(pair)
        return filtered_pairs

    def allocate_funds(self, pairs, account_balance):
        """
        Allocate equal funds to each tradable pair based on maxTradePerAccount.

        Args:
            pairs (list): A list of tradeable pairs.
            account_balance (float or str): The total account balance.

        Returns:
            dict: A dictionary with the allocated funds for each pair.
        """
        # Set the rounding mode to round down
        decimal.getcontext().rounding = decimal.ROUND_DOWN
        # Initialize an empty dictionary to store the allocated funds
        funds = {}
        # Get the number of pairs
        number_of_pairs = len(pairs)
        # If there are no pairs, return the empty funds dictionary
        if number_of_pairs == 0:
            return funds
        # Calculate the fund allocation for each pair
        fund_per_pair = decimal.Decimal(account_balance) / decimal.Decimal(number_of_pairs)
        # Allocate funds to each pair
        for pair in pairs:
            # Round the allocated funds to 3 decimal places
            allocated_funds = round(float(fund_per_pair), 3)
            # Assign the allocated funds to the pair
            funds[pair] = allocated_funds
        
        # Log the allocated funds    
        self.logger.info("Allocated funds: {}".format(funds))
        
        # Return the dictionary with allocated funds for each pair
        return funds

    def filter_symbol_list(self, symbols, supported_symbols):
        # Filter only markets with 
        # - spot == True
        # - status == ENABLED
        # - and among the whitelisted symbols available for trade via API on mexc
        
        filtered_symbol_list = [
            symbol
            for symbol in symbols
            if symbol['spot'] and symbol['info']['status'] == 'ENABLED' and symbol['info']['symbol'] in supported_symbols
        ]
        #spot pairs e.g BTCUSDT
        spot_pairs = [symbol['info']['symbol'] for symbol in filtered_symbol_list]
        # Extract unique base asset symbols
        #e.g USDT, BTC
        symbols = list(set(symbol['info']['baseAsset'] for symbol in filtered_symbol_list))
        return spot_pairs, symbols

    def count_potential_trades(self):
        """
        Returns the number of trades in the trade file.
        """
        try:
            with open("/root/snipeBot/mexc_potential_trades.json", 'r') as trade_list:
                data = json.load(trade_list)
            return len(data)
        except FileNotFoundError:
            self.logger.error("Trade list file not found.")
            return 0
        except json.JSONDecodeError:
            self.logger.error("Error decoding JSON data from the trade list file.")
            return 0
        
    def query_cexmexc(self):
        """
        Query MEXC, fetch the market list, and filter only spot markets.

        Returns:
            dict: A dictionary containing the list of tokens and trading pairs.
        """
        # Initialize an empty dictionary to store the safe symbols and trading pairs
        safe_list = {'Symbols': [], 'Pairs': []}
        status = False
        # Keep querying until successful
        while not status:
            try:
                # Fetch the spot market list from Mexc
                symbol_list = self.client.fetch_spot_markets()
                url = "https://api.mexc.com/api/v3/defaultSymbols"
                response = requests.request("GET", url)
                supported_symbols= response.json()["data"]
                status = True   # = response.json()["data"]
                status = True   # Set status to True to exit the loop if successful
                time.sleep(1)
            except Exception as err:
                self.logger.info("Failed to get Market List")
                self.logger.info("ERROR - {}".format(err))
                time.sleep(2)
                continue
        spot_pairs, symbols = self.filter_symbol_list(symbol_list, supported_symbols)
        
        # Update the safe_list dictionary with the symbols and pairs
        safe_list['Symbols'] = symbols
        safe_list['Pairs'] = spot_pairs
        
        #logger.info("Market successfully retrieved from MEXC!")
        return safe_list

    def main(self):
        old_symbol_dict = dict()
        pairs_to_trade = []
        potential_trades = []
        #list of supported assets
        supported_asset = ['USDT']  # ['USDT','USDC','BUSD','DAI']
        use_all_assets = False
        max_trade_per_account = 2
        n = 0

        while True:
            if n < 1:
                try:
                    old_symbol_dict = self.query_cexmexc()
                    n = n + 1
                    continue
                except Exception:
                    time.sleep(2)
                    continue
            else:
                new_symbol_dict = self.query_cexmexc()

            # Check for new symbols and pairs
            new_symbols = set(new_symbol_dict['Symbols']) - set(old_symbol_dict['Symbols'])
            new_pairs = set(new_symbol_dict['Pairs']) - set(old_symbol_dict['Pairs'])

            #update the old_symbol_dict with the latest info and proceed with other computation
            for symbol in new_symbols:
                old_symbol_dict['Symbols'].append(symbol)

            for pair in new_pairs:
                old_symbol_dict['Pairs'].append(pair)
                pairs_to_trade = list(new_pairs)
                #logger.info("New Pair found. Adding to list of tradeable pairs!")

            if pairs_to_trade:
                #if the number of trades in the file is >= max allowed trade, ignore any new potential trades.
                if self.count_potential_trades() >= max_trade_per_account:
                    self.logger.info("Reached maximum trade count. Ignoring new pairs.")
                    for trade in pairs_to_trade:
                        old_symbol_dict['Pairs'].append(trade)
                    pairs_to_trade.clear()
                    continue

                if len(pairs_to_trade) > self.count_potential_trades():
                    pairs_to_trade = pairs_to_trade[:max_trade_per_account]

                self.logger.info('{} pair(s) available to trade!'.format(len(pairs_to_trade)))

                # Filter the pairs based on specific criteria (if needed)
                filtered_pairs = self.filter_pairs(pairs_to_trade)
                # Get the account balance for a specific currency (e.g., "USDT")
                account_balance = self.get_account_balance("USDT")

                try:
                    # Allocate funds equally among the filtered pairs
                    funds = self.allocate_funds(filtered_pairs, account_balance)
                except Exception:
                    self.logger.info("Can't allocate funds to tradeable pairs")

                for trade_signal in filtered_pairs:
                    symbol_detail = self.get_symbol_detail(trade_signal)
                    min_size = symbol_detail["quoteAmountPrecisionMarket"]
                    max_size = symbol_detail["maxQuoteAmountMarket"]
                    base_asset = symbol_detail['baseAsset']
                    quote_asset = symbol_detail['quoteAsset']
                    base_increment = symbol_detail["baseSizePrecision"]

                    fund_allocated = funds[trade_signal]

                    #check if the useAllAssets is false, then
                    #check if the quotecurrency is a supported asset.
                    #If it is not, remove the asset from the list of tradeable assets.
                    if not use_all_assets and quote_asset not in supported_asset:
                        filtered_pairs.remove(trade_signal)
                        old_symbol_dict['Pairs'].append(trade_signal)
                        self.logger.info(
                            "{} has been removed as the base asset is not supported".format(trade_signal)
                        )
                        continue

                    fund_allocated = funds[trade_signal]
                    potential_trades.append({
                        "trade_signal": trade_signal,
                        "baseCurr": base_asset,
                        "quoteCurr": quote_asset,
                        "minSize": min_size,
                        "maxSize": max_size,
                        "base_increment": base_increment,
                        "fund_allocated": fund_allocated
                    })

                    pairs_to_trade.remove(trade_signal)

                self.logger.info("Potential trade(s) to dump into file : {}".format(potential_trades))
                self.dump(potential_trades)
                potential_trades.clear()   #clear the potential_trades list and start again

            else:
                self.logger.debug("No new pair(s) found")

            time.sleep(1)

    def get_current_price(self,client, trade_signal):
        response = client.fetchTicker(trade_signal)
        last_price = float(response['info']['lastPrice'])
        return last_price

if __name__ == "__main__":
    bot = MEXCScanner()
    bot.main()
