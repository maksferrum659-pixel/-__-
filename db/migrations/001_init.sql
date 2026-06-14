-- Включаем расширение для UUID
create extension if not exists "pgcrypto";

-- Таблица пользователей
create table if not exists users (
    telegram_id bigint primary key,
    portal_token_encrypted text,
    created_at timestamptz default now()
);

-- Таблица дисциплин
create table if not exists disciplines (
    id uuid default gen_random_uuid() primary key,
    name text unique,
    control_form text,
    online_link text
);

-- Таблица событий расписания
create table if not exists schedule_events (
    external_id text,
    telegram_id bigint references users(telegram_id),
    discipline_name text,
    kind text,
    starts_at timestamptz,
    ends_at timestamptz,
    room text,
    teacher text,
    online_link text,
    primary key (external_id, telegram_id)
);

-- Таблица дедлайнов
create table if not exists deadlines (
    id uuid default gen_random_uuid() primary key,
    chat_id bigint,
    discipline_name text,
    work_type text,
    due_at timestamptz,
    raw_quote text,
    confidence real,
    source_message_id bigint,
    created_at timestamptz default now(),
    unique (chat_id, source_message_id)
);

-- Статусы дедлайнов пользователей
create table if not exists user_deadline_status (
    telegram_id bigint references users(telegram_id),
    deadline_id uuid references deadlines(id),
    done boolean default false,
    primary key (telegram_id, deadline_id)
);

-- Включаем RLS на всех таблицах
alter table users enable row level security;
alter table disciplines enable row level security;
alter table schedule_events enable row level security;
alter table deadlines enable row level security;
alter table user_deadline_status enable row level security;