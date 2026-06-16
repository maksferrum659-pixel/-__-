-- Привязка пользователя к групповому чату.
-- Заполняется при первом сообщении бота в группе или командой /setgroup.
alter table users add column if not exists group_chat_id bigint;
