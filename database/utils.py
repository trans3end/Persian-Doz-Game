"""Tiny dependency-free helpers used by both the repository layer and the
game engine (kept separate from repository.py so game/engine.py doesn't
need to import aiosqlite just to generate a game id)."""
from __future__ import annotations

import secrets
import string
import time
import uuid

_ALPHABET = string.ascii_uppercase + string.digits


def generate_code(length: int = 8) -> str:
    """Generates a short, URL-safe referral code, e.g. 'IB4P2OF6'."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def new_game_id() -> str:
    return str(uuid.uuid4())


def now_ms() -> int:
    return int(time.time() * 1000)
