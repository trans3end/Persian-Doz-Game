"""Direct port of sendAccount() plus the getOrCreateUser call-site glue
from handlers.js. get_or_create_user itself lives in the repository layer
(database/repository.py), same as the original where Store owned it.
"""
from __future__ import annotations

from aiogram.types import User as TgUser

from context import AppContext
from database.models import User
from telegram.formatting import escape_html, render_info_card
from telegram.keyboards import back_close_keyboard
from telegram.texts import t


async def get_or_create_user(from_user: TgUser, ctx: AppContext) -> tuple[User, bool]:
    """Returns (user, is_new_user)."""
    existing = await ctx.repo.get_user(from_user.id)
    is_new = existing is None
    user = await ctx.repo.get_or_create_user(
        from_user.id, from_user.first_name, from_user.last_name, from_user.username
    )
    return user, is_new


async def send_account(chat_id: int, user: User, ctx: AppContext) -> None:
    lang = user.language
    r = t(lang, "accountRows")

    rows = [
        (r["name"], escape_html(user.name)),
        (r["username"], f"@{escape_html(user.username)}" if user.username else "-"),
        (r["usernameVisibility"], r["shown"] if user.username_visible else r["hidden"]),
        (r["numericId"], f"<code>{user.id}</code>"),
        (r["score"], str(user.score)),
        (r["coins"], str(user.coins)),
        (r["wins"], str(user.wins)),
        (r["losses"], str(user.losses)),
        (r["draws"], str(user.draws)),
    ]
    text = render_info_card(t(lang, "accountTitle"), rows)
    await ctx.tg.send_message(chat_id, text, reply_markup=back_close_keyboard(lang))


async def send_market_menu(chat_id: int, user: User, ctx: AppContext) -> None:
    from telegram.keyboards import market_menu_keyboard

    lang = user.language
    text = t(lang, "marketIntro", user.coins)
    await ctx.tg.send_message(chat_id, text, reply_markup=market_menu_keyboard(lang))
