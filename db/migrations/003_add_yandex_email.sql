-- Миграция 003: Яндекс-почта для подписки на ICS-календарь
-- Применить ПОСЛЕ 001_init.sql

ALTER TABLE users ADD COLUMN IF NOT EXISTS yandex_email text;
