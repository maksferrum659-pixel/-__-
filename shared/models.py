from datetime import datetime
from pydantic import BaseModel


class ScheduleEvent(BaseModel):
    external_id: str
    telegram_id: int
    discipline_name: str
    kind: str | None = None
    starts_at: datetime
    ends_at: datetime
    room: str | None = None
    teacher: str | None = None
    online_link: str | None = None


class Deadline(BaseModel):
    chat_id: int
    discipline_name: str | None = None
    work_type: str | None = None
    due_at: datetime | None = None
    raw_quote: str | None = None
    confidence: float = 0.0
    source_message_id: int | None = None
    id: str | None = None
