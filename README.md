# TaskFlow

Сервис для управления задачами в команде: проекты, участники, задачи с исполнителями,
приоритетами и дедлайнами, уведомления. Дипломный проект по курсу FastAPI.

Состоит из трёх микросервисов на FastAPI, которые общаются через RabbitMQ:

| Сервис | Что делает | БД |
|---|---|---|
| `auth-service` | регистрация, логин, JWT, роли | `auth_db` |
| `task-service` (2 инстанса) | проекты, участники, задачи, кэш в Redis | `tasks_db` |
| `notification-service` | уведомления пользователям | `notifications_db` |

Снаружи всё доступно через Nginx (порт 80). Ещё есть PostgreSQL, Redis, RabbitMQ и Prometheus.

Стек: Python 3.13, FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL 16, RabbitMQ (aio-pika),
Redis, PyJWT, Nginx, Prometheus, pytest, ruff, Docker, GitHub Actions.

## Что нужно установить

- Docker Desktop (с docker compose)
- Python 3.13 — только если хотите запускать тесты локально

## Запуск

```bash
git clone https://github.com/YusupovDM/taskflow.git
cd taskflow
cp .env.example .env
docker compose up -d --build
```

Через минуту проверить, что всё поднялось:

```bash
docker compose ps
```

Все сервисы должны быть `healthy`, а `task-migrations` — `Exited (0)` (он один раз накатывает
миграции и завершается, так и должно быть). Миграции auth и notification применяются сами при старте.

Остановить: `docker compose down`. Остановить и удалить данные: `docker compose down -v`.

## Адреса

| Что | Где |
|---|---|
| Swagger auth-service | http://localhost/docs/auth |
| Swagger task-service | http://localhost/docs/tasks |
| Swagger notification-service | http://localhost/docs/notifications |
| API | http://localhost/api/v1/... |
| RabbitMQ | http://localhost:15672 (логин и пароль из `.env`: `RABBITMQ_USER` / `RABBITMQ_PASSWORD`) |
| Prometheus | http://localhost:9090/targets |

Админ создаётся автоматически при первом запуске: `admin@taskflow.local` / `Admin12345!`
(меняется в `.env`).

## Как проверить, что всё работает

Удобнее всего через Swagger.

1. В http://localhost/docs/auth через `POST /auth/register` зарегистрировать двух пользователей, A и B.
   Запомнить их `id`.
2. `POST /auth/login` под A, скопировать `access_token`.
3. Открыть http://localhost/docs/tasks, нажать **Authorize**, вставить токен.
4. `POST /projects` — создать проект. A станет владельцем.
5. `POST /projects/{id}/members` с `{"user_id": <id B>}` — добавить B в проект.
6. `POST /projects/{id}/tasks` — создать задачу с `"assignee_id": <id B>` и дедлайном в прошлом.
7. Залогиниться под B, открыть http://localhost/docs/notifications, авторизоваться и вызвать
   `GET /notifications` — там будет приветствие и уведомление о назначенной задаче.
8. Под B вызвать `PATCH /tasks/{id}/status` со статусом `in_progress` — у A появится уведомление.
9. `GET /projects/{id}/tasks?overdue=true` — задача будет в списке просроченных.

## Эндпоинты

Все пути начинаются с `/api/v1`. Для большинства нужен заголовок `Authorization: Bearer <token>`.

**auth-service**

- `POST /auth/register` — регистрация
- `POST /auth/login` — получить токен
- `GET /auth/me` — текущий пользователь
- `GET /users` — список пользователей (только admin)
- `PATCH /users/{id}/role` — сменить роль (только admin)

**task-service**

- `POST /projects`, `GET /projects` — создать проект, мои проекты
- `GET / PATCH / DELETE /projects/{id}` — проект (менять и удалять может владелец или admin)
- `POST /projects/{id}/members`, `DELETE /projects/{id}/members/{user_id}` — участники
- `POST /projects/{id}/tasks`, `GET /projects/{id}/tasks` — задачи проекта
  (фильтры `status`, `assignee_id`, `overdue`, пагинация `limit` / `offset`)
- `GET /tasks/my` — задачи, назначенные на меня
- `GET / PATCH / DELETE /tasks/{id}` — задача
- `PATCH /tasks/{id}/status` — сменить статус (исполнитель, владелец проекта или admin)

**notification-service**

- `GET /notifications` — мои уведомления (`unread_only=true` — только непрочитанные)
- `PATCH /notifications/{id}/read` — отметить прочитанным
- `POST /notifications/read-all` — отметить все

В каждом сервисе есть `GET /health`, `GET /health/ready` и `GET /metrics`
(метрики снаружи через Nginx закрыты, их забирает Prometheus).

## Как это устроено

- JWT выдаёт auth-service, а проверяет каждый сервис сам по общему секрету `JWT_SECRET`.
- Сервисы не ходят друг к другу по HTTP, только через RabbitMQ (exchange `taskflow.events`).
- `user.registered` — после регистрации; task-service сохраняет копию пользователя у себя,
  notification-service присылает приветствие.
- `task.created`, `task.assigned`, `task.status_changed` — notification-service по ним
  создаёт уведомления.
- Сообщения, которые не удалось обработать, попадают в очередь `taskflow.dead-letter`.
- Список задач и карточка проекта кэшируются в Redis. При изменениях кэш сбрасывается.
  Если Redis упал, сервис продолжает работать без кэша.
- Nginx распределяет запросы между двумя инстансами task-service и ограничивает частоту
  запросов (на логин и регистрацию строже).
- Три базы лежат в одном контейнере PostgreSQL, но каждый сервис работает только со своей.

## Тесты

Тесты ходят в настоящий PostgreSQL, поэтому сначала нужно поднять его из compose
(он проброшен на `localhost:5433`, тестовые базы создаются автоматически).

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r auth-service/requirements-dev.txt -r task-service/requirements-dev.txt
docker compose up -d postgres

cd auth-service && ../.venv/bin/pytest -q && cd ..
cd task-service && ../.venv/bin/pytest -q && cd ..
cd notification-service && ../.venv/bin/pytest -q && cd ..

.venv/bin/ruff check .
```

Если volume Postgres остался со старого запуска и тестовых баз нет, создать их вручную:

```bash
docker compose exec postgres psql -U taskflow -d postgres -c "CREATE DATABASE auth_test"
docker compose exec postgres psql -U taskflow -d postgres -c "CREATE DATABASE tasks_test"
docker compose exec postgres psql -U taskflow -d postgres -c "CREATE DATABASE notifications_test"
```

## CI

GitHub Actions (`.github/workflows/ci.yml`) на каждый push и pull request запускает ruff и тесты.
При push в `main` ещё собирает Docker-образы и пушит их в GHCR.

Для CI в настройках репозитория (Settings → Secrets and variables → Actions) можно добавить
секрет `TEST_JWT_SECRET`. Чтобы образы пушились в GHCR, в Settings → Actions → General нужно
включить «Read and write permissions».
