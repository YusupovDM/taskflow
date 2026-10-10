from fastapi import APIRouter, status

from app.dependencies import CurrentUser, PublisherDep, SessionDep
from app.schemas import Token, UserCreate, UserLogin, UserRead
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(data: UserCreate, session: SessionDep, publisher: PublisherDep):
    return await auth_service.create_user(
        session, publisher, email=data.email, password=data.password, full_name=data.full_name
    )


@router.post("/login", response_model=Token)
async def login(data: UserLogin, session: SessionDep):
    token = await auth_service.authenticate(session, data.email, data.password)
    return Token(access_token=token)


@router.get("/me", response_model=UserRead)
async def me(user: CurrentUser):
    return user
