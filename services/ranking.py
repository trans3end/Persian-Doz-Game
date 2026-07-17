"""Direct port of sendLeague() and sendHistory() in handlers.js."""
from __future__ import annotations

from datetime import datetime, timezone

from context import AppContext
from database.models import User
from game.engine import REASON_KEYS
from telegram.formatting import escape_html, render_leaderboard, render_record_list
from telegram.keyboards import Btn, back_close_keyboard, league_inline_keyboard
from telegram.texts import t

HISTORY_PAGE_SIZE = 5


async def send_league(chat_id: int, lang: str, ctx: AppContext) -> None:
    top = await ctx.repo.leaderboard(10)

    if not top:
        await ctx.tg.send_message(
            chat_id,
            f"<b>{t(lang, 'leagueTitle')}</b>\n{t(lang, 'leagueEmpty')}",
            reply_markup=league_inline_keyboard(lang),
        )
        return

    rows = [
        {"identifier": u.id, "score": u.score, "wins": u.wins, "losses": u.losses} for u in top
    ]
    text = render_leaderboard(t(lang, "leagueTitle"), rows)
    await ctx.tg.send_message(chat_id, text, reply_markup=league_inline_keyboard(lang))


def _result_label(lang: str, result: str) -> str:
    if result == "win":
        return t(lang, "historyResultWin")
    if result == "loss":
        return t(lang, "historyResultLoss")
    return t(lang, "historyResultDraw")


def _reason_label(lang: str, reason: str | None) -> str:
    if not reason:
        return "—"
    return t(lang, REASON_KEYS.get(reason, REASON_KEYS["connect4"]))


def _coins_label(lang: str, delta: int) -> str:
    if not delta:
        return t(lang, "coinsUnchanged")
    if delta > 0:
        return t(lang, "coinsGained", delta)
    return t(lang, "coinsLost", -delta)


async def send_history(chat_id: int, user: User, ctx: AppContext, offset: int = 0) -> None:
    lang = user.language
    entries = await ctx.repo.get_history(user.id, HISTORY_PAGE_SIZE, offset)
    total = await ctx.repo.count_history(user.id)
    leaderboard_row = [Btn(text=t(lang, "btnViewLeaderboard"), callback_data="menu:league")]

    if not entries:
        await ctx.tg.send_message(
            chat_id, t(lang, "historyEmpty"), reply_markup=back_close_keyboard(lang, [leaderboard_row])
        )
        return

    f = t(lang, "historyFields")
    records = []
    for e in entries:
        played_at = datetime.fromtimestamp(e.played_at / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        records.append(
            [
                (f["opponent"], escape_html(e.opponent_name)),
                (f["mode"], t(lang, "modeFriend") if e.mode == "friend" else t(lang, "modeRandom")),
                (f["result"], _result_label(lang, e.result)),
                (f["reason"], _reason_label(lang, e.end_reason)),
                (f["coins"], _coins_label(lang, e.coins_delta)),
                (
                    f["duration"],
                    t(lang, "durationSeconds", e.duration_seconds)
                    if e.duration_seconds is not None
                    else "—",
                ),
                (f["date"], played_at),
            ]
        )

    extra_rows = [leaderboard_row]
    next_offset = offset + len(entries)
    if next_offset < total:
        extra_rows.insert(0, [Btn(text=t(lang, "historyMore"), callback_data=f"history:more:{next_offset}")])

    text = render_record_list(t(lang, "historyTitle"), records)
    await ctx.tg.send_message(chat_id, text, reply_markup=back_close_keyboard(lang, extra_rows))
