from pydantic import BaseModel


class ErrorResponse(BaseModel):
    detail: str


_DESCRIPTIONS = {
    400: "Некорректный запрос",
    401: "Нет токена, токен невалиден или просрочен",
    403: "Недостаточно прав",
    404: "Не найдено",
    409: "Конфликт (уже существует)",
}


def error_responses(*codes: int) -> dict[int | str, dict]:
    """Описание ошибок для Swagger: responses=error_responses(401, 403)."""
    return {code: {"model": ErrorResponse, "description": _DESCRIPTIONS[code]} for code in codes}
