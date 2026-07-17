"""Direct port of sendDailyCoinClaim() in handlers.js."""
from __future__ import annotations

import random

from aiogram.types import CallbackQuery

from context import AppContext
from database.models import User
from database.utils import now_ms
from telegram.keyboards import back_close_keyboard
from telegram.texts import t

_DAY_MS = 24 * 60 * 60 * 1000


async def claim_daily_coin(cq: CallbackQuery, user: User, ctx: AppContext) -> None:
    chat_id = cq.message.chat.id
    lang = user.language

    last = user.last_daily_claim_at
    if last and now_ms() - last < _DAY_MS:
        remaining = _DAY_MS - (now_ms() - last)
        hours = remaining // (60 * 60 * 1000)
        minutes = (remaining % (60 * 60 * 1000)) // (60 * 1000)
        await ctx.tg.answer_callback_query(
            cq.id, t(lang, "dailyCoinAlreadyClaimed", hours, minutes), True
        )
        return

    amount = 50 + random.randint(0, 450)  # 50-500 inclusive
    updated = await ctx.repo.claim_daily_coin(user.id, amount)
    await ctx.tg.answer_callback_query(cq.id)
    await ctx.tg.send_message(
        chat_id,
        t(lang, "dailyCoinClaimed", amount, updated.coins),
        reply_markup=back_close_keyboard(lang, [], "market"),
    )
