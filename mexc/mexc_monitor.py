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
    file_handler = logging.handlers.TimedRotatingFileHandler("../logs/mexc/mexc_monitor.log",when= "midnight")
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
 
def custom_market_sell_order (client,symbol,size):
    """
    Place a market sell order on mexc and handle errors with retries.

    Args:
        client: The CCXT client instance for mexc.
        symbol (str): The trading symbol for the order.
        size: The size or quantity to sell.

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
                "symbol":symbol,
                "side":"SELL",
                "type":"MARKET",
                "quantity":size
                })
            #change status to true once the order code execute without errors
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
            elif "api market order is disabled" in error_message:
                logger.info("Market order is disabled, trying limit order")
                result = custom_limit_sell_order(client,symbol,size) 
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

def custom_limit_sell_order (client,symbol,size):
    """
    Place a limit sell order on mexc and handle errors with retries.

    Args:
        client: The CCXT client instance for mexc.
        symbol (str): The trading symbol for the order.
        size: The size or quantity to sell.

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

            result = client.spotPrivatePostOrder({
                "symbol":symbol,
                "side":"SELL",
                "type":"LIMIT",
                "quantity":size,
                "price": current_price
                })
            
            logger.info(f"{size}")
            #change status to true once the order code execute without errors
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
    logger.debug("Cleaning data")

    decimal.getcontext().rounding = decimal.ROUND_DOWN

    # Convert the risk percentage to float.
    risk = float(risk_percentage)

    
    #base increment is the smallest increase in the base price.
    base_increment = details['baseSizePrecision']
    
    # Determine the number of decimal places for rounding
    # mexc sometimes put 0 as the base increment so we try to get it from the price
    if float(base_increment) == 0.0:
        decimal_places = len(str(current_price).split(".")[-1])
    else:
        decimal_places = len(base_increment.split(".")[-1])

    logger.debug("The order size should be rounded to %d decimal places", decimal_places)

    # Calculate the order size based on the side of the trade.
    if side == "buy":
        size = decimal.Decimal(risk / 100 * account_balance) / decimal.Decimal(current_price)
    elif side == "sell":
        size = decimal.Decimal(risk / 100 * account_balance)

    # Round the order size to the specified decimal places.
    size_to_exchange = round(size, decimal_places)

    return float(size_to_exchange)

def getAccountBalance (client,currency):
    """
    Retrieve the available balance of a specific currency in the account.

    Args:
        client: The client object for interacting with the exchange.
        currency (str): The currency symbol to retrieve the balance for.

    Returns:
        float or str: The available balance of the currency as a float if it exists, or an error message as a string.
    """
    logger.info("Retrieving account details")
    account_info = client.spotPrivateGetAccount()
    logger.info("Account information: {}".format(account_info))
    
    for asset in account_info["balances"]:
        if asset['asset'] == currency:
            availableBalance = asset['free']
            logger.info('Available balance: {}'.format(availableBalance))
            return float(availableBalance)
    
    return 0

def readTradeList():
    """
    Reads and returns the data from the trade list file.
    """
    try:
        with open("/root/snipeBot/mexc_trade_list.json", 'r') as trade_list:
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
        with open("/root/snipeBot/mexc_trade_list.json", 'r') as trade_list:
            data = json.load(trade_list)
            data.remove(trade)
        with open("/root/snipeBot/mexc_trade_list.json", 'w') as trade_list:
            json.dump(data, trade_list)
    except FileNotFoundError:
        logger.error("Trade list file not found.")
    except (json.JSONDecodeError, ValueError):
        logger.error("Error decoding JSON data from the trade list file.")
            
def getSymbolDetail (client, symbol):
    """
    Retrieve details of a specific symbol from the exchange.

    Args:
        client: The client object for interacting with the exchange.
        symbol (str): The symbol to retrieve details for.

    Returns:
        dict or None: Details of the symbol if found, None otherwise.
    """
    
    symbolList = client.spotPublicGetExchangeInfo()['symbols']
    for symbol_info in symbolList:
        if symbol_info['symbol'] == symbol:
            return symbol_info
    
    return None  # Symbol not found, return None

def main():
    global client
    client = libraryConnect()

    while True:
        try:
            monitoring = readTradeList()
        except Exception:
            continue         
        
        if monitoring:     
            logger.info("Checking pairs in the monitoring list") 
            
            for trade in monitoring: 
                try:
                    process_trade(client,trade)
                except Exception as err:
                    logger.error("Error processing sell trade: {}".format(err))
                
        time.sleep(1)

def process_trade(client, trade):
    trade_signal = trade["symbol"]  
    logger.info("Monitoring {}".format(trade_signal)) 
    symbolDetail = getSymbolDetail(client,trade_signal)   
    baseCurr = symbolDetail['baseAsset']
    quoteCurr = symbolDetail['quoteAsset']
    account_balance = getAccountBalance(client,baseCurr)   
    current_price = get_current_price(client,trade_signal)
    
    #target price is 20% greater than the opening price.
    open_price = float(trade["openPrice"])
    logger.info("open price: {}".format(open_price))
    target_price = open_price * 1.2
    #At the moment, stop_loss is 20% lower than the opening price
    stop_loss = open_price * 0.8
    
    size = clean(account_balance,symbolDetail,current_price,"sell",100)
    logger.info("{} size to sell: {} at TP: {} or SL: {}".format(trade_signal,size,target_price,stop_loss))

    if current_price >= target_price or current_price <= stop_loss:
        logger.info("Trying to place a market sell order for symbol: {}".format(trade_signal))

        try:
            custom_market_sell_order(client,trade_signal,size)
            if current_price >= target_price:
                logger.info("Pair {} closed with a 20% gain".format(trade_signal))
            else:
                logger.error("{} stopped out with a 20% loss".format(trade_signal))
            rewrite(trade)
        except Exception as err:
            logger.error("Could not place order! Error occurred - {}".format(err))

def get_current_price(client, trade_signal):
    response = client.spotPublicGetTickerPrice({"symbol":trade_signal})
    last_price = float(response['price'])
    return last_price

def test():
    client = libraryConnect()
    order = custom_market_sell_order(client, "YGGUSDT",8.67 )
    #order = custom_limit_sell_order(client, "YGGUSDT",8.63)
    print(order)
    
if __name__ == "__main__":
    #main()
    test()