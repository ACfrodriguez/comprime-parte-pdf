import unicodedata
from io import BytesIO
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse

from .api_errors import (
    build_validation_detail,
    http_exception_handler,
    request_validation_exception_handler,
    unhandled_exception_handler,
)
from .compression_service import RotatingCompressionService
from .config import DASHBOARD_ACCESS_TOKEN, logger
from .dashboard import (
    DASHBOARD_COOKIE,
    is_authenticated,
    is_dashboard_enabled,
    render_css,
    render_dashboard_page,
    render_login_page,
)
from .notifier import GmailNotifier
from .usage_store import (
    add_account_with_usage,
    delete_account,
    get_account,
    init_usage_store,
    list_accounts,
    update_account,
)

# Este script es la entrada principal de FastAPI y conecta endpoints con los servicios.
# Punto de entrada HTTP: endpoints, middleware y registro de handlers.
app = FastAPI(
    title="PDF Compression API",
    version="1.0.0",
    description="API FastAPI para comprimir PDFs con Adobe PDF Services.",
)

gmail_notifier = GmailNotifier()
compression_service = RotatingCompressionService(notifier=gmail_notifier)


@app.on_event("startup")
def startup_event() -> None:
    # Inicializa el archivo JSON de uso si no existe.
    init_usage_store()


@app.get("/usage")
def usage_summary() -> dict[str, Any]:
    """Devuelve el uso agregado de todas las cuentas de Adobe."""
    return compression_service.get_usage()


@app.get("/usage/{account_email}")
def usage_by_account(account_email: str) -> dict[str, Any]:
    """Devuelve el uso de una cuenta concreta de Adobe."""
    return compression_service.get_usage(account_email)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    message: str | None = Query(None),
    error: str | None = Query(None),
    edit: str | None = Query(None),
) -> HTMLResponse:
    if not is_dashboard_enabled():
        return render_login_page(error="Configura DASHBOARD_ACCESS_TOKEN para acceder al dashboard.")

    if not is_authenticated(request):
        return render_login_page(error=error)

    metrics = compression_service.get_usage()
    accounts = list_accounts()
    editing_account = get_account(edit) if edit else None
    if edit and editing_account is None:
        error = error or f"No se encontro una cuenta configurada para {edit}."
    return render_dashboard_page(
        metrics=metrics,
        accounts=accounts,
        editing_account=editing_account,
        message=message,
        error=error,
    )


@app.get("/dashboard/style.css", include_in_schema=False)
def dashboard_style() -> Response:
    return render_css()


@app.post("/dashboard/login")
async def dashboard_login(token: str = Form(...)):
    if not is_dashboard_enabled():
        return render_login_page(error="Configura DASHBOARD_ACCESS_TOKEN para habilitar el dashboard.")

    if token.strip() != DASHBOARD_ACCESS_TOKEN:
        return render_login_page(error="Token invalido.")

    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(
        key=DASHBOARD_COOKIE,
        value=DASHBOARD_ACCESS_TOKEN,
        httponly=True,
        samesite="strict",
        max_age=60 * 60 * 12,
        path="/",
    )
    return response


@app.post("/dashboard/logout")
async def dashboard_logout() -> RedirectResponse:
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.delete_cookie(key=DASHBOARD_COOKIE, path="/")
    return response


@app.get("/dashboard/metrics")
async def dashboard_metrics(request: Request) -> dict[str, Any]:
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="No autorizado.")
    return {
        "usage": compression_service.get_usage(),
        "accounts": list_accounts(),
    }


@app.post("/dashboard/accounts")
async def dashboard_add_account(
    request: Request,
    email: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    day_used: int = Form(0),
    month_used: int = Form(0),
):
    if not is_authenticated(request):
        return render_login_page(error="Tu sesion ha expirado o el token no es valido.")

    try:
        add_account_with_usage(
            email=email,
            client_id=client_id,
            client_secret=client_secret,
            day_used=day_used,
            month_used=month_used,
        )
    except ValueError as exc:
        return render_dashboard_page(
            metrics=compression_service.get_usage(),
            accounts=list_accounts(),
            error=str(exc),
        )

    return RedirectResponse(url="/dashboard?message=Cuenta+agregada", status_code=303)


@app.post("/dashboard/accounts/update")
async def dashboard_update_account(
    request: Request,
    original_email: str = Form(...),
    email: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    day_used: int = Form(0),
    month_used: int = Form(0),
):
    if not is_authenticated(request):
        return render_login_page(error="Tu sesion ha expirado o el token no es valido.")

    try:
        update_account(
            original_email=original_email,
            email=email,
            client_id=client_id,
            client_secret=client_secret,
            day_used=day_used,
            month_used=month_used,
        )
    except ValueError as exc:
        return render_dashboard_page(
            metrics=compression_service.get_usage(),
            accounts=list_accounts(),
            editing_account=get_account(original_email) or get_account(email),
            error=str(exc),
        )

    return RedirectResponse(url="/dashboard?message=Cuenta+actualizada", status_code=303)


@app.post("/dashboard/accounts/delete")
async def dashboard_delete_account(
    request: Request,
    email: str = Form(...),
):
    if not is_authenticated(request):
        return render_login_page(error="Tu sesion ha expirado o el token no es valido.")

    try:
        removed = delete_account(email=email)
    except ValueError as exc:
        return render_dashboard_page(
            metrics=compression_service.get_usage(),
            accounts=list_accounts(),
            error=str(exc),
        )

    if not removed:
        return render_dashboard_page(
            metrics=compression_service.get_usage(),
            accounts=list_accounts(),
            error=f"No se encontro una cuenta configurada para {email}.",
        )

    return RedirectResponse(url="/dashboard?message=Cuenta+eliminada", status_code=303)


def build_content_disposition(filename: str) -> str:
    # Genera un nombre de descarga compatible con clientes ASCII y UTF-8.
    ascii_filename = (
        unicodedata.normalize("NFKD", filename)
        .encode("ascii", "ignore")
        .decode("ascii")
        or "download.pdf"
    )
    encoded_filename = quote(filename)
    return f'attachment; filename="{ascii_filename}"; filename*=UTF-8\'\'{encoded_filename}'


@app.get("/")
async def root() -> dict[str, Any]:
    # Endpoint minimo para comprobar vida del servicio y descubrir rutas.
    return {
        "name": app.title,
        "version": app.version,
        "docs": "/docs",
        "usage": "/usage",
        "dashboard": "/dashboard",
        "compress_endpoint": "/compress",
    }


@app.post("/compress")
async def compress_pdf(
    file: UploadFile = File(...),
    level: str = Query("medium", pattern="^(low|medium|high)$"),
    provider: str | None = Query(None, description="Forzar 'adobe'."),
) -> StreamingResponse:
    # Validaciones ligeras antes de delegar el trabajo real al servicio de compresion.
    if provider is not None and provider.lower() != "adobe":
        raise HTTPException(
            status_code=400,
            detail="Solo se admite el proveedor 'adobe'.",
        )

    if file.content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(
            status_code=400,
            detail=build_validation_detail(
                "Solo se permiten archivos PDF.",
                error=f"content_type invalido: {file.content_type or 'desconocido'}",
                field="file",
            ),
        )

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(
            status_code=400,
            detail=build_validation_detail(
                "El archivo esta vacio.",
                error="No se recibieron bytes en el archivo subido.",
                field="file",
            ),
        )

    filename = file.filename or "document.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail=build_validation_detail(
                "El archivo debe tener extension .pdf.",
                error=f"nombre de archivo invalido: {filename}",
                field="file",
            ),
        )

    result = await compression_service.compress(
        pdf_bytes=pdf_bytes,
        filename=filename,
        level=level,
        force_provider=provider,
    )

    # Expone metadatos utiles en cabeceras sin alterar el binario PDF devuelto.
    return StreamingResponse(
        BytesIO(result.content),
        media_type="application/pdf",
        headers={
            "X-Compression-Provider": result.provider,
            "X-Adobe-Account": result.account_email or "",
            "X-Original-Size": str(result.original_size),
            "X-Compressed-Size": str(result.compressed_size),
            "X-Provider-Attempts": ",".join(result.attempts),
            "Content-Disposition": build_content_disposition(result.filename),
        },
    )


@app.middleware("http")
async def log_requests(request: Request, call_next: Any) -> Any:
    # Trazado simple de inicio/fin para correlacionar peticiones con errores posteriores.
    logger.info(
        "Request iniciada metodo=%s path=%s query=%s",
        request.method,
        request.url.path,
        request.url.query,
    )
    try:
        response = await call_next(request)
        logger.info(
            "Request completada metodo=%s path=%s status=%s",
            request.method,
            request.url.path,
            response.status_code,
        )
        return response
    except Exception:
        logger.exception(
            "Error no controlado durante la request metodo=%s path=%s",
            request.method,
            request.url.path,
        )
        raise


app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, request_validation_exception_handler)


@app.exception_handler(Exception)
async def catch_all_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Ultima capa de seguridad para evitar respuestas HTML o errores sin control.
    return await unhandled_exception_handler(request, exc, gmail_notifier)
