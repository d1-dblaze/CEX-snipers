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
    file_handler = logging.handlers.TimedRotatingFileHandler("action.log", when="midnight")
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

def readTradeList():
    """
    Reads and returns the data from the trade list file.
    """
    try:
        with open("/root/snipeBot/kucoin_potential_trades.json", 'r') as trade_list:
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
        with open("/root/snipeBot/kucoin_potential_trades.json", 'r') as trade_list:
            data = json.load(trade_list)
            data.remove(trade)
        with open("/root/snipeBot/v1/kucoin_potential_trades.json", 'w') as trade_list:
            json.dump(data, trade_list)
    except FileNotFoundError:
        logger.error("Trade list file not found.")
    except (json.JSONDecodeError, ValueError):
        logger.error("Error decoding JSON data from the trade list file.")

def dump(monitoring):
    """
    Dumps the monitoring data to the trade list file.
    """
    try:
        with open("/root/snipeBot/kucoin_trade_list.json", "w") as trade_list:
            json.dump(monitoring, trade_list)
    except FileNotFoundError:
        logger.error("Trade list file not found.")
    except (json.JSONDecodeError, ValueError):
        logger.error("Error encoding JSON data to the trade list file.")

def main():
    global client
    global monitoring

    client = libraryConnect()
    monitoring = []

    while True:
        try:
            trade_list = readTradeList()
        except Exception as err:
            logger.error("Error reading trade list: {}".format(err))
            continue

        if trade_list:
            logger.info("{} trade object(s) available in the list".format(len(trade_list)))

            for trade in trade_list:
                try:
                    process_trade(client, trade)
                except Exception as err:
                    logger.error("Error processing trade: {}".format(err))

        else:
            logger.info("No trade object found in trade list")

        time.sleep(1)

def process_trade(client, trade):
    min_size = trade['minSize']
    max_size = trade['maxSize']
    base_currency = trade['baseCurr']
    quote_currency = trade['quoteCurr']
    trade_signal = trade['trade_signal']
    size = trade['size']

    logger.info("Size to buy: {}".format(size))

    if min_size <= size <= max_size:
        place_market_buy_order(client, base_currency, quote_currency, trade_signal, size, trade)
    elif size > max_size:
        size = max_size
        place_market_buy_order(client, base_currency, quote_currency, trade_signal, size)

def place_market_buy_order(client, base_currency, quote_currency, trade_signal, size, trade):
    symbol = "{}/{}".format(base_currency, quote_currency)
    logger.info("Trying to place a market buy order for symbol: {}".format(symbol))

    try:
        order = custom_market_buy_order(client, symbol, size)

        if 'info' in order and 'orderId' in order['info']:
            order_id = order['info']['orderId']
            logger.info("Successfully opened a trade on {} with order_id {}".format(symbol, order_id))
            open_price = get_opening_price(client, trade_signal)
            update_monitoring_list(trade_signal, open_price)
            rewrite(trade)
        else:
            logger.info("Could not place order!")

    except Exception as err:
        logger.error("Could not place order! Error occurred - {}".format(err))

def get_opening_price(client, trade_signal):
    response = client.publicGetMarketStats({"symbol": trade_signal})
    last_price = response['data']['last']
    return last_price

def update_monitoring_list(trade_signal, open_price):
    monitoring.append({
        'symbol': trade_signal,
        'openPrice': open_price
    })
    dump(monitoring)

if __name__ == "__main__":
    main()