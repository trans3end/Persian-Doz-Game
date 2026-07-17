"""Game-state orchestration that doesn't need the database or Telegram —
constructing a fresh Game, and the reason-code mapping used across the
result/history messages. The actual move application lives in board.py;
this module wires it together into the `Game` dataclass used elsewhere.
"""
from __future__ import annotations

import time

from database.models import Game, Player
from database.utils import new_game_id
from game.board import create_empty_board

REASON_KEYS = {
    "connect4": "reasonConnect4",
    "draw": "reasonDraw",
    "resign": "reasonResign",
    "timeout": "reasonTimeout",
    "leave": "reasonLeave",
}


def now_ms() -> int:
    return int(time.time() * 1000)


def new_two_player_game(player_a: Player, player_b: Player, mode: str) -> Game:
    """Mirrors startGame()'s game-object construction in handlers.js
    (the message-sending side of startGame lives in services/games.py).
    """
    player_a.symbol = 1
    player_a.message_id = None
    player_b.symbol = 2
    player_b.message_id = None
    now = now_ms()
    return Game(
        id=new_game_id(),
        mode=mode,  # "random" | "friend"
        board=create_empty_board(),
        turn=1,
        status="active",
        players=[player_a, player_b],
        move_count=0,
        turn_started_at=now,
        created_at=now,
    )


def new_group_waiting_game(host: Player) -> Game:
    """Mirrors startGroupWaitingGame()'s game-object construction."""
    host.symbol = 1
    now = now_ms()
    return Game(
        id=new_game_id(),
        mode="group",
        board=create_empty_board(),
        turn=1,
        status="waiting",
        players=[host],
        move_count=0,
        turn_started_at=now,
        created_at=now,
    )
