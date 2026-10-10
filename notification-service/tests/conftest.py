import os

# до импорта app: настройки читаются при импорте.
# В CI JWT_SECRET приходит из секрета TEST_JWT_SECRET; если его нет — тестовое значение.
if not os.environ.get("JWT_SECRET"):
    os.environ["JWT_SECRET"] = "test-secret-key-for-pytest-only-32b"
os.environ["RABBITMQ_ENABLED"] = "false"
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://taskflow:change_me@localhost:5433/notifications_test",
)

import uuid  # noqa: E402
from datetime import UTC, datetime, timedelta  # noqa: E402

import jwt  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import Base, get_session  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
async def engine():
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def session_factory(engine):
    yield async_sessionmaker(engine, expire_on_commit=False)
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
async def session(session_factory):
    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(session_factory):
    async def override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


def make_token(user_id: int, role: str = "user") -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "email": f"u{user_id}@example.com",
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


@pytest.fixture
def auth_headers():
    def _headers(user_id: int) -> dict[str, str]:
        return {"Authorization": f"Bearer {make_token(user_id)}"}

    return _headers


def make_event(event_type: str, payload: dict, event_id: str | None = None) -> dict:
    return {
        "event_id": event_id or str(uuid.uuid4()),
        "event_type": event_type,
        "occurred_at": datetime.now(UTC).isoformat(),
        "producer": "test",
        "payload": payload,
    }


TASK = {"task_id": 1, "project_id": 1, "project_name": "Diploma", "title": "Slides"}
