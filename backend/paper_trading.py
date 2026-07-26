"""
backend/paper_trading.py — Paper trading engine.

Provides endpoints to:
- Place simulated long/short orders
- Track open positions
- Close positions
- View order history
- Get equity curve
- Get portfolio summary
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from supabase import Client

from .main import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(tags=["paper_trading"])

INITIAL_CAPITAL = 100_000.0  # $100k paper account

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class PlaceOrderRequest(BaseModel):
    symbol: str
    side: str = Field(..., pattern=r"^(long|short)$")
    quantity: float = Field(..., gt=0)
    order_type: str = Field("market", pattern=r"^(market|limit|stop)$")
    price: float | None = None  # for limit/stop orders
    stop_price: float | None = None
    notes: str | None = None


class ClosePositionRequest(BaseModel):
    symbol: str
    side: str = Field(..., pattern=r"^(long|short)$")
    quantity: float | None = None  # None = close full position


class PositionResponse(BaseModel):
    id: int
    symbol: str
    side: str
    quantity: float
    entry_price: float
    current_price: float | None
    unrealized_pnl: float | None
    realized_pnl: float
    opened_at: str
    market_value: float | None


class PortfolioSummary(BaseModel):
    cash: float
    total_equity: float
    margin_used: float
    open_positions: int
    total_realized_pnl: float
    total_unrealized_pnl: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_current_price(supabase: Client, symbol: str) -> float | None:
    """Fetch the latest known price from crypto_data."""
    try:
        resp = (
            supabase.table("crypto_data")
            .select("current_price")
            .eq("symbol", symbol)
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        if resp.data and len(resp.data) > 0:
            return float(resp.data[0]["current_price"])
    except Exception:
        pass
    return None


def _get_equity(supabase: Client) -> PortfolioSummary:
    """Calculate current portfolio summary."""
    try:
        positions_resp = (
            supabase.table("paper_positions")
            .select("*")
            .execute()
        )
    except Exception:
        positions_resp = type("R", (), {"data": []})()

    positions = positions_resp.data or []
    total_unrealized = 0.0
    total_realized = 0.0
    margin_used = 0.0

    for pos in positions:
        total_realized += float(pos.get("realized_pnl", 0))
        if pos.get("unrealized_pnl") is not None:
            total_unrealized += float(pos["unrealized_pnl"])
        if pos.get("entry_price") and pos.get("quantity"):
            margin_used += float(pos["entry_price"]) * abs(float(pos["quantity"])) * 0.5  # 50% margin

    # Get cash balance from equity curve (latest)
    cash = INITIAL_CAPITAL
    try:
        cash_resp = (
            supabase.table("paper_equity_curve")
            .select("cash")
            .order("timestamp", desc=True)
            .limit(1)
            .execute()
        )
        if cash_resp.data and len(cash_resp.data) > 0:
            cash = float(cash_resp.data[0]["cash"])
    except Exception:
        pass

    total_equity = cash + total_unrealized

    return PortfolioSummary(
        cash=cash,
        total_equity=total_equity,
        margin_used=margin_used,
        open_positions=len(positions),
        total_realized_pnl=total_realized,
        total_unrealized_pnl=total_unrealized,
    )


def _snapshot_equity(supabase: Client):
    """Record an equity curve snapshot."""
    summary = _get_equity(supabase)
    try:
        supabase.table("paper_equity_curve").insert({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "equity": summary.total_equity,
            "cash": summary.cash,
            "margin_used": summary.margin_used,
        }).execute()
    except Exception as e:
        logger.warning(f"Failed to snapshot equity: {e}")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/paper/orders")
async def place_order(
    req: PlaceOrderRequest,
    supabase: Client = Depends(get_supabase),
):
    """Place a paper trade order."""
    # Get current price for market orders
    fill_price = req.price
    if req.order_type == "market":
        fill_price = _get_current_price(supabase, req.symbol)
        if fill_price is None:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot get current price for {req.symbol}. "
                "Run ETL first or provide a limit price.",
            )

    # Check if we already have an open position on this symbol+side
    try:
        existing = (
            supabase.table("paper_positions")
            .select("*")
            .eq("symbol", req.symbol)
            .eq("side", req.side)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    now_iso = datetime.now(timezone.utc).isoformat()

    if existing.data and len(existing.data) > 0:
        # Add to existing position
        pos = existing.data[0]
        pos_id = pos["id"]
        old_qty = float(pos["quantity"])
        old_entry = float(pos["entry_price"])

        # Weighted average entry price
        new_qty = old_qty + req.quantity
        avg_entry = ((old_entry * old_qty) + (fill_price * req.quantity)) / new_qty

        try:
            supabase.table("paper_positions").update({
                "quantity": new_qty,
                "entry_price": round(avg_entry, 4),
                "current_price": fill_price,
                "updated_at": now_iso,
            }).eq("id", pos_id).execute()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Update failed: {e}")
    else:
        # Create new position
        try:
            supabase.table("paper_positions").insert({
                "symbol": req.symbol,
                "side": req.side,
                "quantity": req.quantity,
                "entry_price": round(fill_price, 4),
                "current_price": fill_price,
                "unrealized_pnl": 0.0,
                "realized_pnl": 0.0,
                "opened_at": now_iso,
                "updated_at": now_iso,
                "metadata": {},
            }).execute()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Insert failed: {e}")

    # Record the order
    try:
        supabase.table("paper_orders").insert({
            "symbol": req.symbol,
            "side": req.side,
            "order_type": req.order_type,
            "quantity": req.quantity,
            "price": fill_price,
            "stop_price": req.stop_price,
            "status": "filled",
            "filled_at": now_iso,
            "notes": req.notes or "",
            "metadata": {},
        }).execute()
    except Exception as e:
        logger.warning(f"Order insert failed (non-fatal): {e}")

    _snapshot_equity(supabase)

    return {
        "status": "filled",
        "symbol": req.symbol,
        "side": req.side,
        "quantity": req.quantity,
        "fill_price": fill_price,
        "timestamp": now_iso,
    }


@router.post("/paper/close")
async def close_position(
    req: ClosePositionRequest,
    supabase: Client = Depends(get_supabase),
):
    """Close all or part of a paper position."""
    try:
        existing = (
            supabase.table("paper_positions")
            .select("*")
            .eq("symbol", req.symbol)
            .eq("side", req.side)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    if not existing.data or len(existing.data) == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No open {req.side} position for {req.symbol}",
        )

    pos = existing.data[0]
    pos_id = pos["id"]
    old_qty = float(pos["quantity"])
    entry_price = float(pos["entry_price"])
    current_price = _get_current_price(supabase, req.symbol)
    if current_price is None:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot get current price for {req.symbol}. Run ETL first.",
        )

    close_qty = req.quantity if req.quantity else old_qty
    close_qty = min(close_qty, old_qty)

    # Calculate P&L
    if req.side == "long":
        pnl = (current_price - entry_price) * close_qty
    else:
        pnl = (entry_price - current_price) * close_qty

    now_iso = datetime.now(timezone.utc).isoformat()

    if close_qty >= old_qty:
        # Close entire position
        try:
            supabase.table("paper_positions").delete().eq("id", pos_id).execute()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Delete failed: {e}")
    else:
        # Reduce position
        try:
            supabase.table("paper_positions").update({
                "quantity": old_qty - close_qty,
                "current_price": current_price,
                "updated_at": now_iso,
            }).eq("id", pos_id).execute()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Update failed: {e}")

    # Record the closing order
    try:
        supabase.table("paper_orders").insert({
            "symbol": req.symbol,
            "side": req.side,
            "order_type": "market",
            "quantity": close_qty,
            "price": current_price,
            "status": "filled",
            "filled_at": now_iso,
            "pnl": round(pnl, 2),
            "metadata": {"action": "close"},
        }).execute()
    except Exception as e:
        logger.warning(f"Close order insert failed (non-fatal): {e}")

    _snapshot_equity(supabase)

    return {
        "status": "closed",
        "symbol": req.symbol,
        "side": req.side,
        "quantity_closed": close_qty,
        "fill_price": current_price,
        "realized_pnl": round(pnl, 2),
        "timestamp": now_iso,
    }


@router.get("/paper/positions")
async def get_positions(
    supabase: Client = Depends(get_supabase),
):
    """Get all open paper trading positions with current P&L."""
    try:
        resp = supabase.table("paper_positions").select("*").execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    positions = []
    for pos in resp.data or []:
        current = _get_current_price(supabase, pos["symbol"])
        entry = float(pos["entry_price"])
        qty = abs(float(pos["quantity"]))

        if pos["side"] == "long":
            unrealized = (current - entry) * qty if current else None
        else:
            unrealized = (entry - current) * qty if current else None

        market_value = (current or 0) * qty if current else None

        positions.append(PositionResponse(
            id=pos["id"],
            symbol=pos["symbol"],
            side=pos["side"],
            quantity=abs(float(pos["quantity"])),
            entry_price=entry,
            current_price=current,
            unrealized_pnl=round(unrealized, 2) if unrealized is not None else None,
            realized_pnl=float(pos.get("realized_pnl", 0)),
            opened_at=pos["opened_at"],
            market_value=round(market_value, 2) if market_value else None,
        ))

    # Update unrealized P&L in the database
    for pos in resp.data or []:
        current = _get_current_price(supabase, pos["symbol"])
        if current is None:
            continue
        entry = float(pos["entry_price"])
        qty = abs(float(pos["quantity"]))
        if pos["side"] == "long":
            upnl = (current - entry) * qty
        else:
            upnl = (entry - current) * qty
        try:
            supabase.table("paper_positions").update({
                "current_price": current,
                "unrealized_pnl": round(upnl, 2),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", pos["id"]).execute()
        except Exception:
            pass

    return {"positions": positions}


@router.get("/paper/orders")
async def get_order_history(
    symbol: str | None = Query(None),
    limit: int = Query(50, le=200),
    supabase: Client = Depends(get_supabase),
):
    """Get paper trading order history."""
    try:
        query = (
            supabase.table("paper_orders")
            .select("*")
            .order("opened_at", desc=True)
            .limit(limit)
        )
        if symbol:
            query = query.eq("symbol", symbol)
        resp = query.execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    return {"orders": resp.data or []}


@router.get("/paper/equity")
async def get_equity_curve(
    limit: int = Query(500, le=2000),
    supabase: Client = Depends(get_supabase),
):
    """Get portfolio equity curve history."""
    try:
        resp = (
            supabase.table("paper_equity_curve")
            .select("*")
            .order("timestamp", desc=True)
            .limit(limit)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    curve = sorted(resp.data or [], key=lambda r: r["timestamp"])
    return {
        "initial_capital": INITIAL_CAPITAL,
        "equity_curve": curve,
    }


@router.get("/paper/portfolio")
async def get_portfolio(
    supabase: Client = Depends(get_supabase),
):
    """Get portfolio summary."""
    return _get_equity(supabase)


@router.post("/paper/reset")
async def reset_account(
    supabase: Client = Depends(get_supabase),
):
    """Reset paper trading account — clear all positions, orders, and equity curve."""
    try:
        supabase.table("paper_positions").delete().neq("id", 0).execute()
        supabase.table("paper_orders").delete().neq("id", 0).execute()
        supabase.table("paper_equity_curve").delete().neq("id", 0).execute()

        # Record initial equity snapshot
        supabase.table("paper_equity_curve").insert({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "equity": INITIAL_CAPITAL,
            "cash": INITIAL_CAPITAL,
            "margin_used": 0,
        }).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reset failed: {e}")

    return {
        "status": "reset",
        "initial_capital": INITIAL_CAPITAL,
        "message": "Paper trading account reset to initial state.",
    }
