import os
import ccxt
import logging
import logging.handlers
import time
import decimal
from uuid import uuid1
from dotenv import load_dotenv

load_dotenv()

def getmylogger(name):
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [MODULE::%(module)s] [MESSAGE]:: %(message)s')
    
    file_handler = logging.handlers.TimedRotatingFileHandler("snipe_bot.log",when= "midnight")
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

def checkOrderResponse(response):
    try:
        if isinstance(response,dict):
            message = {
                "code": "success",
                "message": "order executed",
                "orderId": response['info']['orderId'],
                "clientOrderId": response['clientOrderId']
            }
        else:
            return str(response)
    
    except Exception as e:
        logger.info("{}".format(str(e)))
        
        message = {
            "code": "error",
            "message": "Order failed",
	        "errorMessage":str(e)
        }
    return message

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
    elif side == 'sell':
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

def writeToFile (filename):
    with open ("{}".format(filename), "a") as file:
        file.write(str(client.fetch_markets()))

def buildPair(base,quote):
    symbol = base.upper() + '-' + quote.upper()
    return symbol

def filterPairs(client,pairs):
    """
    This function filter symbols with multiple pair and only
    choose one out of the multiple pairs. For example, it chooses
    one out of ETH-USDT and ETH-DAI assuming both are in the list
    of tradeable pairs.
    This function is optional to use.
    """
    new_pairs = []
    symbols = []
    for pair in pairs:
        dt = getSymbolDetail(client,pair)
        logger.info(dt)
        base_asset = dt['baseCurrency']
        if base_asset not in symbols:
            symbols.append(base_asset)
            new_pairs.append(pair)
    return new_pairs

def allocateFunds(pairs):
    """
    This function allocates a % of the total balance to each tradeable
    Pair
    """
    funds = {}
    number_of_pairs = len(pairs)
    percentage_for_each = 100 / number_of_pairs
    for pair in pairs:
        funds[pair] = percentage_for_each
    return funds

def queryCEXKucoin ():
    """
    This function queries Kucoin, fetches the market list, and whitelist
    only spot markets. 
    """
    safe_list = dict()
    trading_pairs = []
    tokens = []
    try: 
        symbolList = client.fetch_markets()
        for symbolObject in symbolList:
            #if symbol is on the spot market and already trading
            if symbolObject['spot'] == True and symbolObject['info']['enableTrading'] == True:
                trading_pairs.append(symbolObject['info']['symbol'])           
                if symbolObject['info']['baseCurrency'] not in tokens:
                    tokens.append(symbolObject['info']['baseCurrency'])
        safe_list['Symbols'] = tokens
        safe_list['Pairs'] = trading_pairs
        logger.info("Market successfully retrieved from kucoin!")           
    except Exception as err:
        logger.info("Failed to get Market List")
        logger.info("ERROR - {}".format(err))

    return safe_list

def main():
    global client
    old_symbol_dict = dict()
    pairs_to_trade = []
    monitoring = []
    client = libraryConnect()
    n = 0
    while True:
        if n < 1 :
            old_symbol_dict = queryCEXKucoin()
            n = n+1
        else:
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
            
            if len(pairs_to_trade) > 1:
                logger.info('{} pairs available to trade!'.format(len(pairs_to_trade)))
                filtered_pairs = filterPairs(client,pairs_to_trade)
                funds = allocateFunds(filtered_pairs)

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
                    current_price = client.publicGetMarketStats({"symbol":trade_signal})['data']['last']
                    account_balance = getAccountBalance(client,quoteCurr)
                    #risk percentage
                    riskP = funds[trade_signal]
                    size = clean(account_balance,symbolDetail,current_price,"buy",riskP)

                    if size > minSize and size < maxSize:
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
                                    pairs_to_trade.remove(trade_signal)
                                    filtered_pairs.remove(trade_signal)
                            except KeyError:
                                logger.info("Could not place order!")

                        except Exception as err: 
                            logger.info('Could not place order! This error Occurred - {}'.format(err))
                    
                    else:
                        size = maxSize
                        try:
                            symbol_for_trade = baseCurr + '/' + quoteCurr
                            
                            order = custom_market_buy_order(client,symbol_for_trade,size)
                            try:
                                orderId = order["orderId"]
                                if orderId:
                                    logger.info("Successfully opened a trade on {0} with order_id {1}".format(symbol_for_trade,orderId))
                                    #Can't find a way to get the opening price of an order
                                    #So I use the last price.
                                    open_price = client.publicGetMarketStats({"symbol":trade_signal})['data']['last']
                                    monitoring.append({
                                        'symbol': trade_signal,
                                        'openPrice': open_price
                                        })
                                    pairs_to_trade.remove(trade_signal)
                                    filtered_pairs.remove(trade_signal)
                            except KeyError:
                                logger.info("Could not place order!")

                        except Exception as err: 
                            logger.info('Could not place order! This error Occurred - {}'.format(err))

            else:
                logger.info("No new pair(s) found")
                
            
            for trade in monitoring:     
                symbolDetail = getSymbolDetail(client,trade['symbol'])     
                minSize = float(symbolDetail['baseMinSize'])
                #logger.info('minsize: {}'.format(minSize))
                maxSize = float(symbolDetail['baseMaxSize'])
                #logger.info('maxsize: {}'.format(maxSize))
                baseCurr = symbolDetail['baseCurrency']
                #logger.info ("basecurrency: {}".format(baseCurr))
                quoteCurr = symbolDetail['quoteCurrency']
                #logger.info ("quotecurrency: {}".format(quoteCurr))
                account_balance = getAccountBalance(client,quoteCurr)   
                current_price = client.publicGetMarketStats({"symbol":trade["symbol"]})['data']['last']
                #target price is 20% greater than the opening price.
                target_price = trade["openPrice"] + (0.2 * trade["openPrice"])
                size = clean(account_balance,symbolDetail,current_price,"sell",100)
                    
                if current_price >= target_price:
                    custom_market_sell_order(client,trade["symbol"],size)
                    logger.info("Pair {} succesfully closede with a 20% gain".format(trade["symbol"]))
                    monitoring.remove(trade)
        time.sleep(1)

if __name__ == "__main__":
    main()