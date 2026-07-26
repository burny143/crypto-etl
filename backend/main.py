"""
backend/main.py — FastAPI application for the Unified Crypto Research Frontend.

Provides endpoints for:
- Technical indicator computation (server-side, cached in Supabase)
- Paper trading (orders, positions, P&L)
- AI research integration points (extensible for LLM-based analysis)
- OHLCV data queries (primarily served directly from Supabase to frontend)

Run:
    uvicorn main:app --reload --port 8765
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .indicators import router as indicators_router
from .paper_trading import router as paper_trading_router
from .research import router as research_router
from .signals import router as signals_router

load_dotenv()

# ---------------------------------------------------------------------------
# Supabase client (shared by all sub-modules)
# ---------------------------------------------------------------------------
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    raise RuntimeError(
        "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in environment"
    )


def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Store supabase client on app state for dependency injection."""
    app.state.supabase = get_supabase()
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Crypto Research Backend",
    version="0.2.0",
    description="Backend API for the unified crypto research + trading dashboard",
    lifespan=lifespan,
)

# CORS — allow the frontend dev server
cors_origins = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:5173,http://localhost:3000,http://localhost:8000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Mount route modules
# ---------------------------------------------------------------------------
app.include_router(indicators_router, prefix="/api/v1")
app.include_router(paper_trading_router, prefix="/api/v1")
app.include_router(research_router, prefix="/api/v1")
app.include_router(signals_router, prefix="/api/v1")
