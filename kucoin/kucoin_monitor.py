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
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [MODULE::%(module)s] [MESSAGE]:: %(message)s')
    
    file_handler = logging.handlers.TimedRotatingFileHandler("monitoring.log",when= "midnight")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
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

def custom_market_sell_order (client,symbol,size):
    """
    Function to place sell order on Kucoin
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
            result = client.create_market_sell_order(symbol,size)
            #change status to true once the order code execute without errors
            status = True
            return result
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

def readTradeList():
    with open("/root/snipeBot/kucoin_trade_list.json", 'r') as trade_list:
        data = json.load(trade_list)
    return data

def rewrite(trade):
    with open("/root/snipeBot/kucoin_trade_list.json",'w') as trade_list:
        data = json.load(trade_list)
        data.remove(trade)
        json.dump(data)

def getSymbolDetail (client, symbol):
    symbolList = client.publicGetSymbols()['data']
    for n in symbolList:
        if n['symbol'] == symbol:
            return n

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
            target_price = open_price + (0.2 * open_price)
            #At the moment, stop_loss is 20% lower than the opening price
            stop_loss = open_price - (0.2 * open_price)
            size = clean(account_balance,symbolDetail,current_price,"sell",100)
            logger.info("size to sell: {}".format(size))

            if current_price >= target_price:
                custom_market_sell_order(client,trade["symbol"],size)
                logger.info("Pair {} succesfully closed with a 20% gain".format(trade["symbol"]))
                rewrite(trade)
            if current_price <= stop_loss:
                custom_market_sell_order(client,trade["symbol"],size)
                logger.info("{} was stopped out with a 20% loss".format(trade["symbol"]))
                rewrite(trade)
                    
        time.sleep(1)

if __name__ == "__main__":
    main()