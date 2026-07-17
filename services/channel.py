"""Direct port of the mandatory-channel-join gate and bot-username
resolution from util.js + the isChannelMember/checkChannelGate helpers
at the top of handlers.js.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from aiogram.exceptions import TelegramAPIError

from context import AppContext
from database.models import User
from telegram.keyboards import channel_gate_keyboard
from telegram.texts import t

logger = logging.getLogger(__name__)

# How long a confirmed membership is trusted before re-checking, to avoid
# hitting Telegram's getChatMember on every single button tap.
CHANNEL_VERIFY_CACHE_MS = 6 * 60 * 60 * 1000  # 6 hours

_USERNAME_RE = re.compile(r"^(?:https?://)?t\.me/([A-Za-z0-9_]{5,})$", re.IGNORECASE)
_BARE_USERNAME_RE = re.compile(r"^@?([A-Za-z0-9_]{5,})$")
_PRIVATE_INVITE_RE = re.compile(r"^https?://t\.me/(\+|joinchat/)", re.IGNORECASE)
_NUMERIC_RE = re.compile(r"^-?\d+$")


def parse_channel_identifier(value: str) -> tuple[Optional[str], Optional[str]]:
    """Returns (api_chat_id, join_url). Accepts "@username",
    "https://t.me/username", or a bare "username". A private t.me/+xxxx
    invite link can't be resolved to an id via the Bot API, so api_chat_id
    comes back None in that case and the membership check is skipped.
    """
    raw = (value or "").strip()
    if not raw:
        return None, None

    m = _USERNAME_RE.match(raw) or _BARE_USERNAME_RE.match(raw)
    if m and "/+" not in raw and "joinchat" not in raw:
        username = m.group(1)
        return f"@{username}", f"https://t.me/{username}"

    if _PRIVATE_INVITE_RE.match(raw):
        return None, raw
    if _NUMERIC_RE.match(raw):
        return raw, None

    return None, raw


async def check_channel_membership(ctx: AppContext, api_chat_id: Optional[str], user_id: int) -> Optional[bool]:
    """Returns True/False, or None if the check couldn't be performed
    (misconfigured channel, or the bot isn't an admin there) — callers
    should treat None as "skip the check" rather than "not a member".
    """
    if not api_chat_id:
        return None
    try:
        member = await ctx.tg.get_chat_member(api_chat_id, user_id)
        status = getattr(member, "status", None)
        return status in ("creator", "administrator", "member")
    except TelegramAPIError as err:
        logger.error("getChatMember failed: %s", err)
        return None


async def is_channel_member(
    user: User, ctx: AppContext, *, force_recheck: bool = False
) -> bool:
    """Pure membership check (no messages sent). Admins and
    unconfigured/unverifiable channels always resolve to True ("allowed").
    """
    from database.utils import now_ms

    if ctx.config.is_admin(user.id):
        return True

    settings = await ctx.repo.get_settings()
    if not settings.required_channel:
        return True

    if (
        not force_recheck
        and user.channel_verified_at
        and now_ms() - user.channel_verified_at < CHANNEL_VERIFY_CACHE_MS
    ):
        return True

    api_chat_id, _ = parse_channel_identifier(settings.required_channel)
    if not api_chat_id:
        return True  # can't verify — fail open rather than lock everyone out

    result = await check_channel_membership(ctx, api_chat_id, user.id)
    if result is None:
        return True  # check failed (misconfig / bot not admin there) — fail open
    if result:
        await ctx.repo.mark_channel_verified(user.id)
        return True
    return False


async def check_channel_gate(user: User, chat_id: int, ctx: AppContext) -> bool:
    """Gate used before any "use a button" action. Returns True if allowed;
    otherwise sends the join-channel prompt itself and returns False.
    """
    lang = user.language
    if await is_channel_member(user, ctx):
        return True

    settings = await ctx.repo.get_settings()
    _, join_url = parse_channel_identifier(settings.required_channel)
    await ctx.tg.send_message(
        chat_id, t(lang, "channelGateMessage"), reply_markup=channel_gate_keyboard(lang, join_url)
    )
    return False


async def get_bot_username(ctx: AppContext) -> str:
    """Resolves the bot's @username robustly: config env var first, then a
    cached value from the DB, and finally a live getMe() call (caching the
    result for next time).
    """
    if ctx.config.bot_username:
        return ctx.config.bot_username

    cached = await ctx.repo.get_cached_bot_username()
    if cached:
        return cached

    me = await ctx.tg.get_me()
    username = getattr(me, "username", None)
    if username:
        await ctx.repo.set_cached_bot_username(username)
        return username

    return "your_bot"  # last-resort fallback so links never literally contain "undefined"
