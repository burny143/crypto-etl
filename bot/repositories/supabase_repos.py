"""Supabase-backed persistence for orders, positions, and equity curve."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from supabase import Client

from bot.domain.models import (
    OrderStatus,
    PaperOrder,
    PaperPosition,
    PortfolioSnapshot,
    Side,
    Symbol,
)
from bot.domain.utc import to_decimal


class SupabaseOrderRepository:
    """Persists ``PaperOrder`` records to the ``paper_orders`` table."""

    def __init__(self, client: Client) -> None:
        self._client = client

    def save(self, order: PaperOrder) -> PaperOrder:
        """Insert or update an order record."""
        payload = self._to_row(order)
        if order.id is None:
            resp = self._client.table("paper_orders").insert(payload).execute()
            if resp.data and len(resp.data) > 0:
                order.id = resp.data[0].get("id")
        else:
            self._client.table("paper_orders").update(payload).eq("id", order.id).execute()
        return order

    def find_by_key(self, decision_key: str) -> PaperOrder | None:
        resp = (
            self._client.table("paper_orders")
            .select("*")
            .eq("decision_key", decision_key)
            .limit(1)
            .execute()
        )
        if not resp.data or len(resp.data) == 0:
            return None
        return self._from_row(resp.data[0])

    def find_by_symbol(self, symbol: Symbol) -> list[PaperOrder]:
        resp = (
            self._client.table("paper_orders")
            .select("*")
            .eq("symbol", symbol)
            .order("opened_at", desc=True)
            .execute()
        )
        return [self._from_row(r) for r in (resp.data or [])]

    def all(self) -> list[PaperOrder]:
        tbl = self._client.table("paper_orders")
        resp = tbl.select("*").order("opened_at", desc=True).execute()
        return [self._from_row(r) for r in (resp.data or [])]

    # ------------------------------------------------------------------
    # Row mapping
    # ------------------------------------------------------------------

    def _to_row(self, order: PaperOrder) -> dict:
        return {
            "symbol": order.symbol,
            "side": order.side.value,
            "quantity": float(order.quantity),
            "order_type": order.order_type,
            "price": float(order.price) if order.price else None,
            "status": order.status.value,
            "decision_key": order.decision_key,
            "strategy_id": order.strategy_id,
            "signal_timestamp": (
                order.signal_timestamp.isoformat()
                if order.signal_timestamp
                else None
            ),
            "reason": order.reason,
            "pnl": float(order.pnl) if order.pnl else None,
            "fee": float(order.fee) if order.fee else None,
        }

    def _from_row(self, row: dict) -> PaperOrder:
        return PaperOrder(
            symbol=Symbol(row["symbol"]),
            side=Side(row["side"]),
            quantity=Decimal(str(row["quantity"])),
            order_type=row.get("order_type", "market"),
            price=to_decimal(row.get("price")),
            status=OrderStatus(row.get("status", "filled")),
            decision_key=row.get("decision_key", ""),
            strategy_id=row.get("strategy_id", ""),
            signal_timestamp=_parse_ts(row.get("signal_timestamp")),
            reason=row.get("reason", ""),
            id=row.get("id"),
            opened_at=_parse_ts(row.get("opened_at")),
            filled_at=_parse_ts(row.get("filled_at")),
            closed_at=_parse_ts(row.get("closed_at")),
            fee=to_decimal(row.get("fee")),
            pnl=to_decimal(row.get("pnl")),
        )


class SupabasePositionRepository:
    """Persists ``PaperPosition`` records to the ``paper_positions`` table."""

    def __init__(self, client: Client) -> None:
        self._client = client

    def save(self, position: PaperPosition) -> PaperPosition:
        """Upsert a position record."""
        payload = self._to_row(position)
        resp = self._client.table("paper_positions").upsert(payload).execute()
        if resp.data and len(resp.data) > 0 and position.id is None:
            position.id = resp.data[0].get("id")
        return position

    def find_open(self, symbol: Symbol, side: Side) -> PaperPosition | None:
        resp = (
            self._client.table("paper_positions")
            .select("*")
            .eq("symbol", symbol)
            .eq("side", side.value)
            .eq("status", "open")
            .limit(1)
            .execute()
        )
        if not resp.data or len(resp.data) == 0:
            return None
        return self._from_row(resp.data[0])

    def all_open(self) -> list[PaperPosition]:
        resp = self._client.table("paper_positions").select("*").eq("status", "open").execute()
        return [self._from_row(r) for r in (resp.data or [])]

    def delete(self, symbol: Symbol, side: Side) -> None:
        self._client.table("paper_positions").update({"status": "closed"}).eq("symbol", symbol).eq(
            "side", side.value
        ).execute()

    # ------------------------------------------------------------------
    # Row mapping
    # ------------------------------------------------------------------

    def _to_row(self, pos: PaperPosition) -> dict:
        return {
            "symbol": pos.symbol,
            "side": pos.side.value,
            "quantity": float(pos.quantity),
            "entry_price": float(pos.entry_price),
            "strategy_id": pos.strategy_id,
            "current_price": float(pos.current_price) if pos.current_price else None,
            "unrealized_pnl": float(pos.unrealized_pnl) if pos.unrealized_pnl else None,
            "realized_pnl": float(pos.realized_pnl),
            "status": "open",
        }

    def _from_row(self, row: dict) -> PaperPosition:
        return PaperPosition(
            symbol=Symbol(row["symbol"]),
            side=Side(row["side"]),
            quantity=Decimal(str(row["quantity"])),
            entry_price=Decimal(str(row["entry_price"])),
            strategy_id=row.get("strategy_id", ""),
            id=row.get("id"),
            opened_at=_parse_ts(row.get("opened_at")),
            current_price=to_decimal(row.get("current_price")),
            unrealized_pnl=to_decimal(row.get("unrealized_pnl")),
            realized_pnl=Decimal(str(row.get("realized_pnl", "0"))),
        )


def _parse_ts(value: object) -> datetime | None:
    """Parse a Supabase timestamp into a UTC-aware datetime."""
    from datetime import datetime

    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


class SupabaseEquityCurveRepository:
    """Persists ``PortfolioSnapshot`` records to the ``paper_equity_curve`` table."""

    def __init__(self, client: Client) -> None:
        self._client = client

    def save(self, snapshot: PortfolioSnapshot) -> PortfolioSnapshot:
        """Insert an equity curve snapshot."""
        payload = {
            "timestamp": snapshot.timestamp.isoformat(),
            "equity": float(snapshot.equity),
            "cash": float(snapshot.cash),
            "margin_used": float(snapshot.margin_used),
        }
        resp = self._client.table("paper_equity_curve").insert(payload).execute()
        if resp.data and len(resp.data) > 0:
            snapshot.id = resp.data[0].get("id")
        return snapshot

    def all(self) -> list[PortfolioSnapshot]:
        resp = (
            self._client.table("paper_equity_curve")
            .select("*")
            .order("timestamp", desc=True)
            .execute()
        )
        return [self._from_row(r) for r in (resp.data or [])]

    def _from_row(self, row: dict) -> PortfolioSnapshot:
        return PortfolioSnapshot(
            timestamp=_parse_ts(row["timestamp"]),
            equity=Decimal(str(row["equity"])),
            cash=Decimal(str(row["cash"])),
            margin_used=Decimal(str(row.get("margin_used", "0"))),
        )
