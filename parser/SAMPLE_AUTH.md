# SAMPLE_AUTH.md — схема авторизации портала `rr-edu.ranepa.ru`

> ✅ **Подтверждено на живом аккаунте** (логин + реальный ответ календаря).
> Изначально снято с публичных ассетов (Nuxt-чанки `auth`, `autologin`, `calendar`),
> затем сверено живым запросом. Реальные значения cookie/токенов и персональные
> данные здесь **не хранятся** — только структура.

## Итог: авторизация **сессионная (Cookie)**, не Bearer

Эндпоинт календаря без сессии отвечает:

```http
GET /api/v1/private/scos/calendar
→ 401 {"code": 401, "name": "Unauthorized", "description": "<p>Session expired</p>"}
```

Формулировка «Session expired» = сервер ждёт **cookie сессии**, а не заголовок
`Authorization`.

## 1. Логин

Реальный логин-эндпоинт (найден в чанке `autologin.*.js`, не путать с
SPA-страницей `/login`):

```http
POST /api/v1/public/users/login
Content-Type: application/json

{"login": "<email_or_login>", "password": "<password>"}
```

Наблюдаемые ответы при проверочных запросах:

| Запрос | Ответ |
|---|---|
| без поля `login` | `400 {'login': ['required field']}` |
| неверные `login`+`password` | `403 «Неверное имя пользователя или пароль»` |
| верные | `200` + `Set-Cookie: session_id=…` + JSON-профиль в теле |

На успехе сервер ставит cookie **`session_id`** (имя подтверждено живым входом).
Эту cookie мы и реплеим дальше.

### cURL (структура, секрет затёрт)

```bash
curl -i -X POST 'https://rr-edu.ranepa.ru/api/v1/public/users/login' \
  -H 'Content-Type: application/json' \
  --data '{"login":"<REDACTED>","password":"<REDACTED>"}'
# → 200, заголовок ответа: Set-Cookie: session_id=<REDACTED>; Path=/; HttpOnly
```

`authenticate()` забирает все cookie из ответа и возвращает строку
`"session_id=<value>"` — это и есть «session token» из §6 контракта
(пароль наружу не отдаётся).

## 2. Текущий пользователь (опционально, для проверки сессии)

```http
GET /api/v1/private/users/current        # требует сессию
```

## 3. Календарь (расписание)

```http
GET /api/v1/private/scos/calendar?dateFrom=YYYY-MM-DD&dateTo=YYYY-MM-DD&perPage=70
Cookie: <строка из authenticate()>
```

Параметры подтверждены живым запросом:
`{ perPage: 70, dateFrom: <YYYY-MM-DD>, dateTo: <YYYY-MM-DD> }`.

### Реальная обёртка ответа

```jsonc
{
  "pagination": { "count": <дней>, "page": 0, "perPage": 70 },
  "results": [                       // суточные бакеты
    { "date": "2025-09-01", "events": [ { …событие… } ] }
  ]
}
```

### Поля события → `ScheduleEvent`

| Поле API | Поле `ScheduleEvent` | Примечание |
|---|---|---|
| `id` (или `key`) | `external_id` | ⚠️ `eventId` в расписании обычно `null`; берём `id` (PK) / `key` (UUID) |
| `name` | `discipline_name` | |
| `type` | `kind` | англ-слаг (`lecture`/`practical`/…) → русский ярлык |
| `date` (бакет) + `startTime` | `starts_at` | `startTime`/`endTime` — **московское** настенное время |
| `date` (бакет) + `endTime` | `ends_at` | |
| `teacher.fullName` | `teacher` | |
| `location.name` | `room` | `location` бывает `null` |
| `meetingUrl` | `online_link` | |

> ⚠️ `dateStart` в ответе — это **UTC** (на 3 ч меньше `startTime`); для времени
> используем именно `startTime`/`endTime` + дату бакета, локализованные в Europe/Moscow.
> `parse_calendar` также поддерживает плоский список (`items`/`data`) — на случай
> других эндпоинтов. `parser/samples/calendar_response.json` — **реальный захват**
> (2 дня, имена преподавателей обезличены, токенизируемые URL обнулены).
