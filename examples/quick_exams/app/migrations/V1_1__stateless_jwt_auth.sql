-- Staff authentication moves from database sessions to signed JWT access tokens.
-- The sessions table is no longer used. Each user gets a token version that is
-- embedded in their tokens; incrementing it (password change, removed access)
-- invalidates every token issued before.

DROP INDEX ix_sessions_user_id;

DROP TABLE sessions;

ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0;
