import os
import ccxt
import requests
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
    
    file_handler = logging.handlers.TimedRotatingFileHandler("scanner.log",when= "midnight")
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
 
def checkOrderResponse(response):
    try:
        if isinstance(response,dict):
            message = {
                "code": "success",
                "message": "order executed",
                "orderId": response['orderId']
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
            logger.info("symbol type is : {}".format(type(symbol)))
            result = client.spotPrivatePostOrder({
                "symbol":symbol,
                "side":"BUY",
                "type":"MARKET",
                "quoteOrderQty":10
                })
            #change status to true once the order code execute without errors
            status = True
            logger.info("Result from trying to place a trade is: {}".format(result))
            return result
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
 
def custom_market_sell_order (client,symbol,size):
    """
    Function to place sell order on MEXC
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
            result = result = client.spotPrivatePostOrder({
                "symbol":symbol,
                "side":"SELL",
                "type":"MARKET",
                "quantity":size
                })
            #change status to true once the order code execute without errors
            status = True
            return result
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

def clean (accountBalance,current_price,side,riskP):
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
        size = decimal.Decimal(risk/100 * accountBalance) * decimal.Decimal(1)
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

def dump(potential_trades:list):
    with open("/root/snipeBot/mexc_potential_trades.json","r") as trade_list:
        data = json.load(trade_list)
        for obj in potential_trades:
            for dataObj in data:
                #if the trade_signal already exist in the file, don't dump
                if obj['trade_signal'] == dataObj['trade_signal']:
                    potential_trades.remove(obj)
                    logger.info("{} already exist in the file. Removing".format(dataObj['trade_signal']))
    
    with open("/root/snipeBot/mexc_potential_trades.json","w") as trade_list:
        json.dump(potential_trades,trade_list)

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
        if dt == None or dt['symbol'] == None:
            pairs.remove(pair)
            continue
        base_asset = dt['baseAsset']
        if base_asset not in symbols:
            symbols.append(base_asset)
            new_pairs.append(pair)
    
    logger.info("Pairs before filtering for ETF assets: {}".format(new_pairs))        
    #remove all ETF pairs        
    filtered_pair = filterETFPairs(new_pairs)
    logger.info("Pairs after filtering out ETF assets: {}".format(filtered_pair))
    return filtered_pair

def filterETFPairs(pairs):
    """
    This function filters out those ETF pairs e.g AXS3s, MINA3L
    """

    for pair in pairs:
        if "3L" in pair or "3S" in pair:
            pairs.remove(pair)
    
    return pairs

def allocateFunds(pairs, account_balance):
    """
    This function allocates equal funds to each tradeable
    Pair.
    Returns a dict
    """
    decimal.getcontext().rounding = decimal.ROUND_DOWN
    funds = {}
    number_of_pairs = len(pairs)
    if number_of_pairs > 0:
        fund_for_each = decimal.Decimal(account_balance) / decimal.Decimal(number_of_pairs)
    else:
        return
    
    for pair in pairs:
        funds[pair] = round(float(fund_for_each),3)
    logger.info("funds: {}".format(funds))  
    return funds

def queryCEXMEXC():
    """
    This function queries mexc, fetches the market list, and whitelist
    only spot markets. 
    """
    safe_list = dict()
    trading_pairs = []
    tokens = []
    status = False
    while status == False:

        try: 
            symbolList = client.fetch_markets()      
        except Exception as err:
            logger.info("Failed to get Market list")
            logger.info("ERROR - {}".format(err))
            time.sleep(2)
            continue
        else:
            status = True
            time.sleep(2)   
            for symbolObject in symbolList:
                #if symbol is on the spot market and already trading
                if symbolObject['spot'] == True and symbolObject['info']['status'] == 'ENABLED':
                    trading_pairs.append(symbolObject['info']['symbol'])           
                    if symbolObject['info']['baseAsset'] not in tokens:
                        tokens.append(symbolObject['info']['baseAsset'])
            safe_list['Symbols'] = tokens
            safe_list['Pairs'] = trading_pairs
            logger.info("Market successfully retrieved from MEXC!")  

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
                old_symbol_dict = queryCEXMEXC()
                n = n+1
            except Exception:
                time.sleep(2)
                continue
        else:

            new_symbol_dict = queryCEXMEXC()
            
            for symbol in new_symbol_dict['Symbols']:
                if symbol not in old_symbol_dict['Symbols']:
                    symbol_to_trade = symbol
                    old_symbol_dict['Symbols'].append(symbol_to_trade)
            for pair in new_symbol_dict['Pairs']:
                if pair not in old_symbol_dict['Pairs']:
                    if pair != None or type(pair) != None:
                        pair_to_trade = pair
                        pairs_to_trade.append(pair_to_trade)
                        old_symbol_dict['Pairs'].append(pair)
                        logger.info("New Pair found. Adding to list of tradeable pairs!")
                    else:
                        continue
            
            if len(pairs_to_trade) > 0:
                logger.info('{} pair(s) available to trade!'.format(len(pairs_to_trade)))
                filtered_pairs = filterPairs(client,pairs_to_trade)
                account_balance = getAccountBalance(client,"USDT")
                try:
                    funds = allocateFunds(filtered_pairs,account_balance)
                except Exception:
                    logger.info("Can't allocate funds to tradeable pair")

                for trade_signal in filtered_pairs:
                    symbolDetail = getSymbolDetail(client,trade_signal)
                    baseCurr = symbolDetail['baseAsset']
                    #logger.info ("baseAsset: {}".format(baseCurr))
                    quoteCurr = symbolDetail['quoteAsset']
                    #logger.info ("quoteAsset: {}".format(quoteCurr))
                    qsize = funds[trade_signal]

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
                        "qsize":        qsize
                    })
                    logger.info("Potential trades: {}".format(potential_trades))
                    dump(potential_trades)

                    """if qsize > minSize_USDT and qsize < maxSize_USDT:
                        try:
                            logger.info("Trying to place an order on {}".format(trade_signal))
                            order = custom_market_buy_order(client,trade_signal,10)
                            try:
                                #check
                                orderId = order["orderId"]
                                if orderId:
                                    logger.info("Successfully opened a trade on {0} with order_id {1}".format(trade_signal,orderId))
                                    #check
                                    open_price = order['price']
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
                    
                    elif qsize > maxSize_USDT:
                        qsize = maxSize_USDT
                        try:
                            order = custom_market_buy_order(client,trade_signal,qsize)
                            try:
                                orderId = order["orderId"]
                                if orderId:
                                    logger.info("Successfully opened a trade on {0} with order_id {1}".format(trade_signal,orderId))
                                    #check
                                    open_price = order['price']
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

                        """
            else:
                logger.debug("No new pair(s) found")
            """               
            for trade in monitoring: 
                logger.info("Checking pairs in the monitoring list")    
                symbolDetail = getSymbolDetail(client,trade['symbol'])    
                baseCurr = symbolDetail['baseAsset']
                prec = symbolDetail['baseAssetPrecision']
                current_price = client.fetchTicker(trade_signal)['info']['lastPrice']
                account_balance = getAccountBalance(client,baseCurr)
                #target price is 20% greater than the opening price.
                target_price = trade["openPrice"] + (0.2 * trade["openPrice"])
                #At the moment, stop_loss is 20% lower than the opening price
                stop_loss = trade["openPrice"] - (0.2 * trade["openPrice"])
                size = round(account_balance,prec)
                logger.info("size to sell: {}".format(size))

                if current_price >= target_price:
                    custom_market_sell_order(client,trade["symbol"],size)
                    logger.info("Pair {} succesfully closed with a 20% gain".format(trade["symbol"]))
                    monitoring.remove(trade)
                if current_price <= stop_loss:
                    custom_market_sell_order(client,trade["symbol"],size)
                    logger.info("{} was stopped out with a 20% loss".format(trade["symbol"]))
                    monitoring.remove(trade)
            """

        time.sleep(1)

if __name__ == "__main__":
    main()