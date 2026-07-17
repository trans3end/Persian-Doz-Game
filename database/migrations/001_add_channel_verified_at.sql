-- Adds channel-membership verification caching to users.
ALTER TABLE users ADD COLUMN channel_verified_at INTEGER;
