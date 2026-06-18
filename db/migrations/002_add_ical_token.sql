-- Миграция 002: токен для ICS-подписки (Яндекс.Календарь и другие)
-- Применить ПОСЛЕ 001_init.sql

ALTER TABLE users ADD COLUMN IF NOT EXISTS ical_token uuid DEFAULT gen_random_uuid();

CREATE UNIQUE INDEX IF NOT EXISTS users_ical_token_idx ON users(ical_token);
