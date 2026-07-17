"""Direct port of handleFindMatch() and handleCancelMatch() in handlers.js."""
from __future__ import annotations

from aiogram.types import CallbackQuery

from context import AppContext
from database.models import Player, User, WaitingPlayer
from telegram.keyboards import empty_keyboard, main_menu_keyboard, match_searching_keyboard
from telegram.texts import t


async def handle_find_match(cq: CallbackQuery, user: User, ctx: AppContext) -> None:
    from game.games import start_game  # local import: avoids a circular import with game/matchmaking.py

    chat_id = cq.message.chat.id
    lang = user.language

    existing_game_id = await ctx.repo.get_active_game_id(user.id)
    if existing_game_id:
        await ctx.tg.answer_callback_query(cq.id, t(lang, "inGameAlready"), True)
        return

    waiting = await ctx.repo.get_waiting_player()

    if not waiting or waiting.user_id == user.id:
        await ctx.repo.set_waiting_player(WaitingPlayer(user.id, chat_id, user.name, lang))
        await ctx.tg.answer_callback_query(cq.id)
        await ctx.tg.send_message(
            chat_id, t(lang, "searchingOpponent"), reply_markup=match_searching_keyboard(lang)
        )
        return

    await ctx.repo.clear_waiting_player()
    await ctx.tg.answer_callback_query(cq.id)

    opponent_user = await ctx.repo.get_user(waiting.user_id)
    await start_game(
        Player(id=user.id, name=user.name, lang=lang, chat_id=chat_id, symbol=0),
        Player(
            id=waiting.user_id,
            name=(opponent_user.name if opponent_user else waiting.name),
            lang=waiting.lang,
            chat_id=waiting.chat_id,
            symbol=0,
        ),
        "random",
        ctx,
    )


async def handle_cancel_match(cq: CallbackQuery, user: User, ctx: AppContext) -> None:
    """Lets a user waiting in the matchmaking queue back out cleanly: the
    queue row is removed (never left dangling) and they're returned to
    the main menu, so nobody can get stuck "searching" forever.
    """
    chat_id = cq.message.chat.id
    lang = user.language

    waiting = await ctx.repo.get_waiting_player()
    if not waiting or waiting.user_id != user.id:
        await ctx.tg.answer_callback_query(cq.id, t(lang, "notSearching"), True)
        return

    await ctx.repo.clear_waiting_player()
    await ctx.tg.answer_callback_query(cq.id, t(lang, "matchCanceled"))
    await ctx.tg.edit_message_reply_markup(chat_id, cq.message.message_id, empty_keyboard())
    await ctx.tg.send_message(chat_id, t(lang, "mainMenuTitle"), reply_markup=main_menu_keyboard(lang))
