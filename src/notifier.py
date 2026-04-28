import base64
import os
from email.message import EmailMessage

import httpx

from .config import logger


# Este script encapsula el envio de alertas por correo usando la API de Gmail.
# Envia alertas por Gmail usando OAuth2 y refresh token.
class GmailNotifier:
    def __init__(self) -> None:
        # Se lee toda la configuracion una vez al crear el servicio.
        self.client_id = os.getenv("GMAIL_CLIENT_ID", "").strip()
        self.client_secret = os.getenv("GMAIL_CLIENT_SECRET", "").strip()
        self.refresh_token = os.getenv("GMAIL_REFRESH_TOKEN", "").strip()
        self.sender_email = os.getenv("GMAIL_SENDER_EMAIL", "").strip()
        self.recipient_email = os.getenv("ALERT_RECIPIENT_EMAIL", "").strip()
        self.token_uri = os.getenv(
            "GMAIL_TOKEN_URI", "https://oauth2.googleapis.com/token"
        ).strip()
        self.timeout = httpx.Timeout(20.0, connect=10.0)

    @property
    def is_configured(self) -> bool:
        return all(
            [
                self.client_id,
                self.client_secret,
                self.refresh_token,
                self.sender_email,
                self.recipient_email,
            ]
        )

    async def send_provider_failure_email(
        self,
        *,
        filename: str,
        level: str,
        provider: str,
        account_email: str | None = None,
        error_code: str,
        error_message: str,
        attempted: list[str],
    ) -> None:
        if not self.is_configured:
            logger.info("Notificacion Gmail omitida: faltan credenciales en .env.")
            return

        # Este aviso se lanza aunque despues otro proveedor consiga completar el trabajo.
        subject = f"[ApiCPdf] Fallo en proveedor {provider}"
        body = "\n".join(
            [
                "Se detecto un fallo en una API de compresion.",
                "",
                f"Proveedor: {provider}",
                f"Cuenta: {account_email or 'N/A'}",
                f"Archivo: {filename}",
                f"Nivel: {level}",
                f"Codigo: {error_code}",
                f"Intentos hasta el fallo: {', '.join(attempted) or provider}",
                "",
                "Detalle del error:",
                error_message,
            ]
        )
        await self._send_email(subject=subject, body=body)

    async def send_application_error_email(
        self, *, path: str, error_message: str
    ) -> None:
        if not self.is_configured:
            logger.info("Notificacion Gmail omitida: faltan credenciales en .env.")
            return

        # Se usa para errores inesperados fuera del flujo normal de proveedores.
        subject = "[ApiCPdf] Error no controlado en la API"
        body = "\n".join(
            [
                "Se detecto un error no controlado en la aplicacion.",
                "",
                f"Ruta: {path}",
                "",
                "Detalle del error:",
                error_message,
            ]
        )
        await self._send_email(subject=subject, body=body)

    async def _send_email(self, *, subject: str, body: str) -> None:
        # Gmail API espera el mensaje RFC822 serializado y codificado en base64 URL-safe.
        access_token = await self._fetch_access_token()

        message = EmailMessage()
        message["From"] = self.sender_email
        message["To"] = self.recipient_email
        message["Subject"] = subject
        message.set_content(body)

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={"raw": raw_message},
            )
            response.raise_for_status()

    async def _fetch_access_token(self) -> str:
        # Intercambia el refresh token por un access token valido para la API de Gmail.
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.token_uri,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token,
                    "grant_type": "refresh_token",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            payload = response.json()

        access_token = payload.get("access_token")
        if not access_token:
            raise RuntimeError("Gmail no devolvio un access_token valido.")
        return str(access_token)
