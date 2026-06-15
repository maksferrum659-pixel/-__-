# SAMPLE_AUTH.md — схема авторизации портала `rr-edu.ranepa.ru`

> Снято с публичных ассетов портала (Nuxt-чанки `auth`, `autologin`, `calendar`)
> и проверочных запросов к API **без валидных учёток**. Реальные значения cookie/
> токенов здесь **не хранятся** — только структура. Перед мержем стоит сверить с
> живым `Copy as cURL` из DevTools на реальном аккаунте.

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
| верные (ожидается) | `200` + `Set-Cookie: <session>=…` |

На успехе сервер ставит cookie сессии. Эту cookie мы и реплеим дальше.

### cURL (структура, секрет затёрт)

```bash
curl -i -X POST 'https://rr-edu.ranepa.ru/api/v1/public/users/login' \
  -H 'Content-Type: application/json' \
  --data '{"login":"<REDACTED>","password":"<REDACTED>"}'
# → 200, заголовок ответа: Set-Cookie: session=<REDACTED>; Path=/; HttpOnly
```

`authenticate()` забирает все cookie из ответа и возвращает строку
`"name=value; name2=value2"` — это и есть «session token» из §6 контракта
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

Параметры взяты из чанка `calendar.*.js`:
`{ perPage: 70, dateFrom: <YYYY-MM-DD>, dateTo: <YYYY-MM-DD> }`.
Фронт по умолчанию запрашивает окно ~+35 дней.

### Поля события (из компонента `CalendarDayPhoneView.*.js`)

| Поле API | Поле `ScheduleEvent` |
|---|---|
| `eventId` | `external_id` |
| `name` | `discipline_name` |
| `type` | `kind` |
| `date` + `startTime` | `starts_at` (Europe/Moscow) |
| `date` + `endTime` | `ends_at` (Europe/Moscow) |
| `teacher.fullName` | `teacher` |
| `location.name` | `room` |
| `meetingUrl` | `online_link` |

> ⚠️ Точная **обёртка** ответа (плоский список в `items` против суточных бакетов
> `{date, events[]}`) с публичных ассетов однозначно не выводится — `parse_calendar`
> поддерживает обе. `parser/samples/calendar_response.json` — **реконструкция** по
> этой схеме; замени его реальным захватом, как только будет живой аккаунт.
