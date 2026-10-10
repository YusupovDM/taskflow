from typing import Any

import jwt

from app.config import settings


def decode_token(token: str) -> dict[str, Any]:
    """Проверяет подпись JWT локально (без запроса в auth-service).

    Бросает jwt.PyJWTError, если токен невалиден или просрочен.
    """
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["sub", "exp"]},
    )
