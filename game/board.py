"""Core "Doz" (7x6 Connect-Four) game engine.

Direct port of game.js. Board is stored row-major, 6 rows x 7 columns.
Cell values: 0 = empty, 1 = player one, 2 = player two. A winning line is
additionally tracked as a list of (row, col) pairs so it can be rendered
with the diamond marker, exactly like the original.

Board size, win detection, and move validation are preserved exactly —
do not change ROWS/COLS or the win-scan algorithm below without also
updating the reference screenshots this bot was designed to match.
"""
from __future__ import annotations

from typing import Optional

ROWS = 6
COLS = 7

_DIRECTIONS = [
    (0, 1),   # horizontal
    (1, 0),   # vertical
    (1, 1),   # diagonal down-right
    (1, -1),  # diagonal down-left
]

_EMPTY_EMOJI = "⚪"
_PLAYER_EMOJIS = {1: "🔴", 2: "🔵"}
_WIN_EMOJI = "🔶"


def create_empty_board() -> list[list[int]]:
    return [[0] * COLS for _ in range(ROWS)]


def next_open_row(board: list[list[int]], col: int) -> int:
    """Returns the row index the piece will land on, or -1 if the column is full."""
    for r in range(ROWS - 1, -1, -1):
        if board[r][col] == 0:
            return r
    return -1


def is_column_full(board: list[list[int]], col: int) -> bool:
    return board[0][col] != 0


def is_board_full(board: list[list[int]]) -> bool:
    return all(cell != 0 for cell in board[0])


def apply_move(board: list[list[int]], col: int, player: int) -> Optional[tuple[int, int]]:
    """Drops `player`'s piece into `col`. Returns (row, col) or None if full."""
    row = next_open_row(board, col)
    if row == -1:
        return None
    board[row][col] = player
    return (row, col)


def check_win(board: list[list[int]], row: int, col: int) -> Optional[list[tuple[int, int]]]:
    """Checks for a 4-in-a-row that passes through (row, col).
    Returns the winning cells list, or None if no win.
    """
    player = board[row][col]
    if not player:
        return None

    for dr, dc in _DIRECTIONS:
        cells = [(row, col)]

        # walk forward
        r, c = row + dr, col + dc
        while 0 <= r < ROWS and 0 <= c < COLS and board[r][c] == player:
            cells.append((r, c))
            r += dr
            c += dc
        # walk backward
        r, c = row - dr, col - dc
        while 0 <= r < ROWS and 0 <= c < COLS and board[r][c] == player:
            cells.insert(0, (r, c))
            r -= dr
            c -= dc

        if len(cells) >= 4:
            return cells[: max(4, len(cells))]
    return None


def render_board_keyboard_rows(board: list[list[int]]) -> list[list[dict]]:
    """Renders the board as inline-keyboard button rows (text + callback_data).
    No number/sign header row — every cell in the grid itself is tappable,
    and tapping any cell in a column drops a piece into that column
    (callback_data encodes only the column).
    """
    rows = []
    for r in range(ROWS):
        row_buttons = []
        for c in range(COLS):
            cell = board[r][c]
            emoji = _PLAYER_EMOJIS[cell] if cell else _EMPTY_EMOJI
            row_buttons.append({"text": emoji, "callback_data": f"move:{c}"})
        rows.append(row_buttons)
    return rows


def render_board_text(
    board: list[list[int]], winning_cells: Optional[list[tuple[int, int]]] = None
) -> str:
    """Plain-text rendering of the final board (with the winning line
    marked), used in the game-over result message.
    """
    win_set = set(winning_cells or [])
    lines = []
    for r in range(ROWS):
        line = ""
        for c in range(COLS):
            cell = board[r][c]
            if (r, c) in win_set:
                line += _WIN_EMOJI
            elif cell:
                line += _PLAYER_EMOJIS[cell]
            else:
                line += _EMPTY_EMOJI
        lines.append(line)
    return "\n".join(lines)
