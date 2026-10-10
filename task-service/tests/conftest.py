import os

# до импорта app: настройки читаются при импорте
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32b")
os.environ["RABBITMQ_ENABLED"] = "false"
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://taskflow:change_me@localhost:5433/tasks_test"
)

from datetime import UTC, datetime, timedelta  # noqa: E402
from unittest.mock import AsyncMock  # noqa: E402

import fakeredis  # noqa: E402
import jwt  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from redis.exceptions import ConnectionError as RedisConnectionError  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.cache import Cache  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import Base, get_session  # noqa: E402
from app.dependencies import get_cache, get_publisher  # noqa: E402
from app.main import app  # noqa: E402
from app.models import UserReplica  # noqa: E402

OWNER_ID, MEMBER_ID, OUTSIDER_ID, ADMIN_ID = 1, 2, 3, 100


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
def publisher():
    return AsyncMock()


@pytest.fixture
async def redis():
    redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    yield redis
    await redis.flushall()
    await redis.aclose()


@pytest.fixture
def cache(redis):
    return Cache(redis)


class BrokenRedis:
    """Redis, который «упал»: любая операция бросает ConnectionError."""

    async def _fail(self, *args, **kwargs):
        raise RedisConnectionError("redis is down")

    get = set = delete = incr = ping = _fail


@pytest.fixture
async def client(session_factory, publisher, cache):
    async def override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_publisher] = lambda: publisher
    app.dependency_overrides[get_cache] = lambda: cache
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


def make_token(user_id: int, role: str = "user") -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "email": f"user{user_id}@example.com",
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


@pytest.fixture
def auth_headers():
    def _headers(user_id: int, role: str = "user") -> dict[str, str]:
        return {"Authorization": f"Bearer {make_token(user_id, role)}"}

    return _headers


@pytest.fixture
def owner_headers(auth_headers):
    return auth_headers(OWNER_ID)


@pytest.fixture
def admin_headers(auth_headers):
    return auth_headers(ADMIN_ID, "admin")


@pytest.fixture
async def users(session):
    """Реплики пользователей, как будто пришли события user.registered."""
    names = {OWNER_ID: "Owner", MEMBER_ID: "Member", OUTSIDER_ID: "Outsider", ADMIN_ID: "Admin"}
    session.add_all(
        UserReplica(id=uid, email=f"user{uid}@example.com", full_name=name)
        for uid, name in names.items()
    )
    await session.commit()


@pytest.fixture
async def project(client, users, owner_headers):
    """Проект владельца OWNER_ID с участником MEMBER_ID."""
    response = await client.post(
        "/api/v1/projects", json={"name": "Diploma"}, headers=owner_headers
    )
    project = response.json()
    await client.post(
        f"/api/v1/projects/{project['id']}/members",
        json={"user_id": MEMBER_ID},
        headers=owner_headers,
    )
    return project
