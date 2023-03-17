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
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [MODULE::%(module)s] [MESSAGE]:: %(message)s')
    
    file_handler = logging.handlers.TimedRotatingFileHandler("action.log",when= "midnight")
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
    Function to place buy order on Kucoin
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
            result = client.create_market_buy_order(symbol,size)
        except Exception as e:
            #returns the string representation of the execution error
            err = repr(e)
            #if the kucoin "Too many request" error is present, leave status as false and continue the loop
            if '429000' in err:
                counter += 1
                logger.info("Encountered Kucoin 'Too many Request' Error, Retrying order placement again "+ str(counter))
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
            logger.info("Place order successful")
            return result

def clean (accountBalance,details,current_price,side,riskP):
    logger.info("======cleaning data =======")
    decimal.getcontext().rounding = decimal.ROUND_DOWN
    #convert the risk% to float.
    risk = float(riskP)
    #Increment of the order size
    baseIncrement = details['baseIncrement']
    #simple algorithm to get the number of decimal place
    #split the number value with reference to the decimal point.
    splitValues = baseIncrement.split(".")
    #print(splitValues)
    if len(splitValues) == 2:           #that is, real and floating part
        decimalP = len(splitValues[1])

    logger.info("The order size should be rounded to %d",decimalP)
    #if side is buy, calculate the size with the formula below
    if side == "buy":    
        size = decimal.Decimal(risk/100 * accountBalance) / decimal.Decimal(current_price)
        size_to_exchange = round(size,decimalP)
        #if side is sell, sell 100% of the asset.
    elif side == "sell":
        #@to_do: remove the risk percentage and just sell everything
        size = decimal.Decimal(risk/100 * accountBalance) * decimal.Decimal(1)
        size_to_exchange = round(size,decimalP)

    return float(size_to_exchange)

def getAccountBalance (client,currency):
    logger.info ("======Retrieving account Details======")
    acctInfo = client.privateGetAccounts({"currency":currency})['data'] 
    logger.info("acctInfo: {} ".format (acctInfo))
    #if it doesn't return any details
    if len(acctInfo) == 0:
        logger.info ("Asset doesn't exist in your Account. Try topping up")
        return ("Asset doesn't exist in your Account. Try topping up")
    for info in acctInfo:
        if info['type'] == 'trade':
            availableBalance = info['available']
            return float(availableBalance)

def getSymbolDetail (client, symbol):
    symbolList = client.publicGetSymbols()['data']
    for n in symbolList:
        if n['symbol'] == symbol:
            return n

def readTradeList():
    with open("/root/snipeBot/kucoin_potential_trades.json", 'r') as trade_list:
        data = json.load(trade_list)
    return data

def rewrite(trade):
    with open("/root/snipeBot/kucoin_potential_trades.json",'w') as trade_list:
        data = json.load(trade_list)
        data.remove(trade)
        json.dump(data)

def dump(monitoring):
    with open("/root/snipeBot/kucoin_trade_list.json","w") as trade_list:
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

        if len(trade_list) > 0: 
            logger.info("{} availbale trade object in list".format(len(trade_list)))
            for trade in trade_list:
                minSize = trade['minSize']
                maxSize = trade['maxSize']
                baseCurr = trade['baseCurr']
                quoteCurr = trade['quoteCurr']
                trade_signal = trade['trade_signal']
                size = trade['size']

                logger.info("size to buy: {}".format(size))
                
                if size > minSize and size < maxSize:
                    try:
                        symbol_for_trade = baseCurr + '/' + quoteCurr
                        logger.info("Trying to place an order!")
                        order = custom_market_buy_order(client,symbol_for_trade,size)
                        try:
                            orderId = order['info']["orderId"]
                            if orderId:
                                logger.info("Successfully opened a trade on {0} with order_id {1}".format(symbol_for_trade,orderId))
                                #Can't find a way to get the opening price of an order
                                #So I use the last price.
                                open_price = client.publicGetMarketStats({"symbol":trade_signal})['data']['last']
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
                
                elif size > maxSize:
                    size = maxSize
                    try:
                        symbol_for_trade = baseCurr + '/' + quoteCurr
                        
                        order = custom_market_buy_order(client,symbol_for_trade,size)
                        try:
                            orderId = order['info']["orderId"]
                            if orderId:
                                logger.info("Successfully opened a trade on {0} with order_id {1}".format(symbol_for_trade,orderId))
                                #Can't find a way to get the opening price of an order
                                #So I use the last price.
                                open_price = client.publicGetMarketStats({"symbol":trade_signal})['data']['last']
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
        else: 
            logger.info("No trade object found in trade list")                    
        time.sleep(1)

if __name__ == "__main__":
    main()