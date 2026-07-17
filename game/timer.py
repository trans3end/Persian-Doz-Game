"""Replacement for the GameTimerDO Durable Object in game-timer.js.

The original used one Durable Object instance per game id, with a single
alarm that got rescheduled after every move — 60s after a move it fires a
"30 seconds left" warning, then (if still nobody's moved) a further 30s
later it applies the timeout. Cloudflare's DO alarms persist independently
of any single request; the direct equivalent in a long-running Python
process is one asyncio background task per active game, tracked here so
it can be cancelled/rescheduled the same way `scheduleTimer`/`cancelTimer`
did.

Persistence recovery after restart: asyncio tasks do NOT survive a process
restart the way a DO's alarm storage does, so `recover()` must be called
once at startup (see app.py) to re-arm a timer for every game that was
still active in the database, based on how much of its 90-second window
has actually elapked since `turn_started_at`.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from database.models import Game
from database.utils import now_ms

logger = logging.getLogger(__name__)

WARNING_AFTER_MS = 60_000  # fires with 30s left on the 90s clock
TIMEOUT_AFTER_WARNING_MS = 30_000
TOTAL_TURN_MS = WARNING_AFTER_MS + TIMEOUT_AFTER_WARNING_MS

OnWarning = Callable[[str, int], Awaitable[bool]]
OnTimeout = Callable[[str, int], Awaitable[None]]


class TimerManager:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self.on_warning: Optional[OnWarning] = None
        self.on_timeout: Optional[OnTimeout] = None

    def configure(self, *, on_warning: OnWarning, on_timeout: OnTimeout) -> None:
        self.on_warning = on_warning
        self.on_timeout = on_timeout

    def cancel(self, game_id: str) -> None:
        """Mirrors cancelTimer(ctx, gameId): clears any pending alarm."""
        task = self._tasks.pop(game_id, None)
        if task and not task.done():
            task.cancel()

    def schedule(
        self, game_id: str, move_count: int, *, warning_delay_ms: int = WARNING_AFTER_MS
    ) -> None:
        """Mirrors scheduleTimer(ctx, gameId, moveCount): (re)arms the timer
        for the new current turn. Any previous pending alarm for this game
        is replaced, exactly like overwriting the DO's single stored alarm.
        """
        self.cancel(game_id)
        self._tasks[game_id] = asyncio.create_task(
            self._run(game_id, move_count, warning_delay_ms / 1000)
        )

    def schedule_timeout_phase(self, game_id: str, move_count: int, timeout_delay_ms: int) -> None:
        """Used only by recover(): re-arms directly into the "timeout"
        phase (skipping the warning) when a restart happened after the
        warning had already fired but before the timeout was due.
        """
        self.cancel(game_id)
        self._tasks[game_id] = asyncio.create_task(
            self._run_timeout_only(game_id, move_count, timeout_delay_ms / 1000)
        )

    async def _run(self, game_id: str, move_count: int, warning_delay_s: float) -> None:
        try:
            await asyncio.sleep(max(0.0, warning_delay_s))
            assert self.on_warning is not None
            still_ongoing = await self.on_warning(game_id, move_count)
            if not still_ongoing:
                self._tasks.pop(game_id, None)
                return
            await asyncio.sleep(TIMEOUT_AFTER_WARNING_MS / 1000)
            assert self.on_timeout is not None
            await self.on_timeout(game_id, move_count)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Timer task failed for game %s", game_id)
        finally:
            self._tasks.pop(game_id, None)

    async def _run_timeout_only(self, game_id: str, move_count: int, delay_s: float) -> None:
        try:
            await asyncio.sleep(max(0.0, delay_s))
            assert self.on_timeout is not None
            await self.on_timeout(game_id, move_count)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Timer task failed for game %s", game_id)
        finally:
            self._tasks.pop(game_id, None)

    def recover(self, active_games: list[Game]) -> None:
        """Re-arms timers for every still-active game after a process
        restart, based on elapsed time since turn_started_at. Games whose
        90-second window has already fully elapsed have their timeout
        applied immediately instead of being silently dropped.
        """
        now = now_ms()
        for game in active_games:
            if game.status != "active":
                continue
            elapsed = now - (game.turn_started_at or game.created_at)
            if elapsed < WARNING_AFTER_MS:
                self.schedule(game.id, game.move_count, warning_delay_ms=WARNING_AFTER_MS - elapsed)
            elif elapsed < TOTAL_TURN_MS:
                self.schedule_timeout_phase(
                    game.id, game.move_count, TOTAL_TURN_MS - elapsed
                )
            else:
                # Already overdue (the process was down past the full
                # window) — apply the timeout right away instead of
                # leaving the game stuck forever.
                self.schedule_timeout_phase(game.id, game.move_count, 0)
