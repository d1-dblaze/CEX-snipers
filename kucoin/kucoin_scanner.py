import os
import ccxt
import logging
import logging.handlers
import time
import decimal
import json
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
    file_handler = logging.handlers.TimedRotatingFileHandler("scanner.log", when="midnight")
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

    API_KEY = os.getenv('KUCOIN_API_KEY')
    API_SECRET = os.getenv('KUCOIN_API_SECRET_KEY')
    PASSPHRASE = os.getenv('KUCOIN_PASSPHRASE')
    handle = ccxt.kucoin({
        'apiKey': API_KEY,
        'secret': API_SECRET,
        'password': PASSPHRASE,
        'enableRateLimit':True 
    })

    handle.load_markets()

    return handle

def return_unique_id():
    return ''.join([each for each in str(uuid1()).split('-')])

def custom_market_buy_order (client,symbol,size):
    """
    Place a market buy order on Kucoin and handle errors with retries.

    Args:
        client: The CCXT client instance for Kucoin.
        symbol (str): The trading symbol for the order.
        size: The size or quantity to buy.

    Returns:
        dict or str: The order result if successful, or the encountered error.

    """
    # Retry counter and order status
    counter = 0
    status = False

    while not status:
        try:
            time.sleep(1)  # Sleep for one second between requests
            result = client.create_order(symbol, 'market', 'buy', size)
            status = True  # Set status to true once the order is executed without errors
            return result
        except ccxt.RequestTimeout as e:
            # Handle request timeout error
            logger.info("Encountered request timeout error. Retrying order placement (Attempt {})".format(counter))
            counter += 1
            time.sleep(1)  # Sleep for one second between retries
        except ccxt.ExchangeError as e:
            error_message = str(e)
            if 'Too many requests' in error_message:
                # Handle rate limit error (Too many requests)
                logger.info("Encountered rate limit error. Retrying order placement (Attempt {})".format(counter))
                counter += 1
                time.sleep(1)  # Sleep for one second between retries
            else:
                # Handle other exchange errors
                logger.info("Error encountered while placing an order: {}".format(error_message))
                return error_message
        except Exception as e:
            # Handle general exceptions
            error_message = str(e)
            logger.info("Error encountered while placing an order: {}".format(error_message))
            return error_message

def custom_market_sell_order(client, symbol, size):
    """
    Place a market sell order on Kucoin and handle errors with retries.

    Args:
        client: The CCXT client instance for Kucoin.
        symbol (str): The trading symbol for the order.
        size: The size or quantity to sell.

    Returns:
        dict or str: The order result if successful, or the encountered error.

    """
    # Retry counter and order status
    counter = 0
    status = False

    while not status:
        try:
            time.sleep(1)  # Sleep for one second between requests
            result = client.create_order(symbol, 'market', 'sell', size)
            status = True  # Set status to true once the order is executed without errors
            return result
        except ccxt.RequestTimeout as e:
            # Handle request timeout error
            logger.info("Encountered request timeout error. Retrying order placement (Attempt {})".format(counter))
            counter += 1
            time.sleep(1)  # Sleep for one second between retries
        except ccxt.ExchangeError as e:
            error_message = str(e)
            if 'Too many requests' in error_message:
                # Handle rate limit error (Too many requests)
                logger.info("Encountered rate limit error. Retrying order placement (Attempt {})".format(counter))
                counter += 1
                time.sleep(1)  # Sleep for one second between retries
            else:
                # Handle other exchange errors
                logger.info("Error encountered while placing an order: {}".format(error_message))
                return error_message
        except Exception as e:
            # Handle general exceptions
            error_message = str(e)
            logger.info("Error encountered while placing an order: {}".format(error_message))
            return error_message

def clean(account_balance, details, current_price, side, risk_percentage):
    """
    Clean and process data for order size calculation.

    Args:
        account_balance (float): The account balance to consider for risk calculation.
        details (dict): Details of the trading pair or instrument.
        current_price (float): The current price of the asset.
        side (str): The side of the trade, either "buy" or "sell".
        risk_percentage (float): The risk percentage to consider for order size calculation.

    Returns:
        float: The cleaned and calculated order size.

    """
    logger.info("Cleaning data")

    decimal.getcontext().rounding = decimal.ROUND_DOWN

    # Convert the risk percentage to float.
    risk = float(risk_percentage)

    # Extract the base increment value for order size calculation.
    base_increment = details['baseIncrement']

    # Determine the number of decimal places for rounding.
    decimal_places = len(base_increment.split(".")[-1])

    logger.info("The order size should be rounded to %d decimal places", decimal_places)

    # Calculate the order size based on the side of the trade.
    if side == "buy":
        size = decimal.Decimal(risk / 100 * account_balance) / decimal.Decimal(current_price)
    elif side == "sell":
        size = decimal.Decimal(risk / 100 * account_balance)

    # Round the order size to the specified decimal places.
    size_to_exchange = round(size, decimal_places)

    return float(size_to_exchange)

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

    # Retrieve account information for the specified currency
    account_info = client.privateGetAccounts({"currency": currency})['data']
    logger.info("Account information: {}".format(account_info))

    # Find the trade account with available balance
    trade_accounts = [info for info in account_info if info['type'] == 'trade']
    if trade_accounts:
        available_balance = float(trade_accounts[0]['available'])
        return available_balance

    # Return an error message if no trade account with available balance is found
    error_message = "No trade account with available balance for the specified currency"
    logger.info(error_message)
    return error_message

def getSymbolDetail(client, symbol):
    """
    Retrieve details of a specific symbol from the exchange.

    Args:
        client: The client object for interacting with the exchange.
        symbol (str): The symbol to retrieve details for.

    Returns:
        dict or None: Details of the symbol if found, None otherwise.
    """
    symbol_list = client.publicGetSymbols()['data']

    for symbol_info in symbol_list:
        if symbol_info['symbol'] == symbol:
            return symbol_info

    return None  # Symbol not found, return None

def writeToFile (filename):
    with open ("{}".format(filename), "a") as file:
        file.write(str(client.fetch_markets()))

def dump(potential_trades):
    """
    Dump the potential trades to a JSON file, while removing duplicates.

    Args:
        potential_trades (list): List of potential trades.

    Returns:
        None
    """
    file_path = "/root/snipeBot/kucoin_potential_trades.json"

    with open(file_path, "r") as trade_file:
        data = json.load(trade_file)

        # Create a new list to store the filtered potential trades
        filtered_trades = []

        for obj in potential_trades:
            trade_signal_exists = False

            for data_obj in data:
                # Check if the trade_signal already exists in the file
                if obj['trade_signal'] == data_obj['trade_signal']:
                    trade_signal_exists = True
                    logger.info("{} already exists in the file. Removing".format(data_obj['trade_signal']))
                    break  # No need to continue checking once a match is found

            if not trade_signal_exists:
                filtered_trades.append(obj)

    with open(file_path, "w") as trade_file:
        json.dump(filtered_trades, trade_file)

def buildPair(base,quote):
    symbol = base.upper() + '-' + quote.upper()
    return symbol

def filterPairs(client, pairs):
    """
    Filter symbols with multiple pairs and choose only one pair from each symbol.
    Removes ETF pairs from the list.

    Args:
        client: The client object for interacting with the exchange.
        pairs (list): List of trading pairs.

    Returns:
        list: Filtered list of pairs, with one pair per symbol and without ETF pairs.
    """
    new_pairs = []  # List to store the filtered pairs (one per symbol)
    symbols = []  # List to keep track of symbols already processed

    for pair in pairs:
        symbol_detail = getSymbolDetail(client, pair)
        logger.info(symbol_detail)
        base_asset = symbol_detail['baseCurrency']

        # Check if the base asset of the pair is already processed
        if base_asset not in symbols:
            symbols.append(base_asset)
            new_pairs.append(pair)

    logger.info("Pairs before filtering: {}".format(new_pairs))

    # Remove ETF pairs
    filtered_pairs = filterETFPairs(new_pairs)

    logger.info("Pairs after filtering: {}".format(filtered_pairs))
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
    Allocate equal funds to each tradable pair.

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

def queryCEXKucoin():
    """
    Query Kucoin, fetch the market list, and whitelist only spot markets.

    Returns:
        dict: A dictionary containing the list of safe symbols and trading pairs.
    """
    # Initialize an empty dictionary to store the safe symbols and trading pairs
    safe_list = {'Symbols': [], 'Pairs': []}

    # Set initial values
    trading_pairs = []
    tokens = []
    status = False

    # Keep querying until successful
    while not status:
        try:
            # Fetch the market list from Kucoin
            symbolList = client.fetch_markets()
            status = True  # Set status to True to exit the loop if successful
            time.sleep(1)
        except Exception as err:
            logger.info("Failed to get Market List")
            logger.info("ERROR - {}".format(err))
            time.sleep(2)
            continue

    # Iterate through each symbol in the market list
    for symbolObject in symbolList:
        # Check if the symbol is on the spot market and already trading
        if symbolObject.get('spot',False) and symbolObject['info'].get('enableTrading',False):
            # Append the symbol to the trading_pairs list
            trading_pairs.append(symbolObject['info']['symbol'])

            # Add the base currency to the tokens list if it's not already present
            if symbolObject['info']['baseCurrency'] not in tokens:
                tokens.append(symbolObject['info']['baseCurrency'])

    # Update the safe_list dictionary with the symbols and pairs
    safe_list['Symbols'] = tokens
    safe_list['Pairs'] = trading_pairs

    logger.info("Market successfully retrieved from Kucoin!")

    # Return the dictionary containing the list of safe symbols and trading pairs
    return safe_list

def main():
    global client
    old_symbol_dict = dict()
    pairs_to_trade = []
    potential_trades = []
    #list of supported assets
    supportedAsset = ['USDT'] #['USDT','USDC','BUSD','DAI']
    useAllAssets = False
    client = libraryConnect()
    n = 0
    while True:
        if n < 1 :
            try:
                old_symbol_dict = queryCEXKucoin()
                n = n+1
            except Exception:
                time.sleep(2)
                continue
        else:
            set
            new_symbol_dict = queryCEXKucoin()

            for symbol in new_symbol_dict['Symbols']:
                if symbol not in old_symbol_dict['Symbols']:
                    symbol_to_trade = symbol
                    old_symbol_dict['Symbols'].append(symbol_to_trade)
            for pair in new_symbol_dict['Pairs']:
                if pair not in old_symbol_dict['Pairs']:
                    pair_to_trade = pair
                    pairs_to_trade.append(pair_to_trade)
                    old_symbol_dict['Pairs'].append(pair)
                    logger.info("New Pair found. Adding to list of tradeable pairs!")
            
            if len(pairs_to_trade) > 0:
                logger.info('{} pairs available to trade!'.format(len(pairs_to_trade)))
                filtered_pairs = filterPairs(client,pairs_to_trade)
                account_balance = getAccountBalance(client,"USDT")
                try:
                    funds = allocateFunds(filtered_pairs,account_balance)
                except Exception: 
                    logger.info("Can't allocate funds to tradeable pair")    
                

                for trade_signal in filtered_pairs:
                    symbolDetail = getSymbolDetail(client,trade_signal)
                    minSize = float(symbolDetail['baseMinSize'])
                    #logger.info('minsize: {}'.format(minSize))
                    maxSize = float(symbolDetail['baseMaxSize'])
                    #logger.info('maxsize: {}'.format(maxSize))
                    baseCurr = symbolDetail['baseCurrency']
                    #logger.info ("basecurrency: {}".format(baseCurr))
                    quoteCurr = symbolDetail['quoteCurrency']
                    #logger.info ("quotecurrency: {}".format(quoteCurr))
                    current_price = client.publicGetMarketStats({"symbol": trade_signal})['data']['last']
                    logger.info("Current price: {}".format(current_price))
                    # keep retrying the loop till you can get the currently trading price.
                    # the thing is, there are cases where the pair might not have started trading but visible through the api
                    if current_price == None:
                        logger.info("Time at which there is no price: {}".format(time.gmtime()))
                        continue

                    logger.info("Time at which there is price: {}".format(time.gmtime()))
                    size = funds[trade_signal]
                    
                    #check if the useAllAssets is false, then
                    #check if the quotecurrency is a supported asset.
                    #If it is not, remove the asset from the list of tradeable assets.
                    if useAllAssets == False and quoteCurr not in supportedAsset:
                        filtered_pairs.remove(trade_signal)
                        old_symbol_dict['Pairs'].append(trade_signal)
                        logger.info("{} has been removed as the base asset is not supported".format(trade_signal))
                        continue
                    
                    potential_trades.append({
                        "trade_signal": trade_signal,
                        "baseCurr":     baseCurr,
                        "quoteCurr":    quoteCurr,
                        "minSize":      minSize,
                        "maxSize":      maxSize,
                        "size":         size
                    })
                    logger.info("Potential trades: {}".format(potential_trades))
                    dump(potential_trades)

            else:
                logger.debug("No new pair(s) found")
    
        time.sleep(1)

if __name__ == "__main__":
    main()