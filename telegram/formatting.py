"""Direct port of format.js and escapeHtml() from telegram.js.

Telegram doesn't support real HTML tables, and monospace box-drawing
characters break alignment when mixed with Persian/RTL text. So instead
of faking a grid, these render a clean vertical list — no box-drawing
grid anywhere, so there's nothing for the bidi engine to misalign.
"""
from __future__ import annotations

from typing import Any, Sequence


def escape_html(value: Any) -> str:
    """Escapes text that will be embedded in an HTML-parse-mode message."""
    s = "" if value is None else str(value)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_info_card(title: str, rows: Sequence[tuple[str, str]]) -> str:
    lines = [f"▫️ <b>{escape_html(label)}:</b> {value}" for label, value in rows]
    title_line = f"<b>{escape_html(title)}</b>\n{'─' * 18}\n" if title else ""
    return f"{title_line}{chr(10).join(lines)}"


def render_record_list(title: str, records: Sequence[Sequence[tuple[str, str]]]) -> str:
    """records: list of "field lists" (game history, etc.) rendered as
    numbered blocks rather than a grid, for the same RTL-safety reason as
    render_info_card.
    """
    blocks = []
    for i, fields in enumerate(records):
        lines = [f"   ▫️ {escape_html(label)}: {value}" for label, value in fields]
        blocks.append(f"<b>{i + 1}.</b>\n" + "\n".join(lines))
    title_line = f"<b>{escape_html(title)}</b>\n{'─' * 18}\n\n" if title else ""
    return title_line + "\n\n".join(blocks)


_MEDALS = ["🥇", "🥈", "🥉"]


def render_leaderboard(title: str, rows: Sequence[dict]) -> str:
    """rows: sequence of {"identifier", "score", "wins", "losses"}, already
    sorted. Players are identified by numeric user ID only, never their
    username or free-text display name.
    """
    lines = []
    for i, r in enumerate(rows):
        rank = _MEDALS[i] if i < len(_MEDALS) else f"{i + 1}."
        lines.append(
            f"{rank} <b>ID:</b> {escape_html(r['identifier'])}   "
            f"<b>Score:</b> {r['score']}   <b>W:</b> {r['wins']}   <b>L:</b> {r['losses']}"
        )
    title_line = f"<b>{escape_html(title)}</b>\n{'─' * 18}\n\n" if title else ""
    return f"{title_line}{chr(10).join(lines)}"
