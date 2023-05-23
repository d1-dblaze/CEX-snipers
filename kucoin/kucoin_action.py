import os
import ccxt
import logging
import decimal
import logging.handlers
import time
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

def clean(balance_allocated, base_increment, current_price):
    """
    Clean and process data for order size calculation.

    Args:
        balance_allocated (float): The balance allocated for the asset.
        base_increment (float): 
        current_price (float): The current price of the asset.
        
    Returns:
        float: The cleaned and calculated order size.

    """
    logger.debug("Cleaning data")

    decimal.getcontext().rounding = decimal.ROUND_DOWN

    # Determine the number of decimal places for rounding.
    decimal_places = len(base_increment.split(".")[-1])

    logger.debug("The order size should be rounded to %d decimal places", decimal_places)

    size = decimal.Decimal(balance_allocated) / decimal.Decimal(current_price)

    # Round the order size to the specified decimal places.
    size_to_exchange = round(size, decimal_places)

    return float(size_to_exchange)

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
        with open("/root/snipeBot/kucoin_potential_trades.json", 'w') as trade_list:
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
            logger.debug("No trade object found in trade list")

        time.sleep(1)

def process_trade(client, trade):
    min_size = trade['minSize']
    max_size = trade['maxSize']
    base_currency = trade['baseCurr']
    quote_currency = trade['quoteCurr']
    trade_signal = trade['trade_signal']

    #Parameters and function to calculate the order size.
    fund_allocated = trade['fundAllocated']
    base_increment = trade['baseIncrement']
    current_price = client.publicGetMarketStats({"symbol": trade_signal})['data']['last']
    size = clean(fund_allocated,base_increment,current_price)

    logger.info("{} Size to buy: {}".format(trade_signal,size))

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
            logger.info("Market buy was not sucessful!")

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