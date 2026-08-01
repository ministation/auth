# SS14 Discord Auth — Мини-станция

Сервис привязки Discord ↔ SS14 и автологина на [ministation.ru](https://ministation.ru/).

**Лицензия:** см. [LICENSE](LICENSE) (© Мини-станция, все права защищены).  
Сторонние зависимости — в [NOTICE](NOTICE).

## Возможности

- Corvax-совместимый API: `POST /{user_id}?key=…`, `GET /{user_id}`, `GET /login/{user_id}`
- Discord OAuth + проверка гильдии + выдача роли на один или несколько серверов (`AUTH_DISCORD_ROLES` / `GUILD2_ID`)
- Запись привязки сразу в `DB1`, `DB2`, …
- Жёстко: 1 Discord ID → 1 игровой аккаунт
- Редирект на сайт с одноразовым HMAC-токеном

## Быстрый старт

Рекомендуется **Python 3.11 или 3.12** (на 3.14 часть пакетов ещё без готовых wheel).

```bash
cp .env.example .env
# заполните .env
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python discord_auth_server.py
```

Docker:

```bash
docker compose up --build
```

SQL (рекомендуется на каждой БД):

```bash
psql -f sql/001_discord_auth_uniques.sql
```

Тесты:

```bash
pytest -q
```

## Конфиг

См. `.env.example`. Обязательно одинаковый `GAME_AUTH_SECRET` на этом сервисе и на сайте (`token_site`).

Роли «Авторизован» на Мини + Оазис: `GUILD_ID` / `AUTH_DISCORD_ROLE_ID` и `GUILD2_ID` / `AUTH_DISCORD_ROLE_ID_2` (при необходимости `GUILD2_BOT_TOKEN`).

Бэкфилл уже привязанных аккаунтов (только тем, кто уже на целевом Discord):

```bash
python scripts/sync_auth_roles.py --only-guild 1381238425260134440 --diagnose
python scripts/sync_auth_roles.py --only-guild 1381238425260134440 --reset-state
```

Для списка участников боту нужен privileged **Server Members Intent**.

## API

| Метод | Путь | Назначение |
|-------|------|------------|
| GET | `/health` | Статус и ping БД |
| GET | `/login/{uuid}` | Старт OAuth |
| GET | `/callback` | Discord callback |
| POST | `/{uuid}?key=` | Ссылка + QR для игры |
| GET | `/{uuid}` | `{ "IsLinked": bool }` |

Контакты: https://ministation.ru/ · mini-station-14@yandex.ru
