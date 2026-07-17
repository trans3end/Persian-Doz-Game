"""Direct port of the admin panel logic in handlers.js: handleAdminCommand,
handleAdminTextInput, handleAdminCallback, and resetUserState.
"""
from __future__ import annotations

from aiogram.types import CallbackQuery

from context import AppContext
from database.models import User
from telegram.formatting import escape_html, render_info_card
from telegram.keyboards import admin_panel_keyboard, back_close_keyboard, cancel_inline_keyboard
from telegram.texts import t

CANCEL_WORDS = {"لغو", "cancel", "/cancel"}


async def handle_admin_command(chat_id: int, user: User, ctx: AppContext) -> None:
    lang = user.language
    if not ctx.config.is_admin(user.id):
        await ctx.tg.send_message(chat_id, t(lang, "adminNoAccess"))
        return
    await ctx.tg.send_message(chat_id, t(lang, "adminPanelTitle"), reply_markup=admin_panel_keyboard(lang))


async def handle_admin_callback(cq: CallbackQuery, user: User, data: str, ctx: AppContext) -> None:
    chat_id = cq.message.chat.id
    lang = user.language

    if not ctx.config.is_admin(user.id):
        await ctx.tg.answer_callback_query(cq.id, t(lang, "adminNoAccess"), True)
        return

    sub = data.split(":")[1]
    await ctx.tg.answer_callback_query(cq.id)

    prompts = {
        "set_support": "adminAskSupportLink",
        "set_channel": "adminAskChannel",
        "add_all": "adminAskAddAll",
        "add_one": "adminAskAddOne",
        "set_referral": "adminAskReferralBonus",
        "set_signup": "adminAskSignupBonus",
        "reset_user": "adminAskResetUser",
    }

    if sub in prompts:
        await ctx.repo.set_admin_state(user.id, sub)
        await ctx.tg.send_message(chat_id, t(lang, prompts[sub]), reply_markup=cancel_inline_keyboard(lang))
        return

    if sub == "view":
        settings = await ctx.repo.get_settings()
        rows = [
            (t(lang, "adminBtnSupport"), settings.support_link),
            (t(lang, "adminBtnChannel"), settings.required_channel or "—"),
            (t(lang, "adminBtnReferralBonus"), str(settings.referral_bonus)),
            (t(lang, "adminBtnSignupBonus"), str(settings.signup_bonus)),
        ]
        await ctx.tg.send_message(
            chat_id, render_info_card(t(lang, "adminPanelTitle"), rows), reply_markup=back_close_keyboard(lang)
        )
        return

    if sub == "cancel":
        await ctx.repo.clear_admin_state(user.id)
        await ctx.tg.send_message(chat_id, t(lang, "adminCanceled"))


async def handle_admin_text_input(
    text: str, chat_id: int, user: User, state: dict, ctx: AppContext
) -> None:
    lang = user.language
    action = state["action"]

    if text.strip().lower() in CANCEL_WORDS:
        await ctx.repo.clear_admin_state(user.id)
        await ctx.tg.send_message(chat_id, t(lang, "adminCanceled"))
        return

    if action == "set_support":
        await ctx.repo.update_settings({"supportLink": text.strip()})
        await ctx.repo.clear_admin_state(user.id)
        await ctx.tg.send_message(chat_id, t(lang, "adminSupportUpdated", escape_html(text.strip())))
        return

    if action == "set_channel":
        value = text.strip()
        await ctx.repo.clear_admin_state(user.id)
        if value == "-":
            await ctx.repo.update_settings({"requiredChannel": ""})
            await ctx.tg.send_message(chat_id, t(lang, "adminChannelDisabled"))
        else:
            await ctx.repo.update_settings({"requiredChannel": value})
            await ctx.tg.send_message(chat_id, t(lang, "adminChannelUpdated", escape_html(value)))
        return

    if action == "add_all":
        try:
            amount = int(text.strip())
        except ValueError:
            await ctx.tg.send_message(chat_id, t(lang, "adminInvalidNumber"))
            return
        count = await ctx.repo.add_coins_to_all(amount)
        await ctx.repo.clear_admin_state(user.id)
        await ctx.tg.send_message(chat_id, t(lang, "adminAddAllDone", amount, count))
        return

    if action == "add_one":
        parts = text.strip().split()
        if len(parts) != 2:
            await ctx.tg.send_message(chat_id, t(lang, "adminInvalidFormat"))
            return
        try:
            target_id = int(parts[0])
            amount = int(parts[1])
        except ValueError:
            await ctx.tg.send_message(chat_id, t(lang, "adminInvalidFormat"))
            return
        target_user = await ctx.repo.add_coins_to_user(target_id, amount)
        if not target_user:
            await ctx.tg.send_message(chat_id, t(lang, "adminUserNotFound"))
            return
        await ctx.repo.clear_admin_state(user.id)
        await ctx.tg.send_message(chat_id, t(lang, "adminAddOneDone", amount, escape_html(target_user.name)))
        return

    if action == "set_referral":
        try:
            amount = int(text.strip())
        except ValueError:
            await ctx.tg.send_message(chat_id, t(lang, "adminInvalidNumber"))
            return
        await ctx.repo.update_settings({"referralBonus": amount})
        await ctx.repo.clear_admin_state(user.id)
        await ctx.tg.send_message(chat_id, t(lang, "adminReferralBonusUpdated", amount))
        return

    if action == "set_signup":
        try:
            amount = int(text.strip())
        except ValueError:
            await ctx.tg.send_message(chat_id, t(lang, "adminInvalidNumber"))
            return
        await ctx.repo.update_settings({"signupBonus": amount})
        await ctx.repo.clear_admin_state(user.id)
        await ctx.tg.send_message(chat_id, t(lang, "adminSignupBonusUpdated", amount))
        return

    if action == "reset_user":
        try:
            target_id = int(text.strip())
            if target_id == 0:
                raise ValueError
        except ValueError:
            await ctx.tg.send_message(chat_id, t(lang, "adminInvalidNumber"))
            return
        await ctx.repo.clear_admin_state(user.id)
        result = await reset_user_state(target_id, ctx)
        if not result:
            await ctx.tg.send_message(chat_id, t(lang, "adminUserNotFound"))
            return
        await ctx.tg.send_message(chat_id, t(lang, "adminResetUserDone", escape_html(result)))
        return

    await ctx.repo.clear_admin_state(user.id)


async def reset_user_state(target_id: int, ctx: AppContext) -> str | None:
    """Fully unsticks a user: ends any active game they're in (notifying
    the opponent, if any, via the normal finishGame flow), clears them
    from the matchmaking queue, and clears any pending "waiting for typed
    input" state. Returns the user's name if found, else None.
    """
    from game.games import finish_game  # local import: avoids a circular import with services/admin.py

    target_user = await ctx.repo.get_user(target_id)
    if not target_user:
        return None

    game_id = await ctx.repo.get_active_game_id(target_id)
    if game_id:
        game = await ctx.repo.get_game(game_id)
        if game and game.status == "active":
            opponent = game.opponent_of(target_id)
            game.status = "finished"
            if opponent:
                # Treat it like a resignation by the stuck player so both
                # sides get a normal result notification, coins, and
                # history — rather than the game just vanishing.
                await finish_game(game, winner_symbol=opponent.symbol, win_cells=None, reason="resign", ctx=ctx)
            else:
                # Malformed game with no distinct opponent — just clear it out.
                ctx.timers.cancel(game.id)
                await ctx.repo.clear_active_game(target_id)
                await ctx.repo.delete_game(game.id)
        else:
            await ctx.repo.clear_active_game(target_id)

    waiting = await ctx.repo.get_waiting_player()
    if waiting and waiting.user_id == target_id:
        await ctx.repo.clear_waiting_player()

    await ctx.repo.clear_user_state(target_id)

    return target_user.name
