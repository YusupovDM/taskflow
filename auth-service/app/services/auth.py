import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import InvalidCredentials, UserAlreadyExists
from app.messaging import EventPublisher
from app.metrics import logins_total, registrations_total
from app.models import User, UserRole
from app.security import create_access_token, hash_password, verify_password

logger = logging.getLogger(__name__)


def user_registered_payload(user: User) -> dict:
    return {
        "user_id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role.value,
    }


async def create_user(
    session: AsyncSession,
    publisher: EventPublisher,
    *,
    email: str,
    password: str,
    full_name: str,
    role: UserRole = UserRole.USER,
) -> User:
    email = email.lower()
    if await session.scalar(select(User.id).where(User.email == email)) is not None:
        raise UserAlreadyExists()
    user = User(
        email=email, full_name=full_name, hashed_password=hash_password(password), role=role
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise UserAlreadyExists() from None
    await session.refresh(user)
    registrations_total.inc()
    # событие — только после успешного commit
    await publisher.publish("user.registered", user_registered_payload(user))
    return user


async def authenticate(session: AsyncSession, email: str, password: str) -> str:
    user = await session.scalar(select(User).where(User.email == email.lower()))
    if user is None or not user.is_active or not verify_password(password, user.hashed_password):
        logins_total.labels(result="failure").inc()
        raise InvalidCredentials()
    logins_total.labels(result="success").inc()
    return create_access_token(user.id, user.email, user.role.value)


async def ensure_admin(
    session: AsyncSession,
    publisher: EventPublisher,
    email: str | None,
    password: str | None,
    full_name: str,
) -> None:
    if not email or not password:
        return
    if await session.scalar(select(User.id).where(User.email == email.lower())) is not None:
        return
    try:
        await create_user(
            session,
            publisher,
            email=email,
            password=password,
            full_name=full_name,
            role=UserRole.ADMIN,
        )
    except UserAlreadyExists:  # параллельный старт другого инстанса
        return
    logger.info("Default admin %s created", email)
