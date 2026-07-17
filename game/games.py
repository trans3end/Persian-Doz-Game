"""Core game orchestration — direct port of the game-lifecycle functions
in handlers.js: startGame, handleMove, finishGame,
finishGroupGameMessage, resignActiveGame, handleResumeGamePrompt,
handleLeaveGamePrompt, the group-chat /game flow, the friend-invite
accept/reject flow, and the two Durable-Object callback entry points
(notifyTurnWarning / applyTurnTimeout), now wired to game/timer.py instead.
"""
from __future__ import annotations

import logging

from aiogram.types import CallbackQuery, Message

from context import AppContext
from database.models import Game, Player, User
from database.utils import new_game_id, now_ms
from game.board import apply_move, check_win, is_board_full, render_board_text
from game.engine import REASON_KEYS, new_group_waiting_game, new_two_player_game
from telegram.formatting import escape_html
from telegram.keyboards import (
    active_game_prompt_keyboard,
    empty_keyboard,
    finished_board_keyboard,
    game_board_keyboard,
    group_finished_keyboard,
    group_join_keyboard,
    main_menu_keyboard,
    remove_keyboard,
)
from telegram.texts import t

logger = logging.getLogger(__name__)

COLOR_EMOJI = {1: "🔴", 2: "🔵"}


# ---------------------------------------------------------------------
# Board message builders
# ---------------------------------------------------------------------


def build_board_message(p: Player, opponent: Player, game: Game) -> str:
    """Builds the persistent "You (Name Color) VS Opponent (Name Color)"
    header plus whose-turn line, shown both when the game starts and
    after every move so this info never disappears from the board message.
    """
    my_color = COLOR_EMOJI[p.symbol]
    opp_color = COLOR_EMOJI[opponent.symbol]
    opp_name = escape_html(opponent.name)
    header = t(p.lang, "modeFriend") if game.mode == "friend" else t(p.lang, "modeRandom")
    board_header = t(p.lang, "boardHeader", escape_html(p.name), my_color, opp_name, opp_color)
    is_your_turn = p.symbol == game.turn
    turn_line = f"{t(p.lang, 'yourTurn')} {my_color}" if is_your_turn else t(p.lang, "waitingForOpponent")
    return f"{header}\n\n{board_header}\n\n{turn_line}"


def build_group_board_message(game: Game, lang: str) -> str:
    """Group-chat games are ONE shared message that every member of the
    group sees the same way — there's no single "you", so this uses
    neutral "PlayerA (color) vs PlayerB (color)" phrasing instead of
    build_board_message's "You vs opponent" framing.
    """
    p1, p2 = game.players
    c1, c2 = COLOR_EMOJI[p1.symbol], COLOR_EMOJI[p2.symbol]
    vs_line = t(lang, "groupVsLine", escape_html(p1.name), c1, escape_html(p2.name), c2)
    active = game.player_by_symbol(game.turn)
    turn_line = t(lang, "groupTurnLine", escape_html(active.name), COLOR_EMOJI[active.symbol])
    return f"{t(lang, 'modeGroup')}\n\n{vs_line}\n\n{turn_line}"


# ---------------------------------------------------------------------
# Starting a 1v1 (friend / random) game
# ---------------------------------------------------------------------


async def start_game(player_a: Player, player_b: Player, mode: str, ctx: AppContext) -> Game:
    game = new_two_player_game(player_a, player_b, mode)

    for idx, p in enumerate(game.players):
        # Hide the persistent bottom keyboard while a game is active — chat
        # and resign are now inline buttons under the board instead.
        await ctx.tg.send_message(p.chat_id, t(p.lang, "newGameCreated"), reply_markup=remove_keyboard())

        opponent = game.players[1 if idx == 0 else 0]
        msg_text = build_board_message(p, opponent, game)

        sent = await ctx.tg.send_message(p.chat_id, msg_text, reply_markup=game_board_keyboard(game.board, p.lang))
        game.players[idx].message_id = sent.message_id
        await ctx.repo.set_active_game(p.id, game.id)

    await ctx.repo.put_game(game)
    ctx.timers.schedule(game.id, game.move_count)
    return game


# ---------------------------------------------------------------------
# Making a move
# ---------------------------------------------------------------------


async def handle_move(cq: CallbackQuery, user: User, col: int, ctx: AppContext) -> None:
    lang = user.language

    game_id = await ctx.repo.get_active_game_id(user.id)
    if not game_id:
        await ctx.tg.answer_callback_query(cq.id)
        return
    game = await ctx.repo.get_game(game_id)
    if not game or game.status != "active":
        await ctx.tg.answer_callback_query(cq.id)
        return

    me = game.find_player(user.id)
    opponent = game.opponent_of(user.id)

    if game.turn != me.symbol:
        await ctx.tg.answer_callback_query(cq.id, t(lang, "notYourTurn"), True)
        return

    move_result = apply_move(game.board, col, me.symbol)
    if not move_result:
        await ctx.tg.answer_callback_query(cq.id, t(lang, "invalidMove"), True)
        return
    await ctx.tg.answer_callback_query(cq.id)

    row, move_col = move_result
    win_cells = check_win(game.board, row, move_col)
    board_full = not win_cells and is_board_full(game.board)

    if win_cells:
        game.status = "finished"
        await finish_game(game, winner_symbol=me.symbol, win_cells=win_cells, reason="connect4", ctx=ctx)
        return

    if board_full:
        game.status = "finished"
        await finish_game(game, winner_symbol=None, win_cells=None, reason="draw", ctx=ctx)
        return

    game.turn = opponent.symbol
    game.move_count = (game.move_count or 0) + 1
    game.turn_started_at = now_ms()
    await ctx.repo.put_game(game)
    ctx.timers.schedule(game.id, game.move_count)

    if game.mode == "group":
        p1 = game.players[0]
        msg_text = build_group_board_message(game, p1.lang)
        if p1.message_id:
            await ctx.tg.edit_message_text(
                p1.chat_id, p1.message_id, msg_text, reply_markup=game_board_keyboard(game.board, p1.lang)
            )
        return

    for p in game.players:
        opp = game.opponent_of(p.id)
        msg_text = build_board_message(p, opp, game)
        if p.message_id:
            await ctx.tg.edit_message_text(
                p.chat_id, p.message_id, msg_text, reply_markup=game_board_keyboard(game.board, p.lang)
            )


# ---------------------------------------------------------------------
# Ending a game
# ---------------------------------------------------------------------


async def finish_game(
    game: Game,
    *,
    winner_symbol: int | None,
    win_cells: list[tuple[int, int]] | None,
    reason: str,
    ctx: AppContext,
) -> None:
    ctx.timers.cancel(game.id)

    for p in game.players:
        await ctx.repo.clear_active_game(p.id)
    await ctx.repo.delete_game(game.id)

    winner = game.player_by_symbol(winner_symbol) if winner_symbol else None
    board_text = render_board_text(game.board, win_cells)
    duration_seconds = max(0, round((now_ms() - (game.created_at or now_ms())) / 1000))

    is_group = game.mode == "group"
    per_player_results = []  # collected for the single combined group message, if needed

    for p in game.players:
        try:
            # Remove the tappable board once the game has ended, replacing
            # it with a single Back button rather than leaving no buttons
            # at all. (For group games this happens once, after the loop,
            # on the one shared message — not per player.)
            if not is_group and p.message_id:
                await ctx.tg.edit_message_reply_markup(p.chat_id, p.message_id, finished_board_keyboard(p.lang))

            opponent = game.opponent_of(p.id)

            user_record: User | None = None
            result = "draw" if not winner else ("win" if winner.id == p.id else "loss")
            coins_delta = 0
            try:
                user_record = await ctx.repo.get_user(p.id)
                if user_record:
                    before = user_record.coins
                    if not winner:
                        user_record.draws += 1
                    elif winner.id == p.id:
                        user_record.wins += 1
                        user_record.score += 30
                        user_record.coins += 50
                    else:
                        user_record.losses += 1
                        user_record.coins = max(0, user_record.coins - 50)
                    coins_delta = user_record.coins - before
                    await ctx.repo.put_user(user_record)
            except Exception:
                # Never let a coin/profile write failure stop the result
                # message from reaching this player (or block the other
                # player's loop iteration below).
                logger.exception("finish_game: failed to update user record %s", p.id)

            if coins_delta > 0:
                coins_line = t(p.lang, "coinsGained", coins_delta)
            elif coins_delta < 0:
                coins_line = t(p.lang, "coinsLost", -coins_delta)
            else:
                coins_line = t(p.lang, "coinsUnchanged")

            per_player_results.append(
                {
                    "player": p,
                    "result": result,
                    "coinsLine": coins_line,
                    "balance": user_record.coins if user_record else "—",
                }
            )

            if not is_group:
                from types import SimpleNamespace

                opponent_info = SimpleNamespace(
                    name=escape_html(opponent.name),
                    mode=t(p.lang, "modeFriend") if game.mode == "friend" else t(p.lang, "modeRandom"),
                    reason=t(p.lang, REASON_KEYS.get(reason, REASON_KEYS["connect4"])),
                    coinsLine=coins_line,
                    balance=user_record.coins if user_record else "—",
                )

                if not winner:
                    result_text = t(p.lang, "gameResultDraw", opponent_info)
                elif winner.id == p.id:
                    result_text = t(p.lang, "gameResultWin", opponent_info)
                else:
                    result_text = t(p.lang, "gameResultLoss", opponent_info)
                result_text += f"\n\n<pre>{board_text}</pre>"

                # Both players must see this — send it before the
                # (non-critical) history write below, so a history-table
                # problem can never prevent either side from getting their
                # result notification.
                await ctx.tg.send_message(p.chat_id, result_text, reply_markup=main_menu_keyboard(p.lang))

            if user_record:
                try:
                    await ctx.repo.add_history_entry(
                        user_id=p.id,
                        opponent_name=opponent.name,
                        mode=game.mode,
                        result=result,
                        end_reason=reason,
                        coins_delta=coins_delta,
                        duration_seconds=duration_seconds,
                        board_snapshot=board_text,
                        played_at=now_ms(),
                    )
                except Exception:
                    logger.exception("finish_game: failed to record history entry %s", p.id)
        except Exception:
            # Whatever goes wrong for this player, still process the other one.
            logger.exception("finish_game: failed to finalize result for player %s", p.id)

    if is_group:
        await ctx.repo.clear_group_game(game.players[0].chat_id)
        await _finish_group_game_message(game, winner, reason, board_text, per_player_results, ctx)


async def _finish_group_game_message(
    game: Game, winner: Player | None, reason: str, board_text: str, per_player_results: list[dict], ctx: AppContext
) -> None:
    """Posts ONE combined result into the group chat (both players' names,
    coin changes, and the final board) and replaces the shared board
    message's buttons with a "New Game" button.
    """
    p1 = game.players[0]
    lang = p1.lang
    chat_id = p1.chat_id

    lines = []
    for r in per_player_results:
        if r["result"] == "win":
            label = t(lang, "historyResultWin")
        elif r["result"] == "loss":
            label = t(lang, "historyResultLoss")
        else:
            label = t(lang, "historyResultDraw")
        lines.append(f"{escape_html(r['player'].name)}: {label} ({r['coinsLine']})")

    reason_line = t(lang, REASON_KEYS.get(reason, REASON_KEYS["connect4"]))
    result_text = (
        f"{t(lang, 'modeGroup')}\n\n{chr(10).join(lines)}\n\n{t(lang, 'historyFields')['reason']}: {reason_line}"
        f"\n\n<pre>{board_text}</pre>"
    )

    if p1.message_id:
        await ctx.tg.edit_message_reply_markup(chat_id, p1.message_id, group_finished_keyboard(lang))
    await ctx.tg.send_message(chat_id, result_text)


# ---------------------------------------------------------------------
# Timer callbacks (replace notifyTurnWarning / applyTurnTimeout from the
# GameTimerDO Durable Object)
# ---------------------------------------------------------------------


async def notify_turn_warning(game_id: str, expected_move_count: int, ctx: AppContext) -> bool:
    """Called ~60s into a turn (30s left on the 90s clock). Returns True if
    the game is still on this exact turn (so the timer manager knows to
    arm the follow-up timeout), False if it's stale.
    """
    game = await ctx.repo.get_game(game_id)
    if not game or game.status != "active" or (game.move_count or 0) != expected_move_count:
        return False

    active = game.player_by_symbol(game.turn)
    if active:
        await ctx.tg.send_message(active.chat_id, t(active.lang, "turnTimeWarning"))
    return True


async def apply_turn_timeout(game_id: str, expected_move_count: int, ctx: AppContext) -> None:
    """Called 90s into a turn with no move made. Ends the game: whoever's
    turn it was auto-loses, their opponent auto-wins.
    """
    game = await ctx.repo.get_game(game_id)
    if not game or game.status != "active" or (game.move_count or 0) != expected_move_count:
        return

    timed_out = game.player_by_symbol(game.turn)
    winner = next((p for p in game.players if p.symbol != game.turn), None)
    if not timed_out or not winner:
        return

    game.status = "finished"
    await finish_game(game, winner_symbol=winner.symbol, win_cells=None, reason="timeout", ctx=ctx)


# ---------------------------------------------------------------------
# Resign / resume / leave (active-game prompt)
# ---------------------------------------------------------------------


async def resign_active_game(user: User, chat_id: int, ctx: AppContext) -> None:
    game_id = await ctx.repo.get_active_game_id(user.id)
    if not game_id:
        await ctx.tg.send_message(chat_id, t(user.language, "mainMenuTitle"), reply_markup=main_menu_keyboard(user.language))
        return
    game = await ctx.repo.get_game(game_id)
    if not game or game.status != "active":
        return

    opponent = game.opponent_of(user.id)
    game.status = "finished"
    await finish_game(game, winner_symbol=opponent.symbol, win_cells=None, reason="resign", ctx=ctx)


async def handle_resume_game_prompt(cq: CallbackQuery, user: User, ctx: AppContext) -> None:
    """User tapped "Resume": re-sends the board as a fresh message (its old
    message may be buried) and points the game's tracked message_id at it
    so future move edits land on the right message.
    """
    chat_id = cq.message.chat.id
    lang = user.language

    game_id = await ctx.repo.get_active_game_id(user.id)
    game = await ctx.repo.get_game(game_id) if game_id else None
    if not game or game.status != "active":
        await ctx.tg.answer_callback_query(cq.id)
        await ctx.tg.send_message(chat_id, t(lang, "mainMenuTitle"), reply_markup=main_menu_keyboard(lang))
        return

    await ctx.tg.answer_callback_query(cq.id)

    me = game.find_player(user.id)
    opponent = game.opponent_of(user.id)
    msg_text = build_board_message(me, opponent, game)

    sent = await ctx.tg.send_message(chat_id, msg_text, reply_markup=game_board_keyboard(game.board, me.lang))
    me.message_id = sent.message_id
    await ctx.repo.put_game(game)


async def handle_leave_game_prompt(cq: CallbackQuery, user: User, ctx: AppContext) -> None:
    """User tapped "Leave": counts as a loss for them exactly like
    resigning — the opponent wins, 50 coins move from the leaver to the
    winner, and the result is recorded/sent via the normal finish_game flow.
    """
    chat_id = cq.message.chat.id
    lang = user.language

    game_id = await ctx.repo.get_active_game_id(user.id)
    game = await ctx.repo.get_game(game_id) if game_id else None
    if not game or game.status != "active":
        await ctx.tg.answer_callback_query(cq.id)
        await ctx.tg.send_message(chat_id, t(lang, "mainMenuTitle"), reply_markup=main_menu_keyboard(lang))
        return

    opponent = game.opponent_of(user.id)
    game.status = "finished"

    await ctx.tg.answer_callback_query(cq.id)
    await finish_game(game, winner_symbol=opponent.symbol, win_cells=None, reason="leave", ctx=ctx)


# ---------------------------------------------------------------------
# Friend-game invites (accept / reject; "invite" itself lives alongside
# the rest of the friend-list logic in services/friends.py)
# ---------------------------------------------------------------------


async def handle_friend_invite(cq: CallbackQuery, user: User, friend_id: int, ctx: AppContext) -> None:
    chat_id = cq.message.chat.id
    lang = user.language

    if friend_id not in user.friends:
        await ctx.tg.answer_callback_query(cq.id)
        return

    my_game = await ctx.repo.get_active_game_id(user.id)
    if my_game:
        await ctx.tg.answer_callback_query(cq.id, t(lang, "inGameAlready"), True)
        return
    friend_game = await ctx.repo.get_active_game_id(friend_id)
    if friend_game:
        await ctx.tg.answer_callback_query(cq.id, t(lang, "friendBusy"), True)
        return

    friend_user = await ctx.repo.get_user(friend_id)
    if not friend_user:
        await ctx.tg.answer_callback_query(cq.id)
        return

    from telegram.keyboards import game_invite_keyboard

    await ctx.repo.add_game_invite(user.id, friend_id)
    await ctx.tg.answer_callback_query(cq.id)
    await ctx.tg.send_message(chat_id, t(lang, "gameInviteSent", escape_html(friend_user.name)))
    await ctx.tg.send_message(
        friend_user.id,
        t(friend_user.language, "gameInviteReceived", escape_html(user.name)),
        reply_markup=game_invite_keyboard(friend_user.language, user.id),
    )


async def handle_game_invite_accept(cq: CallbackQuery, user: User, from_id: int, ctx: AppContext) -> None:
    chat_id = cq.message.chat.id
    lang = user.language

    invite = await ctx.repo.get_game_invite(from_id, user.id)
    if not invite:
        await ctx.tg.answer_callback_query(cq.id, t(lang, "gameInviteExpired"), True)
        return
    await ctx.repo.remove_game_invite(from_id, user.id)

    # Guard against a race where either side started/joined another game
    # between the invite being sent and being accepted.
    if await ctx.repo.get_active_game_id(from_id) or await ctx.repo.get_active_game_id(user.id):
        await ctx.tg.answer_callback_query(cq.id, t(lang, "friendBusy"), True)
        return

    from_user = await ctx.repo.get_user(from_id)
    if not from_user:
        await ctx.tg.answer_callback_query(cq.id)
        return

    await ctx.tg.answer_callback_query(cq.id, t(lang, "gameInviteAccepted"))
    await ctx.tg.edit_message_reply_markup(chat_id, cq.message.message_id, empty_keyboard())

    await start_game(
        Player(id=from_user.id, name=from_user.name, lang=from_user.language, chat_id=from_user.id, symbol=0),
        Player(id=user.id, name=user.name, lang=lang, chat_id=chat_id, symbol=0),
        "friend",
        ctx,
    )


async def handle_game_invite_reject(cq: CallbackQuery, user: User, from_id: int, ctx: AppContext) -> None:
    chat_id = cq.message.chat.id
    lang = user.language

    await ctx.repo.remove_game_invite(from_id, user.id)
    await ctx.tg.answer_callback_query(cq.id, t(lang, "gameInviteRejectedByYou"))
    await ctx.tg.edit_message_reply_markup(chat_id, cq.message.message_id, empty_keyboard())

    from_user = await ctx.repo.get_user(from_id)
    if from_user:
        await ctx.tg.send_message(
            from_user.id, t(from_user.language, "gameInviteRejectedNotice", escape_html(user.name))
        )


# ---------------------------------------------------------------------
# Group-chat /game mode
# ---------------------------------------------------------------------


async def handle_group_command(msg: Message, user: User, ctx: AppContext) -> None:
    await start_group_waiting_game(msg.chat.id, user, ctx)


async def start_group_waiting_game(chat_id: int, user: User, ctx: AppContext) -> None:
    lang = user.language

    existing_game_id = await ctx.repo.get_group_game_id(chat_id)
    if existing_game_id:
        existing = await ctx.repo.get_game(existing_game_id)
        if existing and existing.status in ("active", "waiting"):
            await ctx.tg.send_message(chat_id, t(lang, "groupAlreadyActive"))
            return

    already_in_a_game = await ctx.repo.get_active_game_id(user.id)
    if already_in_a_game:
        await ctx.tg.send_message(chat_id, t(lang, "inGameAlready"))
        return

    host = Player(id=user.id, name=user.name, lang=lang, chat_id=chat_id, symbol=1)
    game = new_group_waiting_game(host)

    sent = await ctx.tg.send_message(
        chat_id, t(lang, "groupWaitingMessage", escape_html(user.name)), reply_markup=group_join_keyboard(lang, game.id)
    )
    game.players[0].message_id = sent.message_id

    await ctx.repo.put_game(game)
    await ctx.repo.set_group_game(chat_id, game.id)
    await ctx.repo.set_active_game(user.id, game.id)


async def handle_group_join(cq: CallbackQuery, joining_user: User, ctx: AppContext) -> None:
    chat_id = cq.message.chat.id
    game_id = cq.data.split(":")[2]
    lang = joining_user.language

    game = await ctx.repo.get_game(game_id)
    if not game or game.status != "waiting":
        await ctx.tg.answer_callback_query(cq.id, t(lang, "groupSlotsFull"), True)
        return
    if game.players[0].id == joining_user.id:
        await ctx.tg.answer_callback_query(cq.id, t(lang, "groupCannotJoinSelf"), True)
        return
    joining_user_busy = await ctx.repo.get_active_game_id(joining_user.id)
    if joining_user_busy:
        await ctx.tg.answer_callback_query(cq.id, t(lang, "inGameAlready"), True)
        return

    await ctx.tg.answer_callback_query(cq.id)

    game.players.append(
        Player(
            id=joining_user.id,
            name=joining_user.name,
            lang=lang,
            chat_id=chat_id,
            symbol=2,
            message_id=game.players[0].message_id,
        )
    )
    game.status = "active"
    game.turn_started_at = now_ms()
    await ctx.repo.put_game(game)
    await ctx.repo.set_active_game(joining_user.id, game_id)

    p1_lang = game.players[0].lang
    board_msg_text = build_group_board_message(game, p1_lang)
    if game.players[0].message_id:
        await ctx.tg.edit_message_text(
            chat_id, game.players[0].message_id, board_msg_text, reply_markup=game_board_keyboard(game.board, p1_lang)
        )
    ctx.timers.schedule(game_id, game.move_count)


async def handle_group_new_game(cq: CallbackQuery, user: User, ctx: AppContext) -> None:
    chat_id = cq.message.chat.id
    await ctx.tg.answer_callback_query(cq.id)
    await start_group_waiting_game(chat_id, user, ctx)
