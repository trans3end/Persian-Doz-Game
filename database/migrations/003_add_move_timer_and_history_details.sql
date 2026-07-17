-- Adds per-move timer bookkeeping to games, and richer result details to
-- game_history.
ALTER TABLE games ADD COLUMN move_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE games ADD COLUMN turn_started_at INTEGER;
UPDATE games SET turn_started_at = created_at WHERE turn_started_at IS NULL;

ALTER TABLE game_history ADD COLUMN end_reason TEXT;
ALTER TABLE game_history ADD COLUMN coins_delta INTEGER NOT NULL DEFAULT 0;
ALTER TABLE game_history ADD COLUMN duration_seconds INTEGER;
ALTER TABLE game_history ADD COLUMN board_snapshot TEXT;
