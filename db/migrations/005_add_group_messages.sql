-- Таблица для хранения сообщений группового чата.
-- Заполняется групповым ботом (ветка bot-split).
-- Используется ИИ-чатом для ответов по истории группы.
create table if not exists group_messages (
    id              bigserial primary key,
    chat_id         bigint not null,
    telegram_id     bigint,
    username        text,
    full_name       text,
    text            text not null,
    sent_at         timestamptz not null,
    message_id      bigint,
    unique (chat_id, message_id)
);

create index if not exists group_messages_chat_sent
    on group_messages (chat_id, sent_at desc);
