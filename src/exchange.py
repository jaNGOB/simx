"""
Here we define the exchange object. Within it, we have the logic for: 
- Positions & balances
- Open Orders 
- Add, delete, modify orders 
- Execute Orders (Limit and Market)
- Spot (Base, Quote balances)
- Modify Orders

TODO: 
- Delete Orders 
- Add Futures support

"""
from typing import List, Literal, Optional
import numpy as np
from collections import deque
from sortedcontainers import SortedDict
from .matching_engine import OrderBook
from .data_types import TOB, Order, Trade, ModifyOrder


class Exchange:
    def __init__(self, fees: List[int] = [0, 2]):
        self.maker_fee = fees[0]
        self.taker_fee = fees[1]
        self.balance = {}

        self.market = {}
        self.market_mapping = {}

        self.positions = {}
        self.open_orders = {}
        self.trades = SortedDict()

    def add_market(self, symbol: str, base: str, quote: str):
        self.market_mapping[symbol] = [base, quote]

    def add_balance(self, symbol: str, amount: float):
        self.balance[symbol] = amount

    def top_of_book(self, symbol):
        tb = self.markets[symbol].bp
        ta = self.markets[symbol].ap
        print(f"Bid: {tb} | {ta} :Ask")
        return [tb, ta]

    def _open_orders(self):
        return True if len(self.open_orders) > 0 else False

    def open_position(self, order: Order, timestamp: int) -> None:
        """
        Order went through and can be opened on the exchange.

        We update the base and quote balance in this example of a spot exchange.


        """
        new_trade = Trade(
            order.order_id,
            order.side,
            order.taker,
            order.amount,
            order.price,
            order.entryTime,
            timestamp,
        )
        print("Position Opened", new_trade)

        order.eventTime = timestamp

        # Update the base currency balance. Here we take the amount (in base) and multiply it by the side.
        # This means that
        self.balance[self.market_mapping[order.symbol][0]] += order.amount * order.side
        self.balance[
            self.market_mapping[order.symbol][1]
        ] -= order.amount * order.price + abs(
            order.amount * order.price * self.taker_fee
        ) * (
            -1 * order.side
        )
        # self.positions[order.symbol] = order.amount

        self.trades[timestamp] = new_trade

    def close_position(self, symbol: str, price: float):
        print("Position Closed")
        self.balance += self.positions[symbol] * price - abs(
            self.positions[symbol] * price * self.taker_fee
        )
        self.positions.pop(symbol)


class OHLCExchange(Exchange):
    def __init__(self, initial_balance: int = 10000, fees: List[int] = [0, 2]):
        super().__init__(initial_balance, fees)


class TickExchange(Exchange):
    def __init__(self, initial_balance: int = 10000, fees: List[int] = [0, 2]):
        super().__init__(initial_balance, fees)

        self.orderbook: OrderBook = OrderBook()


class TOB_Exchange(Exchange):
    def __init__(
        self, initial_balance: int = 10000, fees: List[int] = [0, 2], latency=[200, 15]
    ):
        super().__init__(initial_balance, fees)

        self.events = {}
        self.latency_mean = latency[0]
        self.latency_dev = latency[1]

    def _add_latency(self, timestamp: int):
        timestamp += np.random.lognormal(0, self.latency_dev, 1) * self.latency_mean
        return timestamp

    def overview(self, symbol: str) -> None:
        print(f"Bid: {self.markets[symbol].bp:>8} | {self.markets[symbol].ap:>8} :Ask")

        print("Open Buy Orders")
        for i in self.open_orders["COMPBTC"][1]:
            print(f"{i} @ {self.open_orders['COMPBTC'][1][i].amount}")

        print("Open Sell Orders")
        for i in self.open_orders["COMPBTC"][0]:
            print(f"{i} @ {self.open_orders['COMPBTC'][0][i].amount}")

    def load_trades(self, symbol: str, trades: List[float]) -> None:
        self.trades[symbol] = trades

    def load_tob(self, tob_updates: List[float], symbol: str) -> None:
        # Initialize a orders queue
        self.open_orders[symbol] = {}
        self.open_orders[symbol][1] = SortedDict()
        self.open_orders[symbol][0] = SortedDict()

        # Set initial Orderbook as the start
        tob = tob_updates[0]
        self.markets[symbol] = TOB(
            symbol=symbol, timestamp=tob[0], bq=tob[1], bp=tob[2], ap=tob[3], aq=tob[4]
        )
        # The rest will be taken apart and used as events for the backtester
        # self._process_tob_updates(tob_updates[1:])

        # Open a event queue for the symbol
        self.events = SortedDict()

        # Add all the TOB Updates to the queue
        for i in tob_updates[1:]:
            if i[0] not in self.events.keys():
                self.events[i[0]] = deque()

            self.events[i[0]].append(
                TOB(symbol=symbol, timestamp=i[0], bq=i[1], bp=i[2], ap=i[3], aq=i[4])
            )

    def market_order(self, symbol: str, amount: float, side: bool) -> None:
        """

        :param symbol: (str) Symbol of the traded pair
        :param amount: (float) Amount in base currency that will be traded
        :param side: (bool) 1 if its a buy, 0 if its a sell.

        :return: None
        """
        # Add latency to the timestamp of the last TOB update
        timestamp = self._add_latency(self.markets[symbol].timestamp)

        # If there is already an event in the queue at that time, add it at the end
        if timestamp not in self.events.keys():
            self.events[timestamp] = deque()

        self.events[timestamp].append(
            Order(
                symbol=symbol,
                side=side,
                taker=True,
                price=None,
                amount=amount,
                entryTime=timestamp,
            )
        )

    def limit_order(self, symbol: str, amount: float, price: float, side: bool) -> None:
        """
        Function that adds an order to the events queue. First there is some added
        Latency that can be defined in the initiation of the exchange object itself.
        Then we add it to the queue of the relevant timestamp or open a new queue if we
        dont have a step yet at that time.

        :param symbol: (str) Symbol of the traded pair
        :param amount: (float) Amount in base currency that will be traded
        :param price: (float) Price of the order.
        :param side: (bool) 1 if its a buy, 0 if its a sell.

        :return: None
        """
        # Add latency to the timestamp of the last TOB update
        timestamp = self._add_latency(self.markets[symbol].timestamp)

        # If there is already an event in the queue at that time, add it at the end
        if timestamp not in self.events.keys():
            self.events[timestamp] = deque()

        self.events[timestamp].append(
            Order(
                symbol=symbol,
                side=side,
                taker=False,
                amount=amount,
                price=price,
                entryTime=timestamp,
            )
        )

    def _execute_modification(self, order: ModifyOrder) -> None:
        """
        function that finds the order by the order_id and replaces it by the new that is sent.
        The order_id is not updated so we can just look for it directly.

        :param order: (Order)
        """
        orders = self.open_orders[order.symbol][order.side]

        # look for a match and update the new price and amounts
        for o in orders:
            if o.order_id == order.order_id:
                o.price = order.new_price
                o.amount = order.new_amount

    def modify_order(
        self,
        order: Order,
        price: Optional[float] = None,
        amount: Optional[float] = None,
    ):
        """
        To modify an order, we first open a modification message and assign it.
        Next we check if we received instructions to change the price or amount and add the information where necessary
        Finally we add some latency and append it to the events queue.
        """

        new_order = ModifyOrder(order=order)

        # If there is a change in price, add the information to the new_order
        if price != None:
            new_order.new_price = price
        # If there are no changes, keep the old price
        else:
            new_order.new_price = order.price

        # If there is a change in amount, add the information to the new_order
        if amount != None:
            new_order.new_amount = amount

        else:
            new_order.new_amount = order.amount

        timestamp = self._add_latency(self.markets[order.symbol].timestamp)

        # If there is already an event in the queue at that time, add it at the end
        if timestamp not in self.events.keys():
            self.events[timestamp] = deque()

        self.events[timestamp].append(new_order)

    def _execute_market(self, event: Order) -> None:
        price = (
            self.markets[event.symbol].ap
            if event.side
            else self.markets[event.symbol].bp
        )

        event.price = price
        self.open_position(order=event, timestamp=event.entryTime)

    def _check_match(self, symbol: str, timestamp: int):
        # If there is a buy order and the price is above the current ask price, we execute it
        if len(self.open_orders[symbol][1]) > 0:
            while (
                self.markets[symbol].ap
                <= self.open_orders[symbol][1].peekitem(-1)[1].price
            ):
                order = self.open_orders[symbol][1].popitem(0)
                # If the price moved in the meantime which leads to direct execution, it was a taker
                if order[1].timestamp == timestamp:
                    order[1].taker = True

                self.open_position(order=order[1], timestamp=timestamp)

                if len(self.open_orders[symbol][1]) == 0:
                    break

        # If there is a sell order and the price is lower than the current best bid, we execute it
        if len(self.open_orders[symbol][0]) > 0:
            while (
                self.markets[symbol].bp
                >= self.open_orders[symbol][0].peekitem(0)[1].price
            ):
                order = self.open_orders[symbol][0].popitem(-1)
                # If the price moved in the meantime which leads to direct execution, it was a taker
                if order[1].timestamp == timestamp:
                    order[1].taker = True

                self.open_position(order=order[1], timestamp=timestamp)

                if len(self.open_orders[symbol][0]) == 0:
                    break

    def _simulation_step(self):
        # Select the current event and remove it from the Queue
        ts = self.events.peekitem(0)[0]
        event = self.events.peekitem(0)[1].popleft()

        ##############################
        ### Could be done by switch ##
        ##############################

        # If the update is a new TOB, change it
        if type(event) == TOB:
            self.markets[event.symbol] = TOB(
                symbol=event.symbol,
                timestamp=ts,
                bq=event.bq,
                bp=event.bp,
                ap=event.ap,
                aq=event.aq,
            )
        # If the update is an order, execute the order
        elif type(event) == Order:
            # If its a market order, execute directly
            if event.taker:
                self._execute_market(event)
            # If its a limit order, put it into the open orders that wait for execution
            else:
                self.open_orders[event.symbol][event.side][event.price] = event

        # If the event is a modification, change the order in question.
        elif type(event) == ModifyOrder:
            self._execute_modification(event)

        # Remove the event timestamp if there are no more in the queue at that time
        if len(self.events.peekitem(0)[1]) == 0:
            self.events.popitem(0)

        # Finally, check for a match in the current pair
        # event.symbol exists in all possible updates so we can safely call it
        self._check_match(event.symbol, ts)
        # self.overview(event.symbol)

    def run_simulation(self, strategy):
        while len(self.events) > 0:
            strategy(self.markets, self.open_orders, self.balance)
            self._simulation_step()
