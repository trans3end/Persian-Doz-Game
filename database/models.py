"""Domain dataclasses.

These mirror the plain-object shapes used throughout the original
store.js / handlers.js (user rows, game state, settings, etc.), just
given proper types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

Mode = Literal["friend", "random", "group"]
GameStatus = Literal["waiting", "active", "finished"]
Result = Literal["win", "loss", "draw"]
EndReason = Literal["connect4", "draw", "resign", "timeout", "leave"]


@dataclass
class Settings:
    support_link: str = "https://t.me/PersianDozSupport"
    referral_bonus: int = 50
    signup_bonus: int = 500
    required_channel: str = ""

    @classmethod
    def defaults(cls) -> "Settings":
        return cls()


@dataclass
class User:
    id: int
    name: str
    username: Optional[str]
    username_visible: bool
    language: str
    score: int
    coins: int
    wins: int
    losses: int
    draws: int
    invites_count: int
    referral_code: Optional[str]
    referred_by: Optional[int]
    channel_verified_at: Optional[int]
    last_daily_claim_at: Optional[int]
    friends: list[int]
    created_at: int


@dataclass
class Player:
    """One side of an in-progress game."""

    id: int
    name: str
    lang: str
    chat_id: int
    symbol: int  # 1 | 2
    message_id: Optional[int] = None

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "lang": self.lang,
            "chatId": self.chat_id,
            "symbol": self.symbol,
            "messageId": self.message_id,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Player":
        return cls(
            id=data["id"],
            name=data["name"],
            lang=data["lang"],
            chat_id=data["chatId"],
            symbol=data["symbol"],
            message_id=data.get("messageId"),
        )


@dataclass
class Game:
    id: str
    mode: Mode
    board: list[list[int]]
    turn: int
    status: GameStatus
    players: list[Player]
    move_count: int = 0
    turn_started_at: int = 0
    created_at: int = 0

    def find_player(self, user_id: int) -> Optional[Player]:
        for p in self.players:
            if p.id == user_id:
                return p
        return None

    def opponent_of(self, user_id: int) -> Optional[Player]:
        for p in self.players:
            if p.id != user_id:
                return p
        return None

    def player_by_symbol(self, symbol: int) -> Optional[Player]:
        for p in self.players:
            if p.symbol == symbol:
                return p
        return None


@dataclass
class HistoryEntry:
    id: Optional[int]
    opponent_name: str
    mode: str
    result: str
    end_reason: Optional[str]
    coins_delta: int
    duration_seconds: Optional[int]
    board_snapshot: Optional[str]
    played_at: int


@dataclass
class WaitingPlayer:
    user_id: int
    chat_id: int
    name: str
    lang: str


@dataclass
class FriendRequestRow:
    from_id: int
    to_id: int
    created_at: int
