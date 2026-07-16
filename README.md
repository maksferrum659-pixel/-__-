# CampusSync

**One Telegram bot for everything a student needs to track: class schedule and assignment deadlines.**

CampusSync connects two very different data sources — a university web portal and a group chat — into a single, always up-to-date view for students. It parses the official class schedule from a university portal and uses an LLM to detect and extract assignment deadlines mentioned in natural language inside a Telegram group chat, then serves both back through simple bot commands and a personal calendar feed.

## Why

University schedule portals are clunky and deadlines are usually just announced in a group chat message, easy to miss and impossible to search later ("the essay is due next Friday" buried between a hundred other messages). CampusSync removes the manual work: the schedule syncs automatically from the portal, and the AI reads the chat so no deadline gets lost.

## Features

- **Personal schedule sync** — each student links their own portal account; the bot authenticates, fetches their class schedule, and keeps it updated on a recurring job.
- **AI deadline extraction** — messages posted in the class group chat are analyzed by an LLM, which extracts the discipline, type of work, and due date/time, with a confidence score attached.
- **Chat commands** — `/today`, `/week`, `/discipline <name>`, `/credits` return a formatted view of the student's schedule and open deadlines.
- **Calendar export (ICS)** — a personal calendar feed can be subscribed to from any calendar app (Google Calendar, Apple Calendar, etc.).
- **Automated reminders** — a scheduler pushes reminders ahead of upcoming classes and deadlines.
- **Security by design** — portal credentials are never stored or logged; only a Fernet-encrypted session token is kept, and the message containing a password is deleted from the chat immediately after it's read.

## How it works

```
University portal ──parser.fetch_schedule()──▶ ScheduleEvent ──▶ Supabase (per-user)
Telegram group chat ──message──▶ core.extract_deadline() (LLM) ──▶ Deadline ──▶ Supabase (per-group)
Student commands (/today /week /discipline /credits) ──▶ read from Supabase ──▶ formatted reply
Scheduler (APScheduler) ──▶ periodic portal sync + due reminders
Personal ICS feed ──▶ served over HTTP, subscribable from any calendar app
```

Schedules are personal (each student authenticates with their own portal account); deadlines are shared per group chat, since one announcement applies to everyone in the class.

## Tech stack

| Layer | Technology |
|---|---|
| Bot framework | [aiogram](https://docs.aiogram.dev/) 3.x (async, Telegram Bot API) |
| Language / data models | Python 3.11+, Pydantic v2 |
| Portal client | httpx |
| Database | Supabase (Postgres) with Row Level Security |
| AI / LLM | GigaChat, with YandexGPT as a fallback provider |
| Scheduling | APScheduler |
| Calendar export | icalendar, FastAPI, Uvicorn |
| Secrets | cryptography (Fernet symmetric encryption) |
| Testing | pytest |

## Repository structure

This is a monorepo split by responsibility, so each module can be developed and reviewed independently:

```
shared/    Shared Pydantic data models (ScheduleEvent, Deadline) — frozen contract
core/      AI extraction engine, LLM client, token encryption — frozen contract
db/        Supabase access layer and migrations
parser/    Portal authentication and schedule scraping (pure library, no DB writes)
bot/       aiogram handlers, FSM flows, scheduler wiring
ical/      Personal calendar (.ics) feed server
tests/     Offline unit tests + Supabase integration tests
```

The data contracts and public function signatures for every module are defined up front in [CONTRACT.md](CONTRACT.md), so the parser, database, and bot components can be built in parallel on separate branches without breaking each other's integrations.

## Data models

```python
class ScheduleEvent(BaseModel):
    external_id: str
    telegram_id: int
    discipline_name: str
    kind: str | None          # lecture, seminar, ...
    starts_at: datetime
    ends_at: datetime
    room: str | None
    teacher: str | None
    online_link: str | None

class Deadline(BaseModel):
    chat_id: int
    discipline_name: str | None
    work_type: str | None     # homework, essay, presentation, exam...
    due_at: datetime | None
    raw_quote: str | None
    confidence: float
    source_message_id: int | None
```

## Getting started

```bash
git clone https://github.com/<your-username>/campus-sync.git
cd campus-sync
python -m pip install -r requirements.txt
cp .env.example .env      # fill in Supabase, bot, and LLM credentials
python -m bot.main         # runs the bot: polling + scheduler
```

### Environment variables

```
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
BOT_TOKEN=
GIGACHAT_CREDENTIALS=
FERNET_KEY=
PORTAL_BASE_URL=https://your-university-portal.example
CALENDAR_BASE_URL=https://your-domain.example   # public URL of the ICS feed server
```

### Tests

```bash
pytest tests/test_parser.py tests/test_bot.py   # offline, no network or secrets needed
pytest tests/test_db.py                          # integration, requires a real Supabase instance
```

## Project status

The data contracts, database schema, and module boundaries are finalized. Parser, database, bot, and calendar-export functionality are implemented and developed on dedicated feature branches, integrated regularly into `main`/`develop`.

## Team

Built as a three-person team project, split along the module boundaries above:

- **Parser** (portal authentication & schedule scraping) — Maksim
- **Database** (Supabase schema, migrations, data access layer) — Nastya
- **Bot** (Telegram handlers, scheduler, reminders) — Egor

## License

Educational project, built for a university course.
