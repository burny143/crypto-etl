#!/usr/bin/env python3
"""
Mock Exchange Implementation

Implements a CCXT-compatible interface for synthetic market generation
and testing without requiring actual exchange connections.

Key Features:
- Simulated order book with bid/ask spread and slippage
- Balance tracking for USDT and FRED tokens
- Support for limit and market orders
- CCXT-compatible API methods
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any
from collections import defaultdict

from bot.domain.models import Side, Signal


class OrderType(str, Enum):
    """Order types supported by the mock exchange."""
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, Enum):
    """Order status states."""
    OPEN = "open"
    FILLED = "filled"
    CANCELED = "canceled"


@dataclass
class Order:
    """Represents a trading order."""
    id: str
    client_order_id: Optional[str] = None
    symbol: str
    type: OrderType
    side: Side
    amount: Decimal
    price: Decimal
    avg_price: Decimal = Decimal("0")
    status: OrderStatus = OrderStatus.OPEN
    timestamp: datetime
    update_time: datetime
    fee: Decimal = Decimal("0")
    fee_currency: Optional[str] = None
    trades: List[Dict[str, Any]] = field(default_factory=list)
    stop_price: Optional[Decimal] = None
    take_profit_price: Optional[Decimal] = None
    stop_loss_price: Optional[Decimal] = None

    @property
    def filled(self) -> bool:
        return self.status == OrderStatus.FILLED


@dataclass
class Balance:
    """Account balance information."""
    free: Decimal
    used: Decimal
    total: Decimal

    def __init__(self, free: Decimal = Decimal("0"), used: Decimal = Decimal("0")):
        self.free = free
        self.used = used
        self.total = free + used


class MockExchange:
    """
    CCXT-compatible mock exchange for synthetic market testing.

    Features:
    - Simulated order book with spread and slippage
    - Balance tracking for USDT and FRED tokens
    - Support for market and limit orders
    - Real-time price generation based on synthetic market data
    """

    def __init__(self):
        # Balance tracking
        self._balances: Dict[str, Balance] = {
            "USDT": Balance(free=Decimal("10000.0")),  # Starting balance
            "FRED": Balance(free=Decimal("100000.0")),  # Starting FRED tokens
        }

        # Order book: symbol -> list of orders
        self._order_book: Dict[str, List[Order]] = defaultdict(list)

        # Current price information
        self._tickers: Dict[str, Dict[str, Any]] = {}

        # Track active orders for each symbol
        self._active_orders: Dict[str, List[Order]] = defaultdict(list)

        # Fee rate (0.1% for both buying and selling)
        self.fee_rate = Decimal("0.001")

        # Slippage factor (for market orders)
        self.slippage_factor = Decimal("0.001")

    def __repr__(self) -> str:
        return f"<MockExchange USDT={self._balances['USDT'].total:.2f} FRED={self._balances['FRED'].total:.2f}>"

    # -------------------------------------------------------------------------
    # CCXT Compatibility Methods
    # -------------------------------------------------------------------------

    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch ticker information for a symbol.

        Args:
            symbol: Trading pair (e.g., "FRED/USDT")

        Returns:
            Ticker information with price, volume, and spread.
        """
        self._update_ticker(symbol)
        return self._tickers.get(symbol, {})

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1d", since: Optional[int] = None,
                    limit: Optional[int] = None, params: Optional[Dict] = None) -> List[List]:
        """
        Fetch OHLCV data for a symbol.

        For mock exchange, this returns empty data since price updates come
        from the synthetic market generator.

        Args:
            symbol: Trading pair
            timeframe: Timeframe (e.g., "1d")
            since: Start timestamp (ignored)
            limit: Maximum number of candles (ignored)
            params: Additional parameters (ignored)

        Returns:
            Empty list for mock exchange.
        """
        # Mock exchange doesn't generate historical OHLCV data
        # This would be populated by the synthetic market generator
        return []

    def create_market_buy_order(self, symbol: str, amount: Decimal, params: Optional[Dict] = None) -> Order:
        """
        Create a market buy order.

        Args:
            symbol: Trading pair
            amount: Amount to buy
            params: Additional parameters

        Returns:
            Created order
        """
        return self._create_order(symbol, "market", Side.LONG, amount, None, params)

    def create_market_sell_order(self, symbol: str, amount: Decimal, params: Optional[Dict] = None) -> Order:
        """
        Create a market sell order.

        Args:
            symbol: Trading pair
            amount: Amount to sell
            params: Additional parameters

        Returns:
            Created order
        """
        return self._create_order(symbol, "market", Side.SHORT, amount, None, params)

    def create_limit_buy_order(self, symbol: str, amount: Decimal, price: Decimal,
                              params: Optional[Dict] = None) -> Order:
        """
        Create a limit buy order.

        Args:
            symbol: Trading pair
            amount: Amount to buy
            price: Limit price
            params: Additional parameters

        Returns:
            Created order
        """
        return self._create_order(symbol, "limit", Side.LONG, amount, price, params)

    def create_limit_sell_order(self, symbol: str, amount: Decimal, price: Decimal,
                               params: Optional[Dict] = None) -> Order:
        """
        Create a limit sell order.

        Args:
            symbol: Trading pair
            amount: Amount to sell
            price: Limit price
            params: Additional parameters

        Returns:
            Created order
        """
        return self._create_order(symbol, "limit", Side.SHORT, amount, price, params)

    def fetch_balance(self) -> Dict[str, Balance]:
        """
        Fetch account balances.

        Returns:
            Dictionary of currency balances.
        """
        return self._balances.copy()

    def fetch_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """
        Fetch open orders.

        Args:
            symbol: Optional symbol to filter by

        Returns:
            List of open orders.
        """
        if symbol:
            return [order for order in self._active_orders.get(symbol, []) if order.status == OrderStatus.OPEN]
        return [order for orders in self._active_orders.values() for order in orders if order.status == OrderStatus.OPEN]

    def cancel_order(self, order_id: str, symbol: str) -> Order:
        """
        Cancel an order.

        Args:
            order_id: ID of the order to cancel
            symbol: Trading pair

        Returns:
            The canceled order
        """
        orders = self._active_orders.get(symbol, [])
        for order in orders:
            if order.id == order_id and order.status == OrderStatus.OPEN:
                order.status = OrderStatus.CANCELED
                return order
        raise ValueError(f"Order {order_id} not found or already executed")

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _create_order(self, symbol: str, order_type: str, side: Side, amount: Decimal,
                     price: Optional[Decimal], params: Optional[Dict]) -> Order:
        """
        Create a new order and execute it immediately.

        Args:
            symbol: Trading pair
            order_type: Type of order ("market" or "limit")
            side: Order side (LONG or SHORT)
            amount: Order amount
            price: Order price (required for limit orders)
            params: Additional parameters

        Returns:
            Created order
        """
        # Generate unique order ID
        order_id = f"mock-order-{uuid.uuid4().hex[:8]}"
        timestamp = datetime.now(timezone.utc)

        # Determine execution price
        if order_type == "market":
            exec_price = self._get_market_price(symbol, side, amount)
        else:
            if price is None:
                raise ValueError("Price required for limit orders")
            exec_price = price

        # Calculate fees
        fee = amount * self.fee_rate

        # Create order
        order = Order(
            id=order_id,
            symbol=symbol,
            type=OrderType(order_type),
            side=side,
            amount=amount,
            price=price if order_type == "limit" else exec_price,
            avg_price=exec_price,
            status=OrderStatus.FILLED,
            timestamp=timestamp,
            update_time=timestamp,
            fee=fee,
            fee_currency="USDT" if side == Side.LONG else "FRED",
        )

        # Update balances
        self._update_balances(order, exec_price)

        # Add to active orders and order book
        self._active_orders[symbol].append(order)

        # Record trade
        trade = {
            "id": f"trade-{uuid.uuid4().hex[:8]}",
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "price": exec_price,
            "fee": fee,
            "timestamp": timestamp.timestamp() * 1000,
        }
        order.trades.append(trade)

        # Update ticker
        self._update_ticker(symbol)

        return order

    def _get_market_price(self, symbol: str, side: Side, amount: Decimal) -> Decimal:
        """
        Get market price for a given amount, considering slippage.

        Args:
            symbol: Trading pair
            side: Order side
            amount: Order amount

        Returns:
            Execution price after slippage
        """
        ticker = self._get_base_ticker(symbol)
        if not ticker:
            raise ValueError(f"No ticker available for {symbol}")

        # Base price from ticker
        base_price = Decimal(str(ticker["last"]))

        # Calculate slippage
        slippage = min(self.slippage_factor * Decimal(str(abs(float(amount)))), Decimal("0.01"))

        # Apply slippage based on order side
        if side == Side.LONG:
            # Buying: price increases with slippage
            return base_price * (Decimal("1") + slippage)
        else:
            # Selling: price decreases with slippage
            return base_price * (Decimal("1") - slippage)

    def _get_base_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Get base ticker information for a symbol.

        Args:
            symbol: Trading pair

        Returns:
            Ticker information.
        """
        # If ticker doesn't exist, create a default one
        if symbol not in self._tickers:
            self._tickers[symbol] = {
                "symbol": symbol,
                "last": "100.0",  # Default base price
                "bid": "99.5",
                "ask": "100.5",
                "volume": "0",
                "timestamp": datetime.now(timezone.utc).timestamp() * 1000,
                "datetime": datetime.now(timezone.utc).isoformat(),
            }
        return self._tickers[symbol]

    def _update_ticker(self, symbol: str) -> None:
        """
        Update ticker information based on current order book.

        Args:
            symbol: Trading pair
        """
        # Get all filled orders for this symbol
        filled_orders = [o for o in self._active_orders.get(symbol, []) if o.status == OrderStatus.FILLED]

        if not filled_orders:
            # No trades yet, use default
            self._tickers[symbol] = {
                "symbol": symbol,
                "last": "100.0",
                "bid": "99.5",
                "ask": "100.5",
                "volume": "0",
                "timestamp": datetime.now(timezone.utc).timestamp() * 1000,
                "datetime": datetime.now(timezone.utc).isoformat(),
            }
            return

        # Calculate weighted average price from filled orders
        total_value = Decimal("0")
        total_volume = Decimal("0")

        for order in filled_orders:
            order_value = order.avg_price * order.amount
            total_value += order_value
            total_volume += order.amount

        if total_volume > 0:
            weighted_price = total_value / total_volume
        else:
            weighted_price = Decimal("100.0")

        # Set bid/ask with spread
        spread = Decimal("0.5")  # 0.5 USDT spread
        bid_price = weighted_price - spread
        ask_price = weighted_price + spread

        # Update volume (simplified: sum all trade amounts)
        total_volume_str = str(float(total_volume))

        self._tickers[symbol] = {
            "symbol": symbol,
            "last": str(float(weighted_price)),
            "bid": str(float(bid_price)),
            "ask": str(float(ask_price)),
            "volume": total_volume_str,
            "timestamp": datetime.now(timezone.utc).timestamp() * 1000,
            "datetime": datetime.now(timezone.utc).isoformat(),
        }

    def _update_balances(self, order: Order, execution_price: Decimal) -> None:
        """
        Update account balances after order execution.

        Args:
            order: Executed order
            execution_price: Price at which order was executed
        """
        order_value = order.amount * execution_price
        fee = order.fee

        if order.side == Side.LONG:
            # Buying: decrease USDT balance, increase FRED position
            usdt_balance = self._balances["USDT"]
            fred_balance = self._balances["FRED"]

            # Deduct USDT (amount + fee)
            total_cost = order_value + fee
            usdt_balance.free -= total_cost
            usdt_balance.used += total_cost

            # Receive FRED tokens
            fred_balance.free -= order.amount
            fred_balance.used += order.amount

        else:
            # Selling: increase USDT balance, decrease FRED position
            usdt_balance = self._balances["USDT"]
            fred_balance = self._balances["FRED"]

            # Receive USDT
            usdt_balance.free += order_value
            usdt_balance.used -= order_value

            # Pay FRED tokens (amount + fee)
            total_cost = order_amount = order.amount
            total_cost_fee = total_cost + fee
            fred_balance.free -= total_cost_fee
            fred_balance.used += total_cost_fee

        # Notify any listeners
        self._notify_listeners()

    def _notify_listeners(self) -> None:
        """Notify listeners of balance changes (placeholder)."""
        pass

    def reset(self) -> None:
        """Reset the exchange to initial state."""
        self._balances = {
            "USDT": Balance(free=Decimal("10000.0")),
            "FRED": Balance(free=Decimal("100000.0")),
        }
        self._order_book.clear()
        self._tickers.clear()
        self._active_orders.clear()


# Export the mock exchange for easy import
__all__ = ["MockExchange"]
