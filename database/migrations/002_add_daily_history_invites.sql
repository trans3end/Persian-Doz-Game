-- Adds daily-coin cooldown tracking, referral invite counting, and the
-- friend-game-invite table.
ALTER TABLE users ADD COLUMN last_daily_claim_at INTEGER;
ALTER TABLE users ADD COLUMN invites_count INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS game_invites (
    from_id    INTEGER NOT NULL,
    to_id      INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (from_id, to_id)
);
