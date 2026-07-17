-- Adds group-chat /game session tracking.
CREATE TABLE IF NOT EXISTS group_games (
    chat_id    INTEGER PRIMARY KEY,
    game_id    TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
