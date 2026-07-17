"""Direct port of sendReferralInfo() and the referral-crediting branch of
handleStart() in handlers.js.
"""
from __future__ import annotations

from context import AppContext
from database.models import User
from services.channel import get_bot_username
from telegram.keyboards import back_close_keyboard
from telegram.texts import t


async def send_referral_info(chat_id: int, user: User, ctx: AppContext) -> None:
    lang = user.language
    bot_username = await get_bot_username(ctx)
    code = await ctx.repo.ensure_referral_code(user)
    link = f"https://t.me/{bot_username}?start={code}"
    r = t(lang, "referralInfo")
    settings = await ctx.repo.get_settings()

    from telegram.formatting import render_info_card

    rows = [
        (r["balance"], str(user.coins)),
        (r["invites"], str(user.invites_count)),
        (r["perInvite"], str(settings.referral_bonus)),
        (r["link"], f"<code>{link}</code>"),
    ]
    text = render_info_card(t(lang, "referralTitle"), rows)
    await ctx.tg.send_message(chat_id, text, reply_markup=back_close_keyboard(lang, [], "market"))


async def credit_referral_bonus(referrer: User, new_user: User, ctx: AppContext) -> None:
    """Called once, the first time a brand-new user's /start payload
    resolves to someone else's referral code. Credits the referrer and
    links the new user to them permanently (referred_by).
    """
    from telegram.formatting import escape_html

    settings = await ctx.repo.get_settings()
    referrer.coins += settings.referral_bonus
    referrer.invites_count = (referrer.invites_count or 0) + 1
    await ctx.repo.put_user(referrer)

    new_user.referred_by = referrer.id
    await ctx.repo.put_user(new_user)

    await ctx.tg.send_message(
        referrer.id,
        t(referrer.language, "referralBonusReceived", escape_html(new_user.name), settings.referral_bonus),
    )
