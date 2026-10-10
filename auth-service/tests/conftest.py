import os

# до импорта app: настройки читаются при импорте
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32b")
os.environ["RABBITMQ_ENABLED"] = "false"
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://taskflow:change_me@localhost:5433/auth_test"
)

from unittest.mock import AsyncMock  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.database import Base, get_session  # noqa: E402
from app.dependencies import get_publisher  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User, UserRole  # noqa: E402
from app.security import create_access_token, hash_password  # noqa: E402


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
async def client(session_factory, publisher):
    async def override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_publisher] = lambda: publisher
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


async def _create_user(session, email: str, role: UserRole) -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0],
        hashed_password=hash_password("password123"),
        role=role,
    )
    session.add(user)
    await session.commit()
    return user


def auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(user.id, user.email, user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def user(session) -> User:
    return await _create_user(session, "user@example.com", UserRole.USER)


@pytest.fixture
async def admin(session) -> User:
    return await _create_user(session, "admin@example.com", UserRole.ADMIN)


@pytest.fixture
def user_headers(user) -> dict[str, str]:
    return auth_headers(user)


@pytest.fixture
def admin_headers(admin) -> dict[str, str]:
    return auth_headers(admin)
