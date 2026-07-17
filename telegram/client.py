"""Thin wrapper around aiogram's Bot, exposing the same method names as
the original hand-rolled `Telegram` class in telegram.js (sendMessage,
editMessageText, editMessageReplyMarkup, answerCallbackQuery,
deleteMessage, getChatMember, setWebhook, getMe) so the ported handler
logic reads the same way call-site to call-site. Every call uses HTML
parse mode, matching the original.
"""
from __future__ import annotations

from typing import Any, Optional

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove


def make_bot(token: str) -> Bot:
    return Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


class TelegramClient:
    """ctx.tg in the original — here just `ctx.bot` used directly via these
    thin helpers, kept as a separate class so call sites don't need to know
    aiogram's exact keyword-argument names.
    """

    def __init__(self, bot: Bot):
        self.bot = bot

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup | ReplyKeyboardMarkup | ReplyKeyboardRemove] = None,
    ) -> Message:
        return await self.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
    ) -> Any:
        return await self.bot.edit_message_text(
            chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup
        )

    async def edit_message_reply_markup(
        self, chat_id: int, message_id: int, reply_markup: Optional[InlineKeyboardMarkup]
    ) -> Any:
        return await self.bot.edit_message_reply_markup(
            chat_id=chat_id, message_id=message_id, reply_markup=reply_markup
        )

    async def answer_callback_query(
        self, callback_query_id: str, text: str = "", show_alert: bool = False
    ) -> Any:
        return await self.bot.answer_callback_query(
            callback_query_id=callback_query_id, text=text or None, show_alert=show_alert
        )

    async def delete_message(self, chat_id: int, message_id: int) -> Any:
        return await self.bot.delete_message(chat_id=chat_id, message_id=message_id)

    async def get_chat_member(self, chat_id: str | int, user_id: int) -> Any:
        return await self.bot.get_chat_member(chat_id=chat_id, user_id=user_id)

    async def set_webhook(self, url: str, secret_token: Optional[str] = None) -> Any:
        return await self.bot.set_webhook(url=url, secret_token=secret_token)

    async def get_me(self) -> Any:
        return await self.bot.get_me()
