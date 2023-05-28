import os
import ccxt
import requests
import json
import logging
import logging.handlers
import time
import decimal
from uuid import uuid1
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
    file_handler = logging.handlers.TimedRotatingFileHandler("../logs/mexc_scanner.log", when="midnight")
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
    Allocate equal funds to each tradable pair based on the total account balance.

    Args:
        pairs (list): A list of tradeable pairs.
        account_balance (float or str): The total account balance.

    Returns:
        dict: A dictionary with the allocated funds for each pair.
    """
    allocated_funds = {}

    # Convert the account balance to a Decimal for precise calculations
    total_balance = decimal.Decimal(str(account_balance))

    # Check if there are any pairs to allocate funds to
    if len(pairs) == 0:
        return allocated_funds

    # Calculate the fund allocation for each pair
    fund_per_pair = total_balance / len(pairs)

    # Allocate funds equally to each pair
    for pair in pairs:
        allocated_funds[pair] = float(fund_per_pair)

    logger.info("Allocated funds: {}".format(allocated_funds))
    return allocated_funds

def queryCEXMEXC(client):
    """
    Query MEXC, fetch the market list, and filter only spot markets.

    Args:
        client: The client object for interacting with the MEXC exchange.

    Returns:
        dict: A dictionary containing the list of tokens and trading pairs.
    """
    while True:
        try:
            symbol_list = client.fetch_markets()
            # Filter only spot markets with status ENABLED
            spot_symbols = [
                symbol['info']['symbol']
                for symbol in symbol_list
                if symbol['spot'] and symbol['info']['status'] == 'ENABLED'
            ]
            # Extract unique base asset symbols
            symbols = list(set(
                    symbol['info']['baseAsset'] 
                    for symbol in symbol_list 
                    if symbol['spot'] and symbol['info']['status'] == 'ENABLED'
                ))
            break
        except Exception as err:
            logger.info("Failed to get market list")
            logger.info("ERROR - {}".format(err))
            time.sleep(2)

    safe_list = {
        'Symbols': symbols,
        'Pairs': spot_symbols
    }

    logger.info("Market successfully retrieved from MEXC!")
    return safe_list

def main():
    global client
    old_symbol_dict = dict()
    potential_trades = []
    #list of supported assets
    supportedAsset = ['USDT'] #['USDT','USDC','BUSD','DAI']
    useAllAssets = False
    client = libraryConnect()
    n = 0
    while True:
        if n < 1 :
            try:
                old_symbol_dict = queryCEXMEXC()
                n = n+1
            except Exception:
                time.sleep(2)
                continue
        else:
            new_symbol_dict = queryCEXMEXC()
            
            # Check for new symbols and pairs
        new_symbols = set(new_symbol_dict['Symbols']) - set(old_symbol_dict['Symbols'])
        new_pairs = set(new_symbol_dict['Pairs']) - set(old_symbol_dict['Pairs'])

        for symbol in new_symbols:
            old_symbol_dict['Symbols'].append(symbol)

        for pair in new_pairs:
            old_symbol_dict['Pairs'].append(pair)
            logger.info("New Pair found. Adding to list of tradeable pairs!")

        if new_pairs:
            logger.info('{} pair(s) available to trade!'.format(len(new_pairs)))

            # Filter the pairs based on specific criteria (if needed)
            filtered_pairs = filterPairs(client, list(new_pairs))

            # Get the account balance for a specific currency (e.g., "USDT")
            account_balance = getAccountBalance(client, "USDT")

            try:
                # Allocate funds equally among the filtered pairs
                funds = allocateFunds(filtered_pairs, account_balance)
            except Exception:
                logger.info("Can't allocate funds to tradeable pairs")

            for trade_signal in filtered_pairs:
                symbol_detail = getSymbolDetail(client, trade_signal)
                base_asset = symbol_detail['baseAsset']
                quote_asset = symbol_detail['quoteAsset']

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
                    "fund_allocated": fund_allocated
                })
                logger.info("Potential trades to dump into file : {}".format(potential_trades))
                dump(potential_trades)

        else:
            logger.debug("No new pair(s) found")

        time.sleep(1)

if __name__ == "__main__":
    main()