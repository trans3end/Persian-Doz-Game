"""Direct port of handleCallbackQuery() in handlers.js — the single entry
point for every inline-button tap. Preserves the exact same dispatch
order as the original, including the active-game intercept.
"""
from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery

from context import AppContext
from game import games as game_service
from game import matchmaking
from services import admin as admin_service
from services import channel as channel_service
from services import friends as friends_service
from services.rewards import claim_daily_coin
from services.referrals import send_referral_info
from services.ranking import send_history, send_league
from telegram.keyboards import (
    active_game_prompt_keyboard,
    empty_keyboard,
    main_menu_keyboard,
    play_friends_inline_keyboard,
)
from telegram.texts import t

router = Router(name="callbacks")

# Callback data prefixes that are part of the game itself (or the
# resume/leave prompt) and must NOT be intercepted by the active-game
# prompt, even while the user has a game in progress.
_GAME_INTERNAL_EXACT = {"noop", "msg:close", "channel:check"}
_GAME_INTERNAL_PREFIXES = ("move:", "gameprompt:")


@router.callback_query()
async def handle_callback_query(cq: CallbackQuery, ctx: AppContext) -> None:
    chat_id = cq.message.chat.id
    from_user = cq.from_user
    user = await ctx.repo.get_or_create_user(
        from_user.id, from_user.first_name, from_user.last_name, from_user.username
    )
    lang = user.language
    data = cq.data or ""

    if data == "noop":
        await ctx.tg.answer_callback_query(cq.id)
        return

    if data == "msg:close":
        await ctx.tg.answer_callback_query(cq.id)
        await ctx.tg.delete_message(chat_id, cq.message.message_id)
        return

    if data == "channel:check":
        ok = await channel_service.is_channel_member(user, ctx, force_recheck=True)
        if ok:
            await ctx.tg.answer_callback_query(cq.id, t(lang, "channelJoinedSuccess"))
            await ctx.tg.send_message(chat_id, t(lang, "mainMenuTitle"), reply_markup=main_menu_keyboard(lang))
        else:
            await ctx.tg.answer_callback_query(cq.id, t(lang, "channelStillNotJoined"), True)
        return

    if not await channel_service.check_channel_gate(user, chat_id, ctx):
        await ctx.tg.answer_callback_query(cq.id)
        return

    # If this player has an active (unfinished, non-timed-out) game, any
    # button other than the game's own board/resign controls — or this
    # prompt's own Resume/Leave buttons — is intercepted here: instead of
    # performing whatever the button was for, show a Resume/Leave choice.
    # Group-chat games are left out of this so the existing group
    # join/new-game flows keep working exactly as before.
    is_private_chat = cq.message.chat.type not in ("group", "supergroup")
    is_game_internal_action = (
        data in _GAME_INTERNAL_EXACT
        or data.startswith(_GAME_INTERNAL_PREFIXES)
        or data == "game:resign"
    )

    if is_private_chat and not is_game_internal_action:
        active_game_id = await ctx.repo.get_active_game_id(user.id)
        if active_game_id:
            active_game = await ctx.repo.get_game(active_game_id)
            if active_game and active_game.status == "active" and active_game.mode != "group":
                await ctx.tg.answer_callback_query(cq.id)
                await ctx.tg.send_message(
                    chat_id, t(lang, "activeGamePrompt"), reply_markup=active_game_prompt_keyboard(lang)
                )
                return

    if data == "gameprompt:resume":
        await game_service.handle_resume_game_prompt(cq, user, ctx)
        return

    if data == "gameprompt:leave":
        await game_service.handle_leave_game_prompt(cq, user, ctx)
        return

    if data.startswith("menu:back"):
        target = data.split(":")[2] if len(data.split(":")) > 2 else "main"
        await ctx.tg.answer_callback_query(cq.id)

        if target == "market":
            from services.users import send_market_menu

            await send_market_menu(chat_id, user, ctx)
            return
        if target == "play_friends":
            await ctx.tg.send_message(
                chat_id, t(lang, "playFriendsIntro"), reply_markup=play_friends_inline_keyboard(lang)
            )
            return
        # target == "main" (or unrecognized): the persistent bottom
        # keyboard is already visible, so nothing further is sent.
        return

    if data.startswith("lang:"):
        new_lang = data.split(":")[1]
        user.language = "en" if new_lang == "en" else "fa"
        await ctx.repo.put_user(user)
        await ctx.tg.answer_callback_query(cq.id)
        await ctx.tg.send_message(
            chat_id, t(user.language, "langSet"), reply_markup=main_menu_keyboard(user.language)
        )
        return

    if data == "friend:add":
        await friends_service.start_add_friend_link(cq, user, ctx)
        return

    if data == "friend:add_by_id":
        await friends_service.start_add_friend_by_id(cq, user, ctx)
        return

    if data == "friend:cancel_input":
        await friends_service.cancel_add_friend_input(cq, user, ctx)
        return

    if data == "friend:list":
        await friends_service.show_friend_list(cq, user, ctx)
        return

    if data == "friend:requests":
        await friends_service.show_friend_requests(cq, user, ctx)
        return

    if data.startswith("friend:accept:"):
        await friends_service.accept_friend_request(cq, user, int(data.split(":")[2]), ctx)
        return

    if data.startswith("friend:reject:"):
        await friends_service.reject_friend_request(cq, user, int(data.split(":")[2]), ctx)
        return

    if data.startswith("friend:invite:"):
        await game_service.handle_friend_invite(cq, user, int(data.split(":")[2]), ctx)
        return

    if data.startswith("friend:remove:"):
        await friends_service.remove_friend(cq, user, int(data.split(":")[2]), ctx)
        return

    if data.startswith("game:invite_accept:"):
        await game_service.handle_game_invite_accept(cq, user, int(data.split(":")[2]), ctx)
        return

    if data.startswith("game:invite_reject:"):
        await game_service.handle_game_invite_reject(cq, user, int(data.split(":")[2]), ctx)
        return

    if data == "market:daily":
        await claim_daily_coin(cq, user, ctx)
        return

    if data == "market:referral":
        await ctx.tg.answer_callback_query(cq.id)
        await send_referral_info(chat_id, user, ctx)
        return

    if data == "menu:history":
        await ctx.tg.answer_callback_query(cq.id)
        await send_history(chat_id, user, ctx)
        return

    if data.startswith("history:more:"):
        offset = int(data.split(":")[2] or 0)
        await ctx.tg.answer_callback_query(cq.id)
        await send_history(chat_id, user, ctx, offset)
        return

    if data == "menu:league":
        await ctx.tg.answer_callback_query(cq.id)
        await send_league(chat_id, lang, ctx)
        return

    if data == "league:join":
        await ctx.tg.answer_callback_query(cq.id, t(lang, "joinedLeague"))
        return

    if data == "match:find":
        await matchmaking.handle_find_match(cq, user, ctx)
        return

    if data == "match:cancel":
        await matchmaking.handle_cancel_match(cq, user, ctx)
        return

    if data.startswith("group:join:"):
        await game_service.handle_group_join(cq, user, ctx)
        return

    if data == "group:new":
        await game_service.handle_group_new_game(cq, user, ctx)
        return

    if data.startswith("move:"):
        col = int(data.split(":")[1])
        await game_service.handle_move(cq, user, col, ctx)
        return

    if data == "game:resign":
        await ctx.tg.answer_callback_query(cq.id)
        await game_service.resign_active_game(user, chat_id, ctx)
        return

    if data.startswith("admin:"):
        await admin_service.handle_admin_callback(cq, user, data, ctx)
        return

    await ctx.tg.answer_callback_query(cq.id)
