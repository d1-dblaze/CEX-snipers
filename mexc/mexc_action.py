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
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [MODULE::%(module)s] [MESSAGE]:: %(message)s')
    
    file_handler = logging.handlers.TimedRotatingFileHandler("../logs/mexc_action.log",when= "midnight")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter) 

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
 
#check for the error here
def custom_market_buy_order (client,symbol,qSize):
    """
    Function to place buy order on MEXC
    """
    #This needs to return the price at which the order was opened
    #alongside the order result.
    """
    This while loop is there to curb the 429 "Too many request" error which always lead
    to loss of trades.
    """
    status = False          #status of the order
    counter = 0             #Retry counter
    #while the order status is false, keep trying to place the order
    while status == False:
        try: 
            time.sleep(1) #sleep for one sec
            #logger.info("symbol type is : {}".format(type(symbol)))
            result = client.spotPrivatePostOrder({
                "symbol":symbol,
                "side":"BUY",
                "type":"MARKET",
                "quoteOrderQty":10
                })
        except Exception as e:
            #returns the string representation of the execution error
            err = repr(e)
            #if the MEXC "Too many request" error is present, leave status as false and continue the loop
            if '429000' in err:
                counter += 1
                logger.info("Encountered MEXC 'Too many Request' Error, Retrying order placement again "+ str(counter))
                continue
            #if the http "Too many request" error is present, leave status as false and continue the loop
            elif '429' in err:
                time.sleep(4) #sleep for 4 sec
                logger.info(err)
                counter += 1
                logger.info("Encountered Http 'Too many Request' Error, Retrying order placement again "+ str(counter))
                continue
            #else, break from the loop and return the error encountered.
            else:
                status = True
                logger.info("Error encountered while placing an order - ".format(err))
                return err
        else:
            #change status to true once the order code execute without errors
            status = True
            logger.info("Result from trying to place a trade is: {}".format(result))
            return result
            
def clean (balance_allocated, base_increment, current_price):
    """
    Clean and process data for order size calculation.

    Args:
        balance_allocated (float): The balance allocated for the asset.
        base_increment (float): 
        current_price (float): The current price of the asset.
        
    Returns:
        float: The cleaned and calculated order size.

    """
    
    logger.info("======cleaning data =======")
    decimal.getcontext().rounding = decimal.ROUND_DOWN
    #convert the risk% to float.
    risk = float(riskP)

    #if side is buy, calculate the size with the formula below
    if side == "buy":    
        size = decimal.Decimal(risk/100 * accountBalance) / decimal.Decimal(current_price)
        #round down to the nearest whole number.
        size_to_exchange = round(size)
        #if side is sell, sell 100% of the asset.
    elif side == 'sell':
        size = decimal.Decimal(risk/100 * accountBlance) * decimal.Decimal(1)
        size_to_exchange = round(size)

    return float(size_to_exchange)

def getAccountBalance (client,currency):
    logger.info ("======Retrieving account Details======")
    acctInfo = client.spotPrivateGetAccount()
    logger.info("acctInfo: {} ".format (acctInfo))
    
    for asset in acctInfo["balances"]:
        if asset['asset'] == currency:
            availableBalance = asset['free']
            #test
            logger.info('Available balance: {}'.format(availableBalance))
            return float(availableBalance)

def getSymbolDetail (client, symbol):
    symbolList = client.spotPublicGetExchangeInfo()['symbols']
    for n in symbolList:
        if n['symbol'] == symbol:
            return n
        
def readTradeList():
    with open("/root/snipeBot/mexc_potential_trades.json", 'r') as trade_list:
        data = json.load(trade_list)
    return data

def rewrite(trade):
    with open("/root/snipeBot/mexc_potential_trades.json",'w') as trade_list:
        data = json.load(trade_list)
        data.remove(trade)
        json.dump(data)

def dump(monitoring):
    with open("/root/snipeBot/mexc_trade_list.json","w") as trade_list:
        json.dump(monitoring,trade_list)

def main():
    global client
    monitoring = []
    client = libraryConnect()

    while True:
        try:
            trade_list = readTradeList()
        except Exception as err:
            continue

        for trade in trade_list:
            trade_signal = trade['trade_signal']
            qsize = trade['qsize']

            minSize_USDT = 5.0    
            maxSize_USDT = 5000000.0

            logger.info("size to buy: {}".format(qsize))

            if qsize > minSize_USDT and qsize < maxSize_USDT:
                try:
                    logger.info("Trying to place an order on {}".format(trade_signal))
                    order = custom_market_buy_order(client,trade_signal,10)
                    try:
                        orderId = order["orderId"]
                        if orderId:
                            logger.info("Successfully opened a trade on {0} with order_id {1}".format(trade_signal,orderId))
                            open_price = order['price']
                            monitoring.append({
                                'symbol': trade_signal,
                                'openPrice': open_price
                                })
                            #dump the monitoring list to a file.
                            dump(monitoring)
                            rewrite(trade)

                    except KeyError:
                        logger.info("Could not place order!")

                except Exception as err: 
                    logger.info('Could not place order! This error Occurred - {}'.format(err))
            
            elif qsize > maxSize_USDT:
                qsize = maxSize_USDT
                try:
                    order = custom_market_buy_order(client,trade_signal,qsize)
                    try:
                        orderId = order["orderId"]
                        if orderId:
                            logger.info("Successfully opened a trade on {0} with order_id {1}".format(trade_signal,orderId))
                            open_price = order['price']
                            monitoring.append({
                                'symbol': trade_signal,
                                'openPrice': open_price
                                })
                            #dump the monitoring list to a file.
                            dump(monitoring)
                            rewrite(trade)

                    except KeyError:
                        logger.info("Could not place order!")

                except Exception as err: 
                    logger.info('Could not place order! This error Occurred - {}'.format(err))

        time.sleep(1)

if __name__ == "__main__":
    main()