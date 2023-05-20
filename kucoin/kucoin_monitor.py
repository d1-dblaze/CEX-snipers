import os
import ccxt
import logging
import logging.handlers
import time
import json
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
    file_handler = logging.handlers.TimedRotatingFileHandler("monitoring.log", when="midnight")
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

def readTradeList():
    """
    Reads and returns the data from the trade list file.
    """
    try:
        with open("/root/snipeBot/kucoin_trade_list.json", 'r') as trade_list:
            data = json.load(trade_list)
        return data
    except FileNotFoundError:
        logger.error("Trade list file not found.")
        return None
    except json.JSONDecodeError:
        logger.error("Error decoding JSON data from the trade list file.")
        return None
    
def rewrite(trade):
    """
    Rewrites the trade list file after removing the specified trade.
    """
    try:
        with open("/root/snipeBot/kucoin_trade_list.json", 'r') as trade_list:
            data = json.load(trade_list)
            data.remove(trade)
        with open("/root/snipeBot/v1/kucoin_trade_list.json", 'w') as trade_list:
            json.dump(data, trade_list)
    except FileNotFoundError:
        logger.error("Trade list file not found.")
    except (json.JSONDecodeError, ValueError):
        logger.error("Error decoding JSON data from the trade list file.")

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

def main():
    global client
    client = libraryConnect()

    while True:
        try:
            monitoring = readTradeList()
        except Exception as err:
            continue

        for trade in monitoring:    
            logger.info("Checking pairs in the monitoring list") 
            symbolDetail = getSymbolDetail(client,trade['symbol'])     
            baseCurr = symbolDetail['baseCurrency']
            #logger.info ("basecurrency: {}".format(baseCurr))
            account_balance = getAccountBalance(client,baseCurr)   
            current_price = float(client.publicGetMarketStats({"symbol":trade["symbol"]})['data']['last'])
            #target price is 20% greater than the opening price.
            open_price = float(trade["openPrice"])
            print("open price: {}".format(open_price))
            target_price = open_price * 1.2
            #At the moment, stop_loss is 20% lower than the opening price
            stop_loss = open_price * 0.8
            size = clean(account_balance,symbolDetail,current_price,"sell",100)
            logger.info("size to sell: {}".format(size))

            if current_price >= target_price or current_price <= stop_loss:
                custom_market_sell_order(client,trade["symbol"],size)
                if current_price >= target_price:
                    print("Pair {} closed with a 20% gain".format(trade['symbol']))
                else:
                    print("{} stopped out with a 20% loss".format(trade['symbol']))
                rewrite(trade)
                    
        time.sleep(1)

if __name__ == "__main__":
    main()