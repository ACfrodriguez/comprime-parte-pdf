import asyncio
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .config import logger
from .notifier import GmailNotifier


# Este script agrupa la construccion y manejo de errores HTTP y validaciones.
def build_validation_detail(
    message: str, *, error: str, field: str | None = None
) -> dict[str, Any]:
    # Estructura comun para responder validaciones de forma consistente.
    detail: dict[str, Any] = {
        "message": message,
        "error": error,
        "code": "validation_error",
    }
    if field:
        detail["field"] = field
    return detail


def log_validation_error(*, status_code: int, detail: dict[str, Any]) -> None:
    # Formato uniforme para poder filtrar facilmente validaciones en logs/api.log.
    logger.warning(
        "Validation error status=%s code=%s field=%s message=%s error=%s",
        status_code,
        detail.get("code"),
        detail.get("field"),
        detail.get("message"),
        detail.get("error"),
    )


async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    # Si el error ya viene estructurado como validacion, se registra con un formato mas util.
    if isinstance(exc.detail, dict) and exc.detail.get("code") == "validation_error":
        log_validation_error(status_code=exc.status_code, detail=exc.detail)
    else:
        logger.warning("HTTPException status=%s detail=%s", exc.status_code, exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


async def request_validation_exception_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    # Traduce el formato interno de FastAPI a una respuesta mas clara para el cliente.
    errors = []
    for item in exc.errors():
        # FastAPI expresa la ubicacion como tupla; aqui se convierte a una ruta legible.
        location = [str(part) for part in item.get("loc", []) if part != "body"]
        field = ".".join(location) or None
        errors.append(
            {
                "field": field,
                "message": item.get("msg", "Error de validacion."),
                "error": item.get("type", "validation_error"),
                "input": item.get("input"),
            }
        )

    primary_error = errors[0] if errors else None
    detail = {
        "message": "La solicitud a /compress no es valida.",
        "error": primary_error["message"] if primary_error else "Error de validacion.",
        "code": "validation_error",
        "field": primary_error["field"] if primary_error else None,
        "errors": errors,
    }
    log_validation_error(status_code=422, detail=detail)
    return JSONResponse(status_code=422, content={"detail": detail})


async def notify_unhandled_exception(
    notifier: GmailNotifier, *, path: str, error_message: str
) -> None:
    try:
        await notifier.send_application_error_email(
            path=path, error_message=error_message
        )
    except Exception:
        logger.exception(
            "No se pudo enviar el correo por error no controlado en path=%s", path
        )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
    notifier: GmailNotifier,
) -> JSONResponse:
    # Mantiene respuesta JSON controlada y dispara la alerta en segundo plano.
    logger.exception("Unhandled exception: %s", exc)
    # La notificacion se programa en background para no aumentar la latencia al cliente.
    asyncio.create_task(
        notify_unhandled_exception(
            notifier, path=request.url.path, error_message=str(exc)
        )
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": {
                "message": "Internal Server Error",
                "error": str(exc),
            }
        },
    )
