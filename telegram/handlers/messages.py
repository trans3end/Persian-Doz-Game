"""Direct port of handleMessage() in handlers.js — the single entry point
for every incoming text message (private or group).
"""
from __future__ import annotations

import re

from aiogram import Router
from aiogram.types import Message

from context import AppContext
from database.repository import now_ms
from game.games import handle_group_command
from services import admin as admin_service
from services import friends as friends_service
from services import channel as channel_service
from services.referrals import credit_referral_bonus, send_referral_info
from services.ranking import send_history, send_league
from services.rewards import claim_daily_coin  # noqa: F401  (kept for callback module symmetry)
from services.users import send_account, send_market_menu
from telegram.keyboards import main_menu_keyboard
from telegram.texts import T, t

router = Router(name="messages")

CANCEL_WORDS = {"لغو", "cancel", "/cancel"}

# Reverse lookup: menu button text -> action name, for both languages, so
# the persistent-keyboard text messages can be routed regardless of the
# user's chosen language. Mirrors buildTextActionMap() in handlers.js.
_MENU_ACTION_PAIRS = [
    ("btnPlayFriends", "menu:play_friends"),
    ("btnRandomMatch", "menu:random_match"),
    ("btnHistory", "menu:history"),
    ("btnMarket", "menu:market"),
    ("btnAccount", "menu:account"),
    ("btnCoinsProfile", "menu:market"),
    ("btnSupport", "menu:support"),
    ("btnOtherBots", "menu:other_bots"),
    ("btnTutorial", "menu:tutorial"),
    ("btnLanguage", "menu:language"),
]


def _build_text_action_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for lang in T.keys():
        for key, action in _MENU_ACTION_PAIRS:
            mapping[T[lang][key]] = action
    return mapping


TEXT_ACTION_MAP = _build_text_action_map()

_GROUP_CMD_RE = re.compile(r"^/game(@\S+)?$", re.IGNORECASE)


@router.message()
async def handle_message(message: Message, ctx: AppContext) -> None:
    chat_id = message.chat.id
    from_user = message.from_user
    text = (message.text or "").strip()

    # Group chats: the bot must stay completely inactive (no auto messages,
    # no menus, no replies to normal conversation) until someone explicitly
    # sends /game. Everything else in a group is silently ignored.
    if message.chat.type in ("group", "supergroup"):
        if _GROUP_CMD_RE.match(text):
            bot_username = await channel_service.get_bot_username(ctx)
            if re.match(rf"^/game(@{re.escape(bot_username)})?$", text, re.IGNORECASE):
                user = await ctx.repo.get_or_create_user(
                    from_user.id, from_user.first_name, from_user.last_name, from_user.username
                )
                await handle_group_command(message, user, ctx)
        return  # stay silent — no menu, no reply, no game creation

    existing_user = await ctx.repo.get_user(from_user.id)
    is_new_user = existing_user is None
    user = await ctx.repo.get_or_create_user(
        from_user.id, from_user.first_name, from_user.last_name, from_user.username
    )
    lang = user.language

    if text.startswith("/start"):
        await _handle_start(message, ctx, user, is_new_user)
        return

    if text == "/admin":
        await admin_service.handle_admin_command(chat_id, user, ctx)
        return

    # Admin awaiting a typed value for a pending admin action?
    if ctx.config.is_admin(user.id):
        state = await ctx.repo.get_admin_state(user.id)
        if state and text not in TEXT_ACTION_MAP:
            await admin_service.handle_admin_text_input(text, chat_id, user, state, ctx)
            return

    # Any user awaiting a typed value for a pending action (e.g. add friend by ID)?
    user_state = await ctx.repo.get_user_state(user.id)
    if user_state and text not in TEXT_ACTION_MAP:
        await _handle_user_text_input(text, chat_id, user, user_state, ctx)
        return

    action = TEXT_ACTION_MAP.get(text)
    if action:
        await _route_action(action, chat_id, user, lang, ctx)
        return

    # Unknown text — just show the main menu again. (The Chat feature has
    # been removed entirely, so being in an active game no longer changes
    # how plain text is handled here.)
    await ctx.tg.send_message(chat_id, t(lang, "mainMenuTitle"), reply_markup=main_menu_keyboard(lang))


async def _handle_user_text_input(text: str, chat_id: int, user, state: dict, ctx: AppContext) -> None:
    lang = user.language

    if text.strip().lower() in CANCEL_WORDS:
        await ctx.repo.clear_user_state(user.id)
        await ctx.tg.send_message(chat_id, t(lang, "adminCanceled"), reply_markup=main_menu_keyboard(lang))
        return

    if state["action"] == "add_friend_by_id":
        await friends_service.handle_add_friend_by_id_text(text, chat_id, user, ctx)


async def _handle_start(message: Message, ctx: AppContext, user, is_new_user: bool) -> None:
    chat_id = message.chat.id
    lang = user.language
    parts = (message.text or "").split(" ", 1)
    payload = parts[1].strip() if len(parts) > 1 else None

    if is_new_user:
        settings = await ctx.repo.get_settings()
        if settings.signup_bonus > 0:
            await ctx.tg.send_message(chat_id, t(lang, "signupBonus", settings.signup_bonus))

    if payload and payload.startswith("friend_"):
        try:
            from_id = int(payload.replace("friend_", "", 1))
        except ValueError:
            from_id = 0
        if from_id and from_id != user.id:
            await friends_service.create_friend_request(from_id, user.id, ctx)
    elif payload and is_new_user and not user.referred_by:
        # Treat any other /start payload as a referral code.
        referrer = await ctx.repo.get_user_by_referral_code(payload)
        if referrer and referrer.id != user.id:
            await credit_referral_bonus(referrer, user, ctx)

    await ctx.tg.send_message(chat_id, t(lang, "welcome"), reply_markup=main_menu_keyboard(lang))


async def _route_action(action: str, chat_id: int, user, lang: str, ctx: AppContext) -> None:
    """Direct port of routeAction() in handlers.js."""
    from telegram.keyboards import (
        back_close_keyboard,
        language_inline_keyboard,
        play_friends_inline_keyboard,
        random_match_inline_keyboard,
    )

    if not await channel_service.check_channel_gate(user, chat_id, ctx):
        return

    if action == "menu:play_friends":
        await ctx.tg.send_message(chat_id, t(lang, "playFriendsIntro"), reply_markup=play_friends_inline_keyboard(lang))
    elif action == "menu:random_match":
        await ctx.tg.send_message(chat_id, t(lang, "randomMatchIntro"), reply_markup=random_match_inline_keyboard(lang))
    elif action == "menu:account":
        await send_account(chat_id, user, ctx)
    elif action == "menu:history":
        await send_history(chat_id, user, ctx)
    elif action == "menu:market":
        await send_market_menu(chat_id, user, ctx)
    elif action == "menu:support":
        settings = await ctx.repo.get_settings()
        text = t(lang, "supportText", settings.support_link)
        extra_rows = []
        if settings.required_channel:
            _, join_url = channel_service.parse_channel_identifier(settings.required_channel)
            display_link = join_url or settings.required_channel
            text += f"\n\n{t(lang, 'supportChannelLine', display_link)}"
            if join_url:
                from telegram.keyboards import Btn

                extra_rows.append([Btn(text=t(lang, "btnJoinChannel"), url=join_url)])
        await ctx.tg.send_message(chat_id, text, reply_markup=back_close_keyboard(lang, extra_rows))
    elif action == "menu:other_bots":
        await ctx.tg.send_message(chat_id, t(lang, "otherBotsText"), reply_markup=back_close_keyboard(lang))
    elif action == "menu:tutorial":
        await ctx.tg.send_message(chat_id, t(lang, "tutorialText"), reply_markup=back_close_keyboard(lang))
    elif action == "menu:language":
        await ctx.tg.send_message(chat_id, t(lang, "langPrompt"), reply_markup=language_inline_keyboard())
