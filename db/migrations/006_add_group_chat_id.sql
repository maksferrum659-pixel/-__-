-- Привязка пользователя к групповому чату.
-- Заполняется групповым ботом (@informationRRbot) при первом сообщении в группе.
alter table users add column if not exists group_chat_id bigint;
