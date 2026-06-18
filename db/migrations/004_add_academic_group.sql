-- Миграция 004: академическая группа студента
-- Применить ПОСЛЕ 001_init.sql

ALTER TABLE users ADD COLUMN IF NOT EXISTS academic_group text;
