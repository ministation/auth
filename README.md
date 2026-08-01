# SS14 Discord Auth — Мини-станция

Сервис привязки Discord ↔ SS14 и автологина на [ministation.ru](https://ministation.ru/).

**Лицензия:** см. [LICENSE](LICENSE) (© Мини-станция, все права защищены).  
Сторонние зависимости — в [NOTICE](NOTICE).

## Возможности

- Corvax-совместимый API: `POST /{user_id}?key=…`, `GET /{user_id}`, `GET /login/{user_id}`
- Discord OAuth + проверка гильдии + выдача роли
- Запись привязки сразу в `DB1`, `DB2`, …
- Жёстко: 1 Discord ID → 1 игровой аккаунт
- Редирект на сайт с одноразовым HMAC-токеном

## Быстрый старт

```bash
cp .env.example .env
# заполните .env
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

## API

| Метод | Путь | Назначение |
|-------|------|------------|
| GET | `/health` | Статус и ping БД |
| GET | `/login/{uuid}` | Старт OAuth |
| GET | `/callback` | Discord callback |
| POST | `/{uuid}?key=` | Ссылка + QR для игры |
| GET | `/{uuid}` | `{ "IsLinked": bool }` |

Контакты: https://ministation.ru/ · mini-station-14@yandex.ru
