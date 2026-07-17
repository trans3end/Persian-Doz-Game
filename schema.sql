-- Persian Doz Bot — SQLite schema.
--
-- Converted from the original Cloudflare D1 tables referenced throughout
-- store.js, plus the four incremental migrations that were applied to the
-- live D1 database over time (referenced in store.js's try/catch
-- "no such column" fallbacks):
--   001_add_channel_verified_at.sql      -> users.channel_verified_at
--   002_add_daily_history_invites.sql    -> users.last_daily_claim_at,
--                                           users.invites_count,
--                                           game_invites table
--   003_add_move_timer_and_history_details.sql
--                                        -> games.move_count / turn_started_at,
--                                           game_history.end_reason /
--                                           coins_delta / duration_seconds /
--                                           board_snapshot
--   004_add_group_games.sql              -> group_games table
--
-- Since this is a fresh SQLite database (not an old D1 one being migrated
-- forward), every column from every migration is included from the start —
-- there's no "old" schema to fall back to, so the repository layer does
-- not need store.js's defensive try/catch-and-retry-with-old-columns
-- logic. See database/migrations/ for these as separate, ordered files
-- (applied in sequence by database/repository.py on startup) if you'd
-- rather evolve an existing deployment incrementally instead of using
-- this consolidated file directly.

PRAGMA foreign_keys = ON;

-- ---- Settings (admin-configurable key/value store) ------------------------
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL  -- JSON-encoded value
);

-- ---- Misc bot metadata (currently just the cached @username) --------------
CREATE TABLE IF NOT EXISTS bot_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- ---- Admin conversational state (one pending action per admin) ------------
CREATE TABLE IF NOT EXISTS admin_state (
    admin_id   INTEGER PRIMARY KEY,
    action     TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

-- ---- Generic per-user conversational state (e.g. "add friend by ID") ------
CREATE TABLE IF NOT EXISTS user_state (
    user_id    INTEGER PRIMARY KEY,
    action     TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

-- ---- Users ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id                   INTEGER PRIMARY KEY,          -- Telegram user id
    name                 TEXT NOT NULL,
    username             TEXT,
    username_visible     INTEGER NOT NULL DEFAULT 1,   -- 0/1
    language             TEXT NOT NULL DEFAULT 'fa',   -- 'fa' | 'en'
    score                INTEGER NOT NULL DEFAULT 0,
    coins                INTEGER NOT NULL DEFAULT 0,
    wins                 INTEGER NOT NULL DEFAULT 0,
    losses               INTEGER NOT NULL DEFAULT 0,
    draws                INTEGER NOT NULL DEFAULT 0,
    invites_count        INTEGER NOT NULL DEFAULT 0,
    referral_code        TEXT UNIQUE,
    referred_by          INTEGER,
    channel_verified_at  INTEGER,
    last_daily_claim_at  INTEGER,
    created_at           INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_users_referral_code ON users(referral_code);
CREATE INDEX IF NOT EXISTS idx_users_score ON users(score DESC);

-- ---- Friendships (stored as a symmetric pair of rows, same as the JS store) 
CREATE TABLE IF NOT EXISTS friends (
    user_id    INTEGER NOT NULL,
    friend_id  INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (user_id, friend_id)
);

-- ---- Pending friend requests -------------------------------------------
CREATE TABLE IF NOT EXISTS friend_requests (
    from_id    INTEGER NOT NULL,
    to_id      INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (from_id, to_id)
);

-- ---- Pending friend-game invites ("play with" -> must be accepted) ------
CREATE TABLE IF NOT EXISTS game_invites (
    from_id    INTEGER NOT NULL,
    to_id      INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (from_id, to_id)
);

-- ---- Game history -------------------------------------------------------
CREATE TABLE IF NOT EXISTS game_history (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL,
    opponent_name     TEXT NOT NULL,
    mode              TEXT NOT NULL,           -- 'friend' | 'random' | 'group'
    result            TEXT NOT NULL,           -- 'win' | 'loss' | 'draw'
    end_reason        TEXT,                    -- 'connect4' | 'draw' | 'resign' | 'timeout' | 'leave'
    coins_delta       INTEGER NOT NULL DEFAULT 0,
    duration_seconds  INTEGER,
    board_snapshot    TEXT,
    played_at         INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_game_history_user ON game_history(user_id, played_at DESC);

-- ---- Matchmaking queue (single-slot, mirrors the original design) -------
CREATE TABLE IF NOT EXISTS matchmaking_queue (
    user_id    INTEGER PRIMARY KEY,
    chat_id    INTEGER NOT NULL,
    name       TEXT NOT NULL,
    lang       TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

-- ---- Games --------------------------------------------------------------
CREATE TABLE IF NOT EXISTS games (
    id               TEXT PRIMARY KEY,           -- uuid4
    mode             TEXT NOT NULL,              -- 'friend' | 'random' | 'group'
    board            TEXT NOT NULL,              -- JSON 6x7 int array
    turn             INTEGER NOT NULL,           -- 1 | 2
    chat_enabled     INTEGER NOT NULL DEFAULT 0, -- unused (chat feature removed); kept for schema parity
    status           TEXT NOT NULL,              -- 'waiting' | 'active' | 'finished'
    players          TEXT NOT NULL,              -- JSON array of player objects
    move_count       INTEGER NOT NULL DEFAULT 0,
    turn_started_at  INTEGER NOT NULL,
    created_at       INTEGER NOT NULL
);

-- ---- Per-user pointer to their currently active game --------------------
CREATE TABLE IF NOT EXISTS active_games (
    user_id    INTEGER PRIMARY KEY,
    game_id    TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

-- ---- Per-group-chat pointer to its current /game session -----------------
CREATE TABLE IF NOT EXISTS group_games (
    chat_id    INTEGER PRIMARY KEY,
    game_id    TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
