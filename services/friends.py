"""Direct port of the friend-request logic in handlers.js
(createFriendRequest + the friend:* callback bodies)."""
from __future__ import annotations

from aiogram.types import CallbackQuery

from context import AppContext
from database.models import User
from telegram.formatting import escape_html
from telegram.texts import t


async def create_friend_request(requester_id: int, target_id: int, ctx: AppContext) -> None:
    """Creates (or resolves) a friend request from `requester_id` to
    `target_id`. Used by both the "Add Friend by ID" flow and invitation
    links, so both paths go through the exact same request/accept system
    rather than one of them silently direct-adding.
    """
    if requester_id == target_id:
        return

    requester = await ctx.repo.get_user(requester_id)
    target = await ctx.repo.get_user(target_id)
    if not requester or not target:
        return

    if target_id in requester.friends:
        await ctx.tg.send_message(requester_id, t(requester.language, "cannotAddExistingFriend"))
        return

    # Already sent this exact request? Don't spam another row / message.
    existing = await ctx.repo.get_friend_request(requester_id, target_id)
    if existing:
        await ctx.tg.send_message(
            requester_id,
            t(requester.language, "friendRequestAlreadySent", escape_html(target.name)),
        )
        return

    # The other side already asked first — treat this as mutual acceptance
    # instead of leaving two redundant pending requests sitting around.
    reciprocal = await ctx.repo.get_friend_request(target_id, requester_id)
    if reciprocal:
        await ctx.repo.add_friends(requester_id, target_id)
        await ctx.repo.remove_friend_request(target_id, requester_id)
        await ctx.tg.send_message(requester_id, t(requester.language, "friendAccepted", escape_html(target.name)))
        await ctx.tg.send_message(target_id, t(target.language, "friendAccepted", escape_html(requester.name)))
        return

    await ctx.repo.add_friend_request(requester_id, target_id)
    await ctx.tg.send_message(requester_id, t(requester.language, "friendRequestSent", escape_html(target.name)))

    from telegram.keyboards import Btn, InlineKeyboardMarkup

    await ctx.tg.send_message(
        target_id,
        t(target.language, "friendRequestReceivedButtons", escape_html(requester.name)),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    Btn(text="✅", callback_data=f"friend:accept:{requester_id}"),
                    Btn(text="❌", callback_data=f"friend:reject:{requester_id}"),
                ]
            ]
        ),
    )


# ---------------------------------------------------------------------
# Callback bodies for friend:list / friend:requests / friend:accept /
# friend:reject / friend:remove / friend:add / friend:add_by_id /
# friend:cancel_input
# ---------------------------------------------------------------------


async def show_friend_list(cq: CallbackQuery, user: User, ctx: AppContext) -> None:
    from telegram.keyboards import back_close_keyboard, friend_list_keyboard

    chat_id = cq.message.chat.id
    lang = user.language
    await ctx.tg.answer_callback_query(cq.id)

    if not user.friends:
        await ctx.tg.send_message(chat_id, t(lang, "noFriendsYet"), reply_markup=back_close_keyboard(lang))
        return

    friends = []
    for fid in user.friends:
        f = await ctx.repo.get_user(fid)
        friends.append({"id": fid, "name": f.name if f else str(fid)})
    await ctx.tg.send_message(chat_id, t(lang, "friendListTitle"), reply_markup=friend_list_keyboard(lang, friends))


async def show_friend_requests(cq: CallbackQuery, user: User, ctx: AppContext) -> None:
    from telegram.keyboards import back_close_keyboard, friend_requests_keyboard

    chat_id = cq.message.chat.id
    lang = user.language
    await ctx.tg.answer_callback_query(cq.id)

    reqs = await ctx.repo.list_friend_requests(user.id)
    if not reqs:
        await ctx.tg.send_message(chat_id, t(lang, "noRequestsYet"), reply_markup=back_close_keyboard(lang))
        return

    with_names = []
    for r in reqs:
        f = await ctx.repo.get_user(r.from_id)
        with_names.append({"fromId": r.from_id, "name": f.name if f else str(r.from_id)})
    await ctx.tg.send_message(
        chat_id, t(lang, "friendRequestsTitle"), reply_markup=friend_requests_keyboard(lang, with_names)
    )


async def accept_friend_request(cq: CallbackQuery, user: User, from_id: int, ctx: AppContext) -> None:
    chat_id = cq.message.chat.id
    lang = user.language

    await ctx.repo.add_friends(from_id, user.id)
    await ctx.repo.remove_friend_request(from_id, user.id)
    await ctx.tg.answer_callback_query(cq.id, t(lang, "friendAcceptedToast"))

    requester = await ctx.repo.get_user(from_id)
    await ctx.tg.send_message(chat_id, t(lang, "friendAccepted", escape_html(requester.name if requester else "—")))
    if requester:
        await ctx.tg.send_message(requester.id, t(requester.language, "friendAccepted", escape_html(user.name)))


async def reject_friend_request(cq: CallbackQuery, user: User, from_id: int, ctx: AppContext) -> None:
    lang = user.language

    await ctx.repo.remove_friend_request(from_id, user.id)
    await ctx.tg.answer_callback_query(cq.id)

    requester = await ctx.repo.get_user(from_id)
    if requester:
        await ctx.tg.send_message(requester.id, t(requester.language, "friendRejectedNotice", escape_html(user.name)))


async def remove_friend(cq: CallbackQuery, user: User, friend_id: int, ctx: AppContext) -> None:
    from telegram.keyboards import back_close_keyboard, friend_list_keyboard

    chat_id = cq.message.chat.id
    lang = user.language

    await ctx.repo.remove_friend(user.id, friend_id)
    friend_user = await ctx.repo.get_user(friend_id)
    await ctx.tg.answer_callback_query(cq.id, t(lang, "friendRemoved", friend_user.name if friend_user else str(friend_id)))

    refreshed = await ctx.repo.get_user(user.id)
    updated_friends = []
    for fid in refreshed.friends:
        f = await ctx.repo.get_user(fid)
        updated_friends.append({"id": fid, "name": f.name if f else str(fid)})

    if not updated_friends:
        await ctx.tg.edit_message_text(
            chat_id,
            cq.message.message_id,
            t(lang, "noFriendsYet"),
            reply_markup=back_close_keyboard(lang, [], "play_friends"),
        )
    else:
        await ctx.tg.edit_message_reply_markup(chat_id, cq.message.message_id, friend_list_keyboard(lang, updated_friends))


async def start_add_friend_link(cq: CallbackQuery, user: User, ctx: AppContext) -> None:
    from services.channel import get_bot_username

    chat_id = cq.message.chat.id
    lang = user.language
    bot_username = await get_bot_username(ctx)
    link = f"https://t.me/{bot_username}?start=friend_{user.id}"
    await ctx.tg.answer_callback_query(cq.id)
    await ctx.tg.send_message(chat_id, t(lang, "sendInviteLinkPrompt") + f"\n<code>{link}</code>")


async def start_add_friend_by_id(cq: CallbackQuery, user: User, ctx: AppContext) -> None:
    from telegram.keyboards import cancel_keyboard

    chat_id = cq.message.chat.id
    lang = user.language
    await ctx.repo.set_user_state(user.id, "add_friend_by_id")
    await ctx.tg.answer_callback_query(cq.id)
    await ctx.tg.send_message(chat_id, t(lang, "askFriendId"), reply_markup=cancel_keyboard(lang))


async def cancel_add_friend_input(cq: CallbackQuery, user: User, ctx: AppContext) -> None:
    from telegram.keyboards import empty_keyboard, main_menu_keyboard

    chat_id = cq.message.chat.id
    lang = user.language
    await ctx.repo.clear_user_state(user.id)
    await ctx.tg.answer_callback_query(cq.id, t(lang, "adminCanceled"))
    # Close the "send me the ID" prompt itself (remove its inline keyboard)
    # so the dialog visibly ends instead of sitting there unchanged...
    await ctx.tg.edit_message_reply_markup(chat_id, cq.message.message_id, empty_keyboard())
    # ...and land the user back on the main menu rather than nowhere.
    await ctx.tg.send_message(chat_id, t(lang, "mainMenuTitle"), reply_markup=main_menu_keyboard(lang))


async def handle_add_friend_by_id_text(text: str, chat_id: int, user: User, ctx: AppContext) -> None:
    """Handles the typed reply after start_add_friend_by_id set the
    pending user_state."""
    lang = user.language
    stripped = text.strip()
    try:
        target_id = int(stripped)
        if str(target_id) != stripped.lstrip("+"):
            raise ValueError
    except ValueError:
        from telegram.keyboards import cancel_keyboard

        await ctx.tg.send_message(chat_id, t(lang, "adminInvalidNumber"), reply_markup=cancel_keyboard(lang))
        return

    if target_id == user.id:
        await ctx.repo.clear_user_state(user.id)
        await ctx.tg.send_message(chat_id, t(lang, "cannotAddSelf"))
        return

    target_user = await ctx.repo.get_user(target_id)
    if not target_user:
        from telegram.keyboards import cancel_keyboard

        await ctx.tg.send_message(chat_id, t(lang, "noSuchUser"), reply_markup=cancel_keyboard(lang))
        return

    await ctx.repo.clear_user_state(user.id)
    await create_friend_request(user.id, target_id, ctx)
