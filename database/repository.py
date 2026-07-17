"""Repository layer — direct port of the `Store` class in the original
store.js. Method names/behavior are kept close to the original so the
service layer above reads like a faithful translation; only the D1
`.prepare().bind().run()/.first()/.all()` calling convention changes to
aiosqlite's `execute()` / `fetchone()` / `fetchall()`.

Note on the original's defensive "no such column" try/except fallbacks:
those existed because store.js had to keep working against an old D1
database that hadn't run later migrations yet. Since schema.sql here
always creates every column up front for a fresh install, those fallback
branches aren't needed — but if you apply database/migrations/*.sql
incrementally to an older database instead of using schema.sql directly,
re-introduce the same try/except pattern around the affected queries.
"""
from __future__ import annotations

import json
from typing import Any, Optional

import aiosqlite

from database.models import (
    FriendRequestRow,
    Game,
    HistoryEntry,
    Player,
    Settings,
    User,
    WaitingPlayer,
)
from database.utils import generate_code, new_game_id, now_ms
from storage.sqlite import Database


def _row_to_user(row: aiosqlite.Row, friends: list[int]) -> User:
    return User(
        id=row["id"],
        name=row["name"],
        username=row["username"],
        username_visible=bool(row["username_visible"]),
        language=row["language"],
        score=row["score"],
        coins=row["coins"],
        wins=row["wins"],
        losses=row["losses"],
        draws=row["draws"],
        invites_count=row["invites_count"],
        referral_code=row["referral_code"],
        referred_by=row["referred_by"],
        channel_verified_at=row["channel_verified_at"],
        last_daily_claim_at=row["last_daily_claim_at"],
        friends=friends,
        created_at=row["created_at"],
    )


class Repository:
    def __init__(self, db: Database):
        self.db = db

    @property
    def conn(self) -> aiosqlite.Connection:
        return self.db.conn

    # ---- Settings (admin-configurable) --------------------------------

    async def get_settings(self) -> Settings:
        cur = await self.conn.execute("SELECT key, value FROM settings")
        rows = await cur.fetchall()
        stored = {row["key"]: json.loads(row["value"]) for row in rows}
        defaults = Settings.defaults()
        return Settings(
            support_link=stored.get("supportLink", defaults.support_link),
            referral_bonus=stored.get("referralBonus", defaults.referral_bonus),
            signup_bonus=stored.get("signupBonus", defaults.signup_bonus),
            required_channel=stored.get("requiredChannel", defaults.required_channel),
        )

    async def update_settings(self, patch: dict[str, Any]) -> Settings:
        # patch keys use the original JS camelCase names (supportLink,
        # referralBonus, signupBonus, requiredChannel) so callers can pass
        # through the exact same dict shape as the JS version did.
        for key, value in patch.items():
            await self.conn.execute(
                """INSERT INTO settings (key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (key, json.dumps(value)),
            )
        await self.conn.commit()
        return await self.get_settings()

    # ---- Bot username cache --------------------------------------------

    async def get_cached_bot_username(self) -> Optional[str]:
        cur = await self.conn.execute(
            "SELECT value FROM bot_meta WHERE key = 'bot_username'"
        )
        row = await cur.fetchone()
        return row["value"] if row else None

    async def set_cached_bot_username(self, username: str) -> None:
        await self.conn.execute(
            """INSERT INTO bot_meta (key, value) VALUES ('bot_username', ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (username,),
        )
        await self.conn.commit()

    # ---- Admin conversational state ------------------------------------

    async def get_admin_state(self, admin_id: int) -> Optional[dict[str, str]]:
        cur = await self.conn.execute(
            "SELECT action FROM admin_state WHERE admin_id = ?", (admin_id,)
        )
        row = await cur.fetchone()
        return {"action": row["action"]} if row else None

    async def set_admin_state(self, admin_id: int, action: str) -> None:
        await self.conn.execute(
            """INSERT INTO admin_state (admin_id, action, created_at) VALUES (?, ?, ?)
               ON CONFLICT(admin_id) DO UPDATE SET action = excluded.action,
                                                    created_at = excluded.created_at""",
            (admin_id, action, now_ms()),
        )
        await self.conn.commit()

    async def clear_admin_state(self, admin_id: int) -> None:
        await self.conn.execute("DELETE FROM admin_state WHERE admin_id = ?", (admin_id,))
        await self.conn.commit()

    # ---- Generic per-user conversational state -------------------------

    async def get_user_state(self, user_id: int) -> Optional[dict[str, str]]:
        cur = await self.conn.execute(
            "SELECT action FROM user_state WHERE user_id = ?", (user_id,)
        )
        row = await cur.fetchone()
        return {"action": row["action"]} if row else None

    async def set_user_state(self, user_id: int, action: str) -> None:
        await self.conn.execute(
            """INSERT INTO user_state (user_id, action, created_at) VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET action = excluded.action,
                                                   created_at = excluded.created_at""",
            (user_id, action, now_ms()),
        )
        await self.conn.commit()

    async def clear_user_state(self, user_id: int) -> None:
        await self.conn.execute("DELETE FROM user_state WHERE user_id = ?", (user_id,))
        await self.conn.commit()

    # ---- Users ----------------------------------------------------------

    async def get_friend_ids(self, user_id: int) -> list[int]:
        cur = await self.conn.execute(
            "SELECT friend_id FROM friends WHERE user_id = ?", (user_id,)
        )
        rows = await cur.fetchall()
        return [row["friend_id"] for row in rows]

    async def get_user(self, user_id: int) -> Optional[User]:
        cur = await self.conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = await cur.fetchone()
        if not row:
            return None
        friends = await self.get_friend_ids(user_id)
        return _row_to_user(row, friends)

    async def put_user(self, user: User) -> None:
        await self.conn.execute(
            """INSERT INTO users
                 (id, name, username, username_visible, language, score, coins,
                  wins, losses, draws, invites_count, referral_code, referred_by, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 name = excluded.name,
                 username = excluded.username,
                 username_visible = excluded.username_visible,
                 language = excluded.language,
                 score = excluded.score,
                 coins = excluded.coins,
                 wins = excluded.wins,
                 losses = excluded.losses,
                 draws = excluded.draws,
                 invites_count = excluded.invites_count,
                 referral_code = excluded.referral_code,
                 referred_by = excluded.referred_by""",
            (
                user.id,
                user.name,
                user.username,
                1 if user.username_visible else 0,
                user.language,
                user.score,
                user.coins,
                user.wins,
                user.losses,
                user.draws,
                user.invites_count,
                user.referral_code,
                user.referred_by,
                user.created_at,
            ),
        )
        await self.conn.commit()
        # Friendships live in their own table (see add_friends) and aren't touched here.

    async def get_user_by_referral_code(self, code: str) -> Optional[User]:
        cur = await self.conn.execute(
            "SELECT * FROM users WHERE referral_code = ?", (code,)
        )
        row = await cur.fetchone()
        if not row:
            return None
        friends = await self.get_friend_ids(row["id"])
        return _row_to_user(row, friends)

    async def ensure_referral_code(self, user: User) -> str:
        if user.referral_code:
            return user.referral_code
        while True:
            code = generate_code(8)
            cur = await self.conn.execute(
                "SELECT 1 FROM users WHERE referral_code = ?", (code,)
            )
            if not await cur.fetchone():
                break
        await self.conn.execute(
            "UPDATE users SET referral_code = ? WHERE id = ?", (code, user.id)
        )
        await self.conn.commit()
        user.referral_code = code
        return code

    async def get_or_create_user(
        self,
        tg_user_id: int,
        first_name: str,
        last_name: Optional[str],
        username: Optional[str],
    ) -> User:
        user = await self.get_user(tg_user_id)
        if user is None:
            settings = await self.get_settings()
            display_name = " ".join(filter(None, [first_name, last_name])) or "Player"
            user = User(
                id=tg_user_id,
                name=display_name,
                username=username,
                username_visible=True,
                language="fa",  # always start in Persian; users can switch via the زبان button
                score=0,
                coins=settings.signup_bonus,
                wins=0,
                losses=0,
                draws=0,
                invites_count=0,
                referral_code=None,
                referred_by=None,
                channel_verified_at=None,
                last_daily_claim_at=None,
                friends=[],
                created_at=now_ms(),
            )
            await self.put_user(user)
            await self.ensure_referral_code(user)
        return user

    async def list_all_users(self) -> list[User]:
        cur = await self.conn.execute("SELECT * FROM users")
        rows = await cur.fetchall()
        users = []
        for row in rows:
            friends = await self.get_friend_ids(row["id"])
            users.append(_row_to_user(row, friends))
        return users

    async def leaderboard(self, limit: int = 10) -> list[User]:
        cur = await self.conn.execute(
            "SELECT * FROM users ORDER BY score DESC LIMIT ?", (limit,)
        )
        rows = await cur.fetchall()
        return [_row_to_user(row, []) for row in rows]  # friends aren't needed for the league table

    # ---- Mandatory channel-join gate --------------------------------------

    async def mark_channel_verified(self, user_id: int) -> None:
        await self.conn.execute(
            "UPDATE users SET channel_verified_at = ? WHERE id = ?", (now_ms(), user_id)
        )
        await self.conn.commit()

    # ---- Daily coin bonus ------------------------------------------------

    async def claim_daily_coin(self, user_id: int, amount: int) -> Optional[User]:
        await self.conn.execute(
            "UPDATE users SET coins = coins + ?, last_daily_claim_at = ? WHERE id = ?",
            (amount, now_ms(), user_id),
        )
        await self.conn.commit()
        return await self.get_user(user_id)

    async def add_coins_to_user(self, user_id: int, amount: int) -> Optional[User]:
        cur = await self.conn.execute(
            "SELECT coins FROM users WHERE id = ?", (user_id,)
        )
        row = await cur.fetchone()
        if not row:
            return None
        new_coins = max(0, row["coins"] + amount)
        await self.conn.execute(
            "UPDATE users SET coins = ? WHERE id = ?", (new_coins, user_id)
        )
        await self.conn.commit()
        return await self.get_user(user_id)

    async def add_coins_to_all(self, amount: int) -> int:
        await self.conn.execute("UPDATE users SET coins = MAX(0, coins + ?)", (amount,))
        await self.conn.commit()
        cur = await self.conn.execute("SELECT COUNT(*) as c FROM users")
        row = await cur.fetchone()
        return row["c"] if row else 0

    # ---- Friends --------------------------------------------------------

    async def add_friend_request(self, from_id: int, to_id: int) -> None:
        await self.conn.execute(
            """INSERT INTO friend_requests (from_id, to_id, created_at) VALUES (?, ?, ?)
               ON CONFLICT(from_id, to_id) DO NOTHING""",
            (from_id, to_id, now_ms()),
        )
        await self.conn.commit()

    async def get_friend_request(self, from_id: int, to_id: int) -> Optional[FriendRequestRow]:
        cur = await self.conn.execute(
            "SELECT from_id, to_id, created_at FROM friend_requests WHERE from_id = ? AND to_id = ?",
            (from_id, to_id),
        )
        row = await cur.fetchone()
        if not row:
            return None
        return FriendRequestRow(row["from_id"], row["to_id"], row["created_at"])

    async def list_friend_requests(self, to_id: int) -> list[FriendRequestRow]:
        cur = await self.conn.execute(
            "SELECT from_id, to_id, created_at FROM friend_requests WHERE to_id = ?",
            (to_id,),
        )
        rows = await cur.fetchall()
        return [FriendRequestRow(r["from_id"], r["to_id"], r["created_at"]) for r in rows]

    async def remove_friend_request(self, from_id: int, to_id: int) -> None:
        await self.conn.execute(
            "DELETE FROM friend_requests WHERE from_id = ? AND to_id = ?", (from_id, to_id)
        )
        await self.conn.commit()

    async def add_friends(self, id_a: int, id_b: int) -> None:
        now = now_ms()
        await self.conn.execute(
            """INSERT INTO friends (user_id, friend_id, created_at) VALUES (?, ?, ?)
               ON CONFLICT(user_id, friend_id) DO NOTHING""",
            (id_a, id_b, now),
        )
        await self.conn.execute(
            """INSERT INTO friends (user_id, friend_id, created_at) VALUES (?, ?, ?)
               ON CONFLICT(user_id, friend_id) DO NOTHING""",
            (id_b, id_a, now),
        )
        await self.conn.commit()

    async def remove_friend(self, id_a: int, id_b: int) -> None:
        await self.conn.execute(
            "DELETE FROM friends WHERE user_id = ? AND friend_id = ?", (id_a, id_b)
        )
        await self.conn.execute(
            "DELETE FROM friends WHERE user_id = ? AND friend_id = ?", (id_b, id_a)
        )
        await self.conn.commit()

    # ---- Friend-game invites ----------------------------------------------

    async def add_game_invite(self, from_id: int, to_id: int) -> None:
        await self.conn.execute(
            """INSERT INTO game_invites (from_id, to_id, created_at) VALUES (?, ?, ?)
               ON CONFLICT(from_id, to_id) DO UPDATE SET created_at = excluded.created_at""",
            (from_id, to_id, now_ms()),
        )
        await self.conn.commit()

    async def get_game_invite(self, from_id: int, to_id: int) -> Optional[FriendRequestRow]:
        cur = await self.conn.execute(
            "SELECT from_id, to_id, created_at FROM game_invites WHERE from_id = ? AND to_id = ?",
            (from_id, to_id),
        )
        row = await cur.fetchone()
        if not row:
            return None
        return FriendRequestRow(row["from_id"], row["to_id"], row["created_at"])

    async def remove_game_invite(self, from_id: int, to_id: int) -> None:
        await self.conn.execute(
            "DELETE FROM game_invites WHERE from_id = ? AND to_id = ?", (from_id, to_id)
        )
        await self.conn.commit()

    # ---- Game history ----------------------------------------------------

    async def add_history_entry(
        self,
        *,
        user_id: int,
        opponent_name: str,
        mode: str,
        result: str,
        end_reason: Optional[str] = None,
        coins_delta: int = 0,
        duration_seconds: Optional[int] = None,
        board_snapshot: Optional[str] = None,
        played_at: int,
    ) -> Optional[int]:
        cur = await self.conn.execute(
            """INSERT INTO game_history
                 (user_id, opponent_name, mode, result, end_reason, coins_delta,
                  duration_seconds, board_snapshot, played_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                opponent_name,
                mode,
                result,
                end_reason,
                coins_delta,
                duration_seconds,
                board_snapshot,
                played_at,
            ),
        )
        await self.conn.commit()
        return cur.lastrowid

    async def get_history(
        self, user_id: int, limit: int = 10, offset: int = 0
    ) -> list[HistoryEntry]:
        cur = await self.conn.execute(
            """SELECT id, opponent_name, mode, result, end_reason, coins_delta,
                      duration_seconds, board_snapshot, played_at
               FROM game_history WHERE user_id = ? ORDER BY played_at DESC LIMIT ? OFFSET ?""",
            (user_id, limit, offset),
        )
        rows = await cur.fetchall()
        return [
            HistoryEntry(
                id=row["id"],
                opponent_name=row["opponent_name"],
                mode=row["mode"],
                result=row["result"],
                end_reason=row["end_reason"],
                coins_delta=row["coins_delta"],
                duration_seconds=row["duration_seconds"],
                board_snapshot=row["board_snapshot"],
                played_at=row["played_at"],
            )
            for row in rows
        ]

    async def count_history(self, user_id: int) -> int:
        cur = await self.conn.execute(
            "SELECT COUNT(*) as c FROM game_history WHERE user_id = ?", (user_id,)
        )
        row = await cur.fetchone()
        return row["c"] if row else 0

    # ---- Matchmaking queue ------------------------------------------------
    # Mirrors the original single-slot design: only one user waits at a
    # time; queuing up replaces whoever was waiting before.

    async def get_waiting_player(self) -> Optional[WaitingPlayer]:
        cur = await self.conn.execute(
            "SELECT user_id, chat_id, name, lang FROM matchmaking_queue LIMIT 1"
        )
        row = await cur.fetchone()
        if not row:
            return None
        return WaitingPlayer(row["user_id"], row["chat_id"], row["name"], row["lang"])

    async def set_waiting_player(self, entry: WaitingPlayer) -> None:
        await self.conn.execute("DELETE FROM matchmaking_queue")
        await self.conn.execute(
            """INSERT INTO matchmaking_queue (user_id, chat_id, name, lang, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (entry.user_id, entry.chat_id, entry.name, entry.lang, now_ms()),
        )
        await self.conn.commit()

    async def clear_waiting_player(self) -> None:
        await self.conn.execute("DELETE FROM matchmaking_queue")
        await self.conn.commit()

    # ---- Games --------------------------------------------------------

    async def get_game(self, game_id: str) -> Optional[Game]:
        cur = await self.conn.execute("SELECT * FROM games WHERE id = ?", (game_id,))
        row = await cur.fetchone()
        if not row:
            return None
        return Game(
            id=row["id"],
            mode=row["mode"],
            board=json.loads(row["board"]),
            turn=row["turn"],
            status=row["status"],
            players=[Player.from_json(p) for p in json.loads(row["players"])],
            move_count=row["move_count"] or 0,
            turn_started_at=row["turn_started_at"] or row["created_at"],
            created_at=row["created_at"],
        )

    async def put_game(self, game: Game) -> None:
        await self.conn.execute(
            """INSERT INTO games (id, mode, board, turn, chat_enabled, status, players,
                                   move_count, turn_started_at, created_at)
               VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 board = excluded.board,
                 turn = excluded.turn,
                 status = excluded.status,
                 players = excluded.players,
                 move_count = excluded.move_count,
                 turn_started_at = excluded.turn_started_at""",
            (
                game.id,
                game.mode,
                json.dumps(game.board),
                game.turn,
                game.status,
                json.dumps([p.to_json() for p in game.players]),
                game.move_count or 0,
                game.turn_started_at or now_ms(),
                game.created_at or now_ms(),
            ),
        )
        await self.conn.commit()

    async def delete_game(self, game_id: str) -> None:
        await self.conn.execute("DELETE FROM games WHERE id = ?", (game_id,))
        await self.conn.commit()

    async def set_active_game(self, user_id: int, game_id: str) -> None:
        await self.conn.execute(
            """INSERT INTO active_games (user_id, game_id, created_at) VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET game_id = excluded.game_id,
                                                   created_at = excluded.created_at""",
            (user_id, game_id, now_ms()),
        )
        await self.conn.commit()

    async def get_active_game_id(self, user_id: int) -> Optional[str]:
        cur = await self.conn.execute(
            "SELECT game_id FROM active_games WHERE user_id = ?", (user_id,)
        )
        row = await cur.fetchone()
        return row["game_id"] if row else None

    async def clear_active_game(self, user_id: int) -> None:
        await self.conn.execute("DELETE FROM active_games WHERE user_id = ?", (user_id,))
        await self.conn.commit()

    async def list_active_games(self) -> list[Game]:
        """Not present in the original store.js (Durable Objects held timer
        state independently of any "list all active games" query) — added
        so game/timer.py can re-arm timers for every in-progress game after
        a process restart, since asyncio tasks don't survive one.
        """
        cur = await self.conn.execute("SELECT * FROM games WHERE status = 'active'")
        rows = await cur.fetchall()
        games = []
        for row in rows:
            games.append(
                Game(
                    id=row["id"],
                    mode=row["mode"],
                    board=json.loads(row["board"]),
                    turn=row["turn"],
                    status=row["status"],
                    players=[Player.from_json(p) for p in json.loads(row["players"])],
                    move_count=row["move_count"] or 0,
                    turn_started_at=row["turn_started_at"] or row["created_at"],
                    created_at=row["created_at"],
                )
            )
        return games

    # ---- Group games (/game in a group chat) ---------------------------

    async def get_group_game_id(self, chat_id: int) -> Optional[str]:
        cur = await self.conn.execute(
            "SELECT game_id FROM group_games WHERE chat_id = ?", (chat_id,)
        )
        row = await cur.fetchone()
        return row["game_id"] if row else None

    async def set_group_game(self, chat_id: int, game_id: str) -> None:
        await self.conn.execute(
            """INSERT INTO group_games (chat_id, game_id, created_at) VALUES (?, ?, ?)
               ON CONFLICT(chat_id) DO UPDATE SET game_id = excluded.game_id,
                                                   created_at = excluded.created_at""",
            (chat_id, game_id, now_ms()),
        )
        await self.conn.commit()

    async def clear_group_game(self, chat_id: int) -> None:
        await self.conn.execute("DELETE FROM group_games WHERE chat_id = ?", (chat_id,))
        await self.conn.commit()
