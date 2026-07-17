"""Shared per-process context, equivalent to the `ctx = { tg, store, env }`
object threaded through every handler in the original handlers.js.
"""
from __future__ import annotations

from dataclasses import dataclass

from config import Config
from database.repository import Repository
from game.timer import TimerManager
from telegram.client import TelegramClient


@dataclass
class AppContext:
    tg: TelegramClient
    repo: Repository
    config: Config
    timers: TimerManager
