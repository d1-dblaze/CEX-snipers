import os
import ccxt
import json
import logging
import logging.handlers
import time
import decimal
import requests
from dotenv import load_dotenv
               
load_dotenv()

def getmylogger(name):
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

logger = getmylogger(__name__)
 
def libraryConnect():

    API_KEY = os.getenv('MEXC_API_KEY')
    API_SECRET = os.getenv('MEXC_API_SECRET_KEY')

    handle = ccxt.mexc3({
        'apiKey': API_KEY,
        'secret': API_SECRET,
        'enableRateLimit':True 
    })

    handle.load_markets()

    return handle

def getAccountBalance(client, currency):
    """
    Retrieve the available balance of a specific currency in the account.

    Args:
        client: The client object for interacting with the exchange.
        currency (str): The currency symbol to retrieve the balance for.

    Returns:
        float or str: The available balance of the currency as a float if it exists, or an error message as a string.
    """
    logger.info("Retrieving account details")
    
    # Fetch the account information
    acctInfo = client.spotPrivateGetAccount()
    logger.info("acctInfo: {}".format(acctInfo))
    
    # Use a list comprehension to extract the available balance for the specified currency
    available_balances = [asset['free'] for asset in acctInfo["balances"] if asset['asset'] == currency]
    
    if available_balances:
        # Log the available balance for testing purposes
        logger.info('Available balance: {}'.format(available_balances[0]))
        
        # Return the available balance as a float
        return float(available_balances[0])
    
    # If the currency is not found in the account balances, return an error message
    return "Currency balance not found"

def getSymbolDetail(client, symbol):
    """
    Retrieve the details of a specific symbol.

    Args:
        client: The client object for interacting with the exchange.
        symbol (str): The symbol to retrieve the details for.

    Returns:
        dict or None: The details of the symbol as a dictionary if it exists, or None if not found.
    """
    symbolList = client.spotPublicGetExchangeInfo()['symbols']
    
    # Use a list comprehension to filter the symbol list based on the specified symbol
    symbol_details = [n for n in symbolList if n['symbol'] == symbol]
    
    if symbol_details:
        return symbol_details[0]
    
    # If the symbol is not found, return None
    return None

def extract_unique_trade_signals(list_A, list_B):
    trade_signals_B = {trade['trade_signal'] for trade in list_B}
    unique_trades = [trade for trade in list_A if trade['trade_signal'] not in trade_signals_B]
    return unique_trades

def dump(potential_trades:list):
    """
    Dump the potential trades to a JSON file, while removing duplicates.

    Args:
        potential_trades (list): List of potential trades.

    Returns:
        None
    """
    file_path = "/root/snipeBot/mexc_potential_trades.json"
    with open(file_path,"r") as trade_file:
        data = json.load(trade_file)
        unique_trade_signals = extract_unique_trade_signals(potential_trades, data)
        data.extend(unique_trade_signals)
    
    with open(file_path,"w") as trade_file:
        json.dump(data,trade_file)

def filterPairs(client,pairs):
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
        symbol_detail = getSymbolDetail(client, pair)
        logger.debug(symbol_detail)

        if symbol_detail is None or symbol_detail['symbol'] is None:
            continue

        base_asset = symbol_detail['baseAsset']
        
        # Check if the base asset has already been encountered
        if base_asset not in symbols:
            symbols.append(base_asset)
            filtered_pairs.append(pair)

    logger.debug("Pairs before filtering for ETF assets: {}".format(filtered_pairs))

    # Filter out ETF pairs
    filtered_pairs = filterETFPairs(filtered_pairs)

    logger.debug("Pairs after filtering out ETF assets: {}".format(filtered_pairs))

    return filtered_pairs

def filterETFPairs(pairs):
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

    # Return the filtered list of pairs without ETF pairs
    return filtered_pairs

def allocateFunds(pairs, account_balance):
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
    logger.info("Allocated funds: {}".format(funds))

    # Return the dictionary with allocated funds for each pair
    return funds

#need to fix
#it always return an error for newer symbols.
"""def exchangeSupportSymbol(client, symbol):
    #not all symbols received are active to be traded via the api
    #This function checks for the active flag thanks to ccxt
    market = client.market(symbol)
    if market["active"]: 
        return True 
    else:
        return False"""

def filterSymbolList(symbols,supportedSymbols):
    # Filter only markets with 
    # - spot == True
    # - status == ENABLED
    # - and among the whitelisted symbols available for trade via API on mexc
    
    filtered_symbolList = [
        symbol
        for symbol in symbols
        if symbol['spot'] and symbol['info']['status'] == 'ENABLED' and symbol['info']['symbol'] in supportedSymbols
    ]
    
    #spot pairs e.g BTCUSDT
    spot_pairs = [
        symbol['info']['symbol']
        for symbol in filtered_symbolList
    ]

    # Extract unique base asset symbols
    #e.g USDT, BTC
    symbols = list(set(
            symbol['info']['baseAsset'] 
            for symbol in filtered_symbolList 
        ))
    
    #print(spot_pairs)
    
    return spot_pairs,symbols

def countPotentialTrades ():
    """
    Returns the number of trades in the trade file.
    """
    try:
        with open("/root/snipeBot/mexc_potential_trades.json", 'r') as trade_list:
            data = json.load(trade_list)
        return len(data)
    except FileNotFoundError:
        logger.error("Trade list file not found.")
        return 0
    except json.JSONDecodeError:
        logger.error("Error decoding JSON data from the trade list file.")
        return 0

def queryCEXMEXC():
    """
    Query MEXC, fetch the market list, and filter only spot markets.

    Returns:
        dict: A dictionary containing the list of tokens and trading pairs.
    """
        # Initialize an empty dictionary to store the safe symbols and trading pairs
    safe_list = {'Symbols': [], 'Pairs': []}

    # Set initial values
    status = False

    # Keep querying until successful
    while not status:
        try:
            # Fetch the spot market list from Mexc
            symbolList = client.fetch_spot_markets()
            url = "https://api.mexc.com/api/v3/defaultSymbols"
            response = requests.request("GET", url)
            supported_symbols = response.json()["data"]
            status = True  # Set status to True to exit the loop if successful
            time.sleep(1)
        except Exception as err:
            logger.info("Failed to get Market List")
            logger.info("ERROR - {}".format(err))
            time.sleep(2)
            continue

    spot_pairs, symbols = filterSymbolList(symbolList,supported_symbols)

    # Update the safe_list dictionary with the symbols and pairs
    safe_list['Symbols'] = symbols
    safe_list['Pairs'] = spot_pairs

    #logger.info("Market successfully retrieved from MEXC!")
    return safe_list

def main():
    global client
    old_symbol_dict = dict()
    pairs_to_trade = []
    potential_trades = []
    #list of supported assets
    supportedAsset = ['USDT'] #['USDT','USDC','BUSD','DAI']
    useAllAssets = False
    maxTradePerAccount = 2
    client = libraryConnect()
    n = 0
    
    while True:
        if n < 1 :
            try:
                old_symbol_dict = queryCEXMEXC()
                n = n+1
                continue
            except Exception:
                time.sleep(2)
                continue
        else:
            new_symbol_dict = queryCEXMEXC()
            
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
            if countPotentialTrades() >= maxTradePerAccount:
                logger.info("Reached maximum trade count. Ignoring new pairs.")
                for trade in pairs_to_trade:
                    old_symbol_dict['Pairs'].append(trade)
                pairs_to_trade.clear()
                continue 

            if len(pairs_to_trade) > countPotentialTrades():
                pairs_to_trade = pairs_to_trade[:maxTradePerAccount]
                
            logger.info('{} pair(s) available to trade!'.format(len(pairs_to_trade)))

            # Filter the pairs based on specific criteria (if needed)
            filtered_pairs = filterPairs(client, pairs_to_trade)

            # Get the account balance for a specific currency (e.g., "USDT")
            account_balance = getAccountBalance(client, "USDT")

            try:
                # Allocate funds equally among the filtered pairs
                funds = allocateFunds(filtered_pairs, account_balance)
            except Exception:
                logger.info("Can't allocate funds to tradeable pairs")

            for trade_signal in filtered_pairs:
                symbol_detail = getSymbolDetail(client, trade_signal)
                min_size = symbol_detail["quoteAmountPrecisionMarket"]
                max_size = symbol_detail["maxQuoteAmountMarket"]
                base_asset = symbol_detail['baseAsset']
                quote_asset = symbol_detail['quoteAsset']
                base_increment = symbol_detail["baseSizePrecision"]

                fund_allocated = funds[trade_signal]
                
                #check if the useAllAssets is false, then
                #check if the quotecurrency is a supported asset.
                #If it is not, remove the asset from the list of tradeable assets.
                if useAllAssets == False and quote_asset not in supportedAsset:
                    filtered_pairs.remove(trade_signal)
                    old_symbol_dict['Pairs'].append(trade_signal)
                    logger.info("{} has been removed as the base asset is not supported".format(trade_signal))
                    continue

                fund_allocated = funds[trade_signal]
                potential_trades.append({
                    "trade_signal": trade_signal,
                    "baseCurr":     base_asset,
                    "quoteCurr":    quote_asset,
                    "minSize":      min_size,
                    "maxSize":      max_size,
                    "base_increment":base_increment,
                    "fund_allocated": fund_allocated
                })
                
                pairs_to_trade.remove(trade_signal)
                
            logger.info("Potential trade(s) to dump into file : {}".format(potential_trades))
            dump(potential_trades)

        else:
            logger.debug("No new pair(s) found")
    
        time.sleep(1)

def get_current_price(client, trade_signal):
    response = client.fetchTicker(trade_signal)
    last_price = float(response['info']['lastPrice'])
    return last_price

def test():
    client = libraryConnect()
    symbol_list = [{'id': 'RIBBITUSDT', 'symbol': 'RIBBIT/USDT', 'base': 'RIBBIT', 'quote': 'USDT', 'settle': None, 'baseId': 'RIBBIT', 'quoteId': 'USDT', 'settleId': None, 'type': 'spot', 'spot': True, 'margin': False, 'swap': False, 'future': False, 'option': False, 'active': True, 'contract': False, 'linear': None, 'inverse': None, 'taker': 0.0, 'maker': 0.0, 'contractSize': None, 'expiry': None, 'expiryDatetime': None, 'strike': None, 'optionType': None, 'precision': {'amount': 1.0, 'price': 1e-12}, 'limits': {'leverage': {'min': None, 'max': None}, 'amount': {'min': 0.0, 'max': None}, 'price': {'min': None, 'max': None}, 'cost': {'min': 5.0, 'max': 2000000.0}}, 'info': {'symbol': 'RIBBITUSDT', 'status': 'ENABLED', 'baseAsset': 'RIBBIT', 'baseAssetPrecision': '0', 'quoteAsset': 'USDT', 'quotePrecision': '12', 'quoteAssetPrecision': '12', 'baseCommissionPrecision': '0', 'quoteCommissionPrecision': '12', 'orderTypes': ['LIMIT', 'MARKET', 'LIMIT_MAKER'], 'isSpotTradingAllowed': True, 'isMarginTradingAllowed': False, 'quoteAmountPrecision': '5.000000000000000000', 'baseSizePrecision': '0', 'permissions': ['SPOT'], 'filters': [], 'maxQuoteAmount': '2000000.000000000000000000', 'makerCommission': '0', 'takerCommission': '0', 'quoteAmountPrecisionMarket': '5.000000000000000000', 'maxQuoteAmountMarket': '100000.000000000000000000'}}, {'id': 'ANKRETH', 'symbol': 'ANKR/ETH', 'base': 'ANKR', 'quote': 'ETH', 'settle': None, 'baseId': 'ANKR', 'quoteId': 'ETH', 'settleId': None, 'type': 'spot', 'spot': True, 'margin': False, 'swap': False, 'future': False, 'option': False, 'active': True, 'contract': False, 'linear': None, 'inverse': None, 'taker': 0.0, 'maker': 0.0, 'contractSize': None, 'expiry': None, 'expiryDatetime': None, 'strike': None, 'optionType': None, 'precision': {'amount': 0.0001, 'price': 1e-09}, 'limits': {'leverage': {'min': None, 'max': None}, 'amount': {'min': 0.01, 'max': None}, 'price': {'min': None, 'max': None}, 'cost': {'min': 0.001, 'max': 1000.0}}, 'info': {'symbol': 'ANKRETH', 'status': 'ENABLED', 'baseAsset': 'ANKR', 'baseAssetPrecision': '4', 'quoteAsset': 'ETH', 'quotePrecision': '9', 'quoteAssetPrecision': '9', 'baseCommissionPrecision': '4', 'quoteCommissionPrecision': '9', 'orderTypes': ['LIMIT', 'LIMIT_MAKER'], 'isSpotTradingAllowed': True, 'isMarginTradingAllowed': False, 'quoteAmountPrecision': '0.001000000000000000', 'baseSizePrecision': '0.01', 'permissions': ['SPOT'], 'filters': [], 'maxQuoteAmount': '1000.000000000000000000', 'makerCommission': '0', 'takerCommission': '0', 'quoteAmountPrecisionMarket': '0.001000000000000000', 'maxQuoteAmountMarket': '50.000000000000000000'}}, {'id': 'ISKUSDT', 'symbol': 'ISK/USDT', 'base': 'ISK', 'quote': 'USDT', 'settle': None, 'baseId': 'ISK', 'quoteId': 'USDT', 'settleId': None, 'type': 'spot', 'spot': True, 'margin': False, 'swap': False, 'future': False, 'option': False, 'active': True, 'contract': False, 'linear': None, 'inverse': None, 'taker': 0.0, 'maker': 0.0, 'contractSize': None, 'expiry': None, 'expiryDatetime': None, 'strike': None, 'optionType': None, 'precision': {'amount': 0.01, 'price': 0.0001}, 'limits': {'leverage': {'min': None, 'max': None}, 'amount': {'min': 0.001, 'max': None}, 'price': {'min': None, 'max': None}, 'cost': {'min': 5.0, 'max': 2000000.0}}, 'info': {'symbol': 'ISKUSDT', 'status': 'ENABLED', 'baseAsset': 'ISK', 'baseAssetPrecision': '2', 'quoteAsset': 'USDT', 'quotePrecision': '4', 'quoteAssetPrecision': '4', 'baseCommissionPrecision': '2', 'quoteCommissionPrecision': '4', 'orderTypes': ['LIMIT', 'MARKET', 'LIMIT_MAKER'], 'isSpotTradingAllowed': True, 'isMarginTradingAllowed': False, 'quoteAmountPrecision': '5.000000000000000000', 'baseSizePrecision': '0.001', 'permissions': ['SPOT'], 'filters': [], 'maxQuoteAmount': '2000000.000000000000000000', 'makerCommission': '0', 'takerCommission': '0', 'quoteAmountPrecisionMarket': '5.000000000000000000', 'maxQuoteAmountMarket': '100000.000000000000000000'}}, {'id': 'VRSWUSDT', 'symbol': 'VRSW/USDT', 'base': 'VRSW', 'quote': 'USDT', 'settle': None, 'baseId': 'VRSW', 'quoteId': 'USDT', 'settleId': None, 'type': 'spot', 'spot': True, 'margin': False, 'swap': False, 'future': False, 'option': False, 'active': True, 'contract': False, 'linear': None, 'inverse': None, 'taker': 0.0, 'maker': 0.0, 'contractSize': None, 'expiry': None, 'expiryDatetime': None, 'strike': None, 'optionType': None, 'precision': {'amount': 0.01, 'price': 1e-06}, 'limits': {'leverage': {'min': None, 'max': None}, 'amount': {'min': 0.0, 'max': None}, 'price': {'min': None, 'max': None}, 'cost': {'min': 5.0, 'max': 2000000.0}}, 'info': {'symbol': 'VRSWUSDT', 'status': 'ENABLED', 'baseAsset': 'VRSW', 'baseAssetPrecision': '2', 'quoteAsset': 'USDT', 'quotePrecision': '6', 'quoteAssetPrecision': '6', 'baseCommissionPrecision': '2', 'quoteCommissionPrecision': '6', 'orderTypes': ['LIMIT', 'MARKET', 'LIMIT_MAKER'], 'isSpotTradingAllowed': True, 'isMarginTradingAllowed': False, 'quoteAmountPrecision': '5.000000000000000000', 'baseSizePrecision': '0', 'permissions': ['SPOT'], 'filters': [], 'maxQuoteAmount': '2000000.000000000000000000', 'makerCommission': '0', 'takerCommission': '0', 'quoteAmountPrecisionMarket': '5.000000000000000000', 'maxQuoteAmountMarket': '100000.000000000000000000'}}, {'id': 'WINUSDT', 'symbol': 'WIN/USDT', 'base': 'WIN', 'quote': 'USDT', 'settle': None, 'baseId': 'WIN', 'quoteId': 'USDT', 'settleId': None, 'type': 'spot', 'spot': True, 'margin': False, 'swap': False, 'future': False, 'option': False, 'active': True, 'contract': False, 'linear': None, 'inverse': None, 'taker': 0.0, 'maker': 0.0, 'contractSize': None, 'expiry': None, 'expiryDatetime': None, 'strike': None, 'optionType': None, 'precision': {'amount': 0.01, 'price': 1e-08}, 'limits': {'leverage': {'min': None, 'max': None}, 'amount': {'min': 0.001, 'max': None}, 'price': {'min': None, 'max': None}, 'cost': {'min': 5.0, 'max': 2000000.0}}, 'info': {'symbol': 'WINUSDT', 'status': 'ENABLED', 'baseAsset': 'WIN', 'baseAssetPrecision': '2', 'quoteAsset': 'USDT', 'quotePrecision': '8', 'quoteAssetPrecision': '8', 'baseCommissionPrecision': '2', 'quoteCommissionPrecision': '8', 'orderTypes': ['LIMIT', 'LIMIT_MAKER'], 'isSpotTradingAllowed': True, 'isMarginTradingAllowed': False, 'quoteAmountPrecision': '5.000000000000000000', 'baseSizePrecision': '0.001', 'permissions': ['SPOT'], 'filters': [], 'maxQuoteAmount': '2000000.000000000000000000', 'makerCommission': '0', 'takerCommission': '0', 'quoteAmountPrecisionMarket': '5.000000000000000000', 'maxQuoteAmountMarket': '100000.000000000000000000'}}, {'id': 'BGBUSDT', 'symbol': 'BGB/USDT', 'base': 'BGB', 'quote': 'USDT', 'settle': None, 'baseId': 'BGB', 'quoteId': 'USDT', 'settleId': None, 'type': 'spot', 'spot': True, 'margin': False, 'swap': False, 'future': False, 'option': False, 'active': True, 'contract': False, 'linear': None, 'inverse': None, 'taker': 0.0, 'maker': 0.0, 'contractSize': None, 'expiry': None, 'expiryDatetime': None, 'strike': None, 'optionType': None, 'precision': {'amount': 0.01, 'price': 1e-05}, 'limits': {'leverage': {'min': None, 'max': None}, 'amount': {'min': 0.0, 'max': None}, 'price': {'min': None, 'max': None}, 'cost': {'min': 5.0, 'max': 2000000.0}}, 'info': {'symbol': 'BGBUSDT', 'status': 'ENABLED', 'baseAsset': 'BGB', 'baseAssetPrecision': '2', 'quoteAsset': 'USDT', 'quotePrecision': '5', 'quoteAssetPrecision': '5', 'baseCommissionPrecision': '2', 'quoteCommissionPrecision': '5', 'orderTypes': ['LIMIT', 'MARKET', 'LIMIT_MAKER'], 'isSpotTradingAllowed': True, 'isMarginTradingAllowed': False, 'quoteAmountPrecision': '5.000000000000000000', 'baseSizePrecision': '0', 'permissions': ['SPOT'], 'filters': [], 'maxQuoteAmount': '2000000.000000000000000000', 'makerCommission': '0', 'takerCommission': '0', 'quoteAmountPrecisionMarket': '5.000000000000000000', 'maxQuoteAmountMarket': '100000.000000000000000000'}}, {'id': 'SERPUSDT', 'symbol': 'SERP/USDT', 'base': 'SERP', 'quote': 'USDT', 'settle': None, 'baseId': 'SERP', 'quoteId': 'USDT', 'settleId': None, 'type': 'spot', 'spot': True, 'margin': False, 'swap': False, 'future': False, 'option': False, 'active': True, 'contract': False, 'linear': None, 'inverse': None, 'taker': 0.0, 'maker': 0.0, 'contractSize': None, 'expiry': None, 'expiryDatetime': None, 'strike': None, 'optionType': None, 'precision': {'amount': 0.01, 'price': 1e-07}, 'limits': {'leverage': {'min': None, 'max': None}, 'amount': {'min': 0.0, 'max': None}, 'price': {'min': None, 'max': None}, 'cost': {'min': 5.0, 'max': 2000000.0}}, 'info': {'symbol': 'SERPUSDT', 'status': 'ENABLED', 'baseAsset': 'SERP', 'baseAssetPrecision': '2', 'quoteAsset': 'USDT', 'quotePrecision': '7', 'quoteAssetPrecision': '7', 'baseCommissionPrecision': '2', 'quoteCommissionPrecision': '7', 'orderTypes': ['LIMIT', 'MARKET', 'LIMIT_MAKER'], 'isSpotTradingAllowed': True, 'isMarginTradingAllowed': False, 'quoteAmountPrecision': '5.000000000000000000', 'baseSizePrecision': '0', 'permissions': ['SPOT'], 'filters': [], 'maxQuoteAmount': '2000000.000000000000000000', 'makerCommission': '0', 'takerCommission': '0', 'quoteAmountPrecisionMarket': '5.000000000000000000', 'maxQuoteAmountMarket': '100000.000000000000000000'}}, {'id': 'BCUSDT', 'symbol': 'BC/USDT', 'base': 'BC', 'quote': 'USDT', 'settle': None, 'baseId': 'BC', 'quoteId': 'USDT', 'settleId': None, 'type': 'spot', 'spot': True, 'margin': False, 'swap': False, 'future': False, 'option': False, 'active': True, 'contract': False, 'linear': None, 'inverse': None, 'taker': 0.0, 'maker': 0.0, 'contractSize': None, 'expiry': None, 'expiryDatetime': None, 'strike': None, 'optionType': None, 'precision': {'amount': 0.01, 'price': 1e-06}, 'limits': {'leverage': {'min': None, 'max': None}, 'amount': {'min': 0.0, 'max': None}, 'price': {'min': None, 'max': None}, 'cost': {'min': 5.0, 'max': 2000000.0}}, 'info': {'symbol': 'BCUSDT', 'status': 'ENABLED', 'baseAsset': 'BC', 'baseAssetPrecision': '2', 'quoteAsset': 'USDT', 'quotePrecision': '6', 'quoteAssetPrecision': '6', 'baseCommissionPrecision': '2', 'quoteCommissionPrecision': '6', 'orderTypes': ['LIMIT', 'LIMIT_MAKER'], 'isSpotTradingAllowed': True, 'isMarginTradingAllowed': False, 'quoteAmountPrecision': '5.000000000000000000', 'baseSizePrecision': '0', 'permissions': ['SPOT'], 'filters': [], 'maxQuoteAmount': '2000000.000000000000000000', 'makerCommission': '0', 'takerCommission': '0', 'quoteAmountPrecisionMarket': '5.000000000000000000', 'maxQuoteAmountMarket': '100000.000000000000000000'}}, {'id': 'MXENUSDT', 'symbol': 'MXEN/USDT', 'base': 'MXEN', 'quote': 'USDT', 'settle': None, 'baseId': 'MXEN', 'quoteId': 'USDT', 'settleId': None, 'type': 'spot', 'spot': True, 'margin': False, 'swap': False, 'future': False, 'option': False, 'active': True, 'contract': False, 'linear': None, 'inverse': None, 'taker': 0.0, 'maker': 0.0, 'contractSize': None, 'expiry': None, 'expiryDatetime': None, 'strike': None, 'optionType': None, 'precision': {'amount': 0.01, 'price': 1e-12}, 'limits': {'leverage': {'min': None, 'max': None}, 'amount': {'min': 0.001, 'max': None}, 'price': {'min': None, 'max': None}, 'cost': {'min': 5.0, 'max': 2000000.0}}, 'info': {'symbol': 'MXENUSDT', 'status': 'ENABLED', 'baseAsset': 'MXEN', 'baseAssetPrecision': '2', 'quoteAsset': 'USDT', 'quotePrecision': '12', 'quoteAssetPrecision': '12', 'baseCommissionPrecision': '2', 'quoteCommissionPrecision': '12', 'orderTypes': ['LIMIT', 'LIMIT_MAKER'], 'isSpotTradingAllowed': True, 'isMarginTradingAllowed': False, 'quoteAmountPrecision': '5.000000000000000000', 'baseSizePrecision': '0.001', 'permissions': ['SPOT'], 'filters': [], 'maxQuoteAmount': '2000000.000000000000000000', 'makerCommission': '0', 'takerCommission': '0', 'quoteAmountPrecisionMarket': '5.000000000000000000', 'maxQuoteAmountMarket': '100000.000000000000000000'}}]
    
    sym = filterSymbolList(client,symbol_list)
    print(sym)
        
if __name__ == "__main__":
    #main()
    s = time.time()
    test()
    print(time.time() - s)

