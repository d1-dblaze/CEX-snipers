import os
import ccxt
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
    file_handler = logging.handlers.TimedRotatingFileHandler("../logs/mexc/mexc_action.log",when= "midnight")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    
    # Configure the console handler for logging to the console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter) 

    # Create a logger and add the file handler and console handler
    loggerHandle = logging.getLogger(name)
    loggerHandle.addHandler(file_handler)
    loggerHandle.addHandler(console_handler)
    loggerHandle.setLevel(logging.INFO)
    
    return loggerHandle

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

    # Determine the number of decimal places for rounding
    # mexc sometimes put 0 as the base increment so we try to get it from the price
    if float(base_increment) == 0.0:
        decimal_places = len(str(current_price).split(".")[-1])
    else:
        decimal_places = len(base_increment.split(".")[-1])

    logger.debug("The order size should be rounded to %d decimal places", decimal_places)

    size = decimal.Decimal(balance_allocated) / decimal.Decimal(current_price)

    # Round the order size to the specified decimal places.
    size_to_exchange = round(size, decimal_places)

    return float(size_to_exchange)

def custom_market_buy_order (client,symbol,size):
    """
    Place a market buy order on mexc and handle errors with retries.

    Args:
        client: The CCXT client instance for mexc.
        symbol (str): The trading symbol for the order.
        size: The size or quantity to buy in quote currency.

    Returns:
        dict or str: The order result if successful, or the encountered error.

    """
    # Retry counter and order status
    counter = 0
    status = False
    
    #while the order status is false, keep trying to place the order
    while not status:
        try: 
            time.sleep(1) #sleep for one sec
            result = client.spotPrivatePostOrder({
                "symbol": symbol,
                "side": "BUY",
                "type": "MARKET",
                "quoteOrderQty": size
            })
            status = True
            return result
        except ccxt.RequestTimeout as e:
            # Handle request timeout error
            logger.info("Encountered request timeout error. Retrying order placement (Attempt {})".format(counter))
            if counter == 3:
                status = True
                return e
            counter += 1
            time.sleep(1)  # Sleep for one second between retries
        except ccxt.InsufficientFunds as e:                       
            logger.info("Balance insufficient!")
            status = True  # Set status to true 
            return str(e)
        #except other exchange errors
        except ccxt.ExchangeError as e:
            error_message = str(e)
            logger.info("Encountered this Exchange error - {}".format(e))

            if 'Too many requests' in error_message:
                # Handle rate limit error (Too many requests)
                logger.info("Encountered rate limit error. Retrying order placement (Attempt {})".format(counter))
                if counter == 3:
                    status = True
                    break
                counter += 1
                time.sleep(1)  # Sleep for one second between retries
            elif "api market order is disabled" in error_message:
                logger.info("Market order is disabled, trying limit order")
                result = custom_limit_buy_order(client,symbol,size) 
                return result
            else:
                # Handle other exchange errors
                logger.info("Error encountered while placing an order: {}".format(error_message))
                return error_message
        except Exception as e:
            # Handle general exceptions
            error_message = str(e)
            logger.info("Error encountered while placing an order: {}".format(error_message))
            return error_message

def custom_limit_buy_order (client,symbol,fund_allocated):
    """
    Place a limit buy order on mexc and handle errors with retries.

    Args:
        client: The CCXT client instance for mexc.
        symbol (str): The trading symbol for the order.
        fund_allocated: amount to buy in quote currency.

    Returns:
        dict or str: The order result if successful, or the encountered error.

    """
    # Retry counter and order status
    counter = 0
    status = False
    
    #while the order status is false, keep trying to place the order
    while not status:
        try: 
            time.sleep(1) #sleep for one sec
            current_price = get_current_price(client,symbol)
            base_increment = trade['base_increment']
            #size to buy in base currency
            size = clean(fund_allocated,base_increment,current_price)

            result = client.spotPrivatePostOrder({
                "symbol": symbol,
                "side": "BUY",
                "type": "LIMIT",
                "quantity": size,
                "price": current_price
            })
            status = True
            return result
        except ccxt.RequestTimeout as e:
            # Handle request timeout error
            logger.info("Encountered request timeout error. Retrying order placement (Attempt {})".format(counter))
            if counter == 3:
                status = True
                return e
            counter += 1
            time.sleep(1)  # Sleep for one second between retries
        except ccxt.InsufficientFunds as e:                       
            logger.info("Balance insufficient!")
            status = True  # Set status to true 
            return e
        except ccxt.ExchangeError as e:
            error_message = str(e)
            logger.info("Encountered this Exchange error - {}".format(e))
            if 'Too many requests' in error_message:
                # Handle rate limit error (Too many requests)
                logger.info("Encountered rate limit error. Retrying order placement (Attempt {})".format(counter))
                if counter == 3:
                    status = True
                    break
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
        with open("/root/snipeBot/mexc_potential_trades.json", 'r') as trade_list:
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
        with open("/root/snipeBot/mexc_potential_trades.json", 'r') as trade_list:
            data = json.load(trade_list)
            data.remove(trade)
        with open("/root/snipeBot/mexc_potential_trades.json", 'w') as trade_list:
            json.dump(data, trade_list)
    except FileNotFoundError:
        logger.error("Trade list file not found.")
    except (json.JSONDecodeError, ValueError):
        logger.error("Error decoding JSON data from the trade list file.")

def removeFromFile(symbol:str):
    """
    Rewrites the trade list file after removing the specified trade.
    """
    sym = symbol if symbol.find('-') != -1 else symbol.replace('/', '-')
    try:
        with open("/root/snipeBot/mexc_potential_trades.json", 'r') as trade_list:
            data:list = json.load(trade_list)
            for trade in data:
                if trade['trade_signal'] == sym:        
                    data.remove(trade)
        with open("/root/snipeBot/mexc_potential_trades.json", 'w') as trade_list:
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
        with open("/root/snipeBot/mexc_trade_list.json", 'r') as trade_list:
            data = json.load(trade_list)
            for trade in monitoring:
                data.append(trade)
        with open("/root/snipeBot/mexc_trade_list.json", "w") as trade_list:
            json.dump(data, trade_list)
    except FileNotFoundError:
        logger.error("Trade list file not found.")
    except (json.JSONDecodeError, ValueError):
        logger.error("Error encoding JSON data to the trade list file.")                    
        
def main():
    global client
    global monitoring
    global trade
    
    monitoring = []
    client = libraryConnect()

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
    min_size = float(trade['minSize'])
    max_size = float(trade['maxSize'])
    trade_signal = trade['trade_signal']

    #fund_allocated is in the quote currency
    fund_allocated = trade['fund_allocated']
    
    #in mexc, when placing market order, we specify the quantity in
    #the quote currency and not base currency.
    size = float(fund_allocated)

    logger.info("{} Size to buy: ${}".format(trade_signal,size))

    if min_size <= size <= max_size:
        place_market_buy_order(client, trade_signal, size, trade)
    elif size > max_size:
        size = max_size
        place_market_buy_order(client, trade_signal, size, trade)
    elif size < min_size:
        logger.info("{} Size to buy= {} is less than minSize allowed= {}, removing!".format(trade_signal,size,min_size))
        rewrite(trade)

def place_market_buy_order(client, trade_signal, size, trade):
    symbol = trade_signal
    logger.info("Trying to place a market buy order for symbol: {}".format(symbol))

    try:
        order = custom_market_buy_order(client, symbol, size)

        if 'orderId' in order:
            order_id = order['orderId']
            logger.info("Successfully opened a trade on {} with order_id {}".format(symbol, order_id))
            open_price = order['price']
            update_monitoring_list(trade_signal, open_price)
            rewrite(trade)
        else:
            logger.info("Market buy was not sucessful!")

    except Exception as err:
        logger.error("Could not place order! Error occurred - {}".format(err))

def update_monitoring_list(trade_signal, open_price):
    monitoring.append({
        'symbol': trade_signal,
        'openPrice': open_price
    })
    dump(monitoring)

def get_current_price(client, trade_signal):
    response = client.fetchTicker(trade_signal)
    last_price = float(response['info']['lastPrice'])
    return last_price

def test():
    global trade 
    
    trade = {"base_increment": '4'}
    client = libraryConnect()
    order = custom_market_buy_order(client, "YGGUSDT",5.5)
    #order = custom_limit_buy_order(client, "YGGUSDT",10)
    print(order)
    
if __name__ == "__main__":
    main()
    #test()