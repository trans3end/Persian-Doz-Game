"""Direct port of keyboards.js (plus the reply/inline builder helpers
from telegram.js), using aiogram's keyboard types instead of raw dicts.
Every button layout below is unchanged from the original.
"""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from database.models import Player
from game.board import render_board_keyboard_rows
from telegram.texts import t

Btn = InlineKeyboardButton


def _ikb(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


# --- Reply keyboard builders (persistent bottom keyboard) -----------------


def reply_keyboard(rows: list[list[str]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=label) for label in row] for row in rows],
        resize_keyboard=True,
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


# --- Main menu -------------------------------------------------------------
# League button is intentionally hidden per current requirements — the
# underlying league feature still works, it's just not surfaced here.
# "Score & Rank" was replaced with "Game History" per current requirements.


def main_menu_keyboard(lang: str) -> ReplyKeyboardMarkup:
    return reply_keyboard(
        [
            [t(lang, "btnPlayFriends"), t(lang, "btnRandomMatch")],
            [t(lang, "btnHistory"), t(lang, "btnMarket"), t(lang, "btnAccount")],
            [t(lang, "btnCoinsProfile"), t(lang, "btnSupport"), t(lang, "btnOtherBots")],
            [t(lang, "btnTutorial"), t(lang, "btnLanguage")],
        ]
    )


def back_close_row(lang: str, target: str = "main") -> list[InlineKeyboardButton]:
    return [
        Btn(text=t(lang, "btnBack"), callback_data=f"menu:back:{target}"),
        Btn(text=t(lang, "btnClose"), callback_data="msg:close"),
    ]


def back_close_keyboard(
    lang: str, extra_rows: list[list[InlineKeyboardButton]] | None = None, target: str = "main"
) -> InlineKeyboardMarkup:
    return _ikb([*(extra_rows or []), back_close_row(lang, target)])


def finished_board_keyboard(lang: str) -> InlineKeyboardMarkup:
    return _ikb([[Btn(text=t(lang, "btnBack"), callback_data="menu:back:main")]])


# --- Play with Friends ------------------------------------------------------


def play_friends_inline_keyboard(lang: str) -> InlineKeyboardMarkup:
    return _ikb(
        [
            [Btn(text=t(lang, "btnChooseFriendOrGroup"), switch_inline_query="play")],
            [
                Btn(text=t(lang, "btnAddFriend"), callback_data="friend:add"),
                Btn(text=t(lang, "btnAddFriendById"), callback_data="friend:add_by_id"),
            ],
            [
                Btn(text=t(lang, "btnFriendList"), callback_data="friend:list"),
                Btn(text=t(lang, "btnFriendRequests"), callback_data="friend:requests"),
            ],
            back_close_row(lang, "main"),
        ]
    )


def friend_list_keyboard(lang: str, friends: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [
            Btn(text=f"🎮 {t(lang, 'btnPlayWith')} {f['name']}", callback_data=f"friend:invite:{f['id']}"),
            Btn(text="🗑", callback_data=f"friend:remove:{f['id']}"),
        ]
        for f in friends
    ]
    rows.append(back_close_row(lang, "play_friends"))
    return _ikb(rows)


def friend_requests_keyboard(lang: str, requests: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [
            Btn(text=f"✅ {r['name']}", callback_data=f"friend:accept:{r['fromId']}"),
            Btn(text=f"❌ {r['name']}", callback_data=f"friend:reject:{r['fromId']}"),
        ]
        for r in requests
    ]
    rows.append(back_close_row(lang, "play_friends"))
    return _ikb(rows)


def game_invite_keyboard(lang: str, from_id: int) -> InlineKeyboardMarkup:
    return _ikb(
        [
            [
                Btn(text=t(lang, "btnAcceptInvite"), callback_data=f"game:invite_accept:{from_id}"),
                Btn(text=t(lang, "btnRejectInvite"), callback_data=f"game:invite_reject:{from_id}"),
            ]
        ]
    )


def cancel_keyboard(lang: str) -> InlineKeyboardMarkup:
    return _ikb([[Btn(text=t(lang, "adminBtnCancel"), callback_data="friend:cancel_input")]])


def random_match_inline_keyboard(lang: str) -> InlineKeyboardMarkup:
    return _ikb([[Btn(text=t(lang, "btnFindOpponent"), callback_data="match:find")], back_close_row(lang, "main")])


def match_searching_keyboard(lang: str) -> InlineKeyboardMarkup:
    return _ikb([[Btn(text=t(lang, "btnCancelSearch"), callback_data="match:cancel")]])


def league_inline_keyboard(lang: str) -> InlineKeyboardMarkup:
    return _ikb(
        [[Btn(text=t(lang, "btnJoinLeague"), callback_data="league:join")], back_close_row(lang, "main")]
    )


def language_inline_keyboard() -> InlineKeyboardMarkup:
    return _ikb(
        [
            [Btn(text="🇬🇧 English", callback_data="lang:en")],
            [Btn(text="🇮🇷 فارسی", callback_data="lang:fa")],
        ]
    )


def channel_gate_keyboard(lang: str, join_url: str | None) -> InlineKeyboardMarkup:
    rows = []
    if join_url:
        rows.append([Btn(text=t(lang, "btnJoinChannel"), url=join_url)])
    rows.append([Btn(text=t(lang, "btnIJoined"), callback_data="channel:check")])
    return _ikb(rows)


def market_menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    return _ikb(
        [
            [
                Btn(text=t(lang, "btnDailyCoin"), callback_data="market:daily"),
                Btn(text=t(lang, "btnReferral"), callback_data="market:referral"),
            ],
            back_close_row(lang, "main"),
        ]
    )


# --- In-game keyboard: tappable board + Resign ------------------------------
# (The Chat feature has been removed entirely — no toggle, no button.)


def game_board_keyboard(board: list[list[int]], lang: str) -> InlineKeyboardMarkup:
    rows = [[Btn(**cell) for cell in row] for row in render_board_keyboard_rows(board)]
    rows.append([Btn(text=t(lang, "btnResign"), callback_data="game:resign")])
    return _ikb(rows)


def empty_keyboard() -> InlineKeyboardMarkup:
    return _ikb([])


def active_game_prompt_keyboard(lang: str) -> InlineKeyboardMarkup:
    return _ikb(
        [
            [
                Btn(text=t(lang, "btnResumeGame"), callback_data="gameprompt:resume"),
                Btn(text=t(lang, "btnLeaveGame"), callback_data="gameprompt:leave"),
            ]
        ]
    )


# --- Group-chat /game mode ---------------------------------------------------


def group_join_keyboard(lang: str, game_id: str) -> InlineKeyboardMarkup:
    return _ikb([[Btn(text=t(lang, "btnJoinGame"), callback_data=f"group:join:{game_id}")]])


def group_finished_keyboard(lang: str) -> InlineKeyboardMarkup:
    return _ikb([[Btn(text=t(lang, "btnNewGame"), callback_data="group:new")]])


# --- Admin panel --------------------------------------------------------------


def admin_panel_keyboard(lang: str) -> InlineKeyboardMarkup:
    return _ikb(
        [
            [
                Btn(text=t(lang, "adminBtnSupport"), callback_data="admin:set_support"),
                Btn(text=t(lang, "adminBtnChannel"), callback_data="admin:set_channel"),
            ],
            [
                Btn(text=t(lang, "adminBtnAddAll"), callback_data="admin:add_all"),
                Btn(text=t(lang, "adminBtnAddOne"), callback_data="admin:add_one"),
            ],
            [
                Btn(text=t(lang, "adminBtnReferralBonus"), callback_data="admin:set_referral"),
                Btn(text=t(lang, "adminBtnSignupBonus"), callback_data="admin:set_signup"),
            ],
            [Btn(text=t(lang, "adminBtnView"), callback_data="admin:view")],
            [Btn(text=t(lang, "adminBtnResetUser"), callback_data="admin:reset_user")],
            back_close_row(lang, "main"),
        ]
    )


def cancel_inline_keyboard(lang: str) -> InlineKeyboardMarkup:
    return _ikb([[Btn(text=t(lang, "adminBtnCancel"), callback_data="admin:cancel")]])
