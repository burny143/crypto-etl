# Persistence adapters (in-memory default + Supabase).
from bot.repositories.memory import (
    InMemoryOrderRepository,
    InMemoryPositionRepository,
)
from bot.repositories.signal import (
    InMemorySignalRepository,
    SignalRepository,
    SupabaseSignalRepository,
)
from bot.repositories.supabase_repos import (
    SupabaseOrderRepository,
    SupabasePositionRepository,
)

__all__ = [
    "InMemoryOrderRepository",
    "InMemoryPositionRepository",
    "InMemorySignalRepository",
    "SignalRepository",
    "SupabaseSignalRepository",
    "SupabaseOrderRepository",
    "SupabasePositionRepository",
]
