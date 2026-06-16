"""
core/ — общая, замороженная основа проекта (CONTRACT.md §3, §6).

Публичные точки входа:
    core.security.encrypt_token / decrypt_token   — Fernet-шифрование токена портала
    core.llm.GigaChatClient                       — реализация протокола LLMClient
    core.deadline_extractor.extract_deadline      — ИИ-извлечение дедлайнов из текста
    core.ai_chat.answer_question                  — ИИ-ответ на вопрос по контексту из БД (ветка marina)
"""
