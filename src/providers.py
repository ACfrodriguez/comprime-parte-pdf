import asyncio
from io import BytesIO

import httpx

from .adobe_accounts import AdobeAccount
from .config import logger
from .models import CompressionResult, ProviderError, build_output_filename
from .usage_store import increment as usage_increment, increment_month


# Este modulo contiene la integracion con el proveedor externo de compresion.
def has_credit_errors(message: str, extra_tokens: list[str] | None = None) -> bool:
    # Reutiliza una deteccion simple de errores por cuota o creditos agotados.
    lowered = message.lower()
    tokens = [
        "quota",
        "credit",
        "credits",
        "limit",
        "insufficient",
        "too many requests",
    ]
    if extra_tokens:
        tokens.extend(extra_tokens)
    return any(token in lowered for token in tokens)


class AdobePdfProvider:
    name = "adobe"

    # Lee credenciales de Adobe desde una cuenta concreta del JSON.
    def __init__(self, account: AdobeAccount) -> None:
        self.account = account

    @property
    def account_email(self) -> str:
        return self.account.email

    @property
    # Indica si el proveedor puede usarse con la configuracion actual.
    def is_configured(self) -> bool:
        return bool(
            self.account.email and self.account.client_id and self.account.client_secret
        )

    # Comprende un PDF usando Adobe y registra el intento de uso.
    async def compress(
        self, pdf_bytes: bytes, filename: str, level: str
    ) -> CompressionResult:
        if not self.is_configured:
            raise ProviderError(
                self.name, "Adobe no esta configurado.", status_code=500
            )

        logger.info(
            "Compresion Adobe iniciada cuenta=%s archivo=%s nivel=%s",
            self.account_email,
            filename,
            level,
        )
        self._record_usage()

        try:
            # El SDK oficial de Adobe es bloqueante, por eso se ejecuta en un hilo.
            output = await asyncio.to_thread(self._compress_sync, pdf_bytes, level)
        except ProviderError:
            raise
        except Exception as exc:  # pragma: no cover
            raise self._classify_error(exc) from exc

        return CompressionResult(
            content=output,
            filename=build_output_filename(filename),
            provider=self.name,
            account_email=self.account_email,
            original_size=len(pdf_bytes),
            compressed_size=len(output),
            attempts=[self.name],
        )

    # Ejecuta el SDK de Adobe fuera del event loop asyncrono.
    def _compress_sync(self, pdf_bytes: bytes, level: str) -> bytes:
        # El SDK de Adobe es sincrono, por eso esta parte se ejecuta fuera del loop async.
        from adobe.pdfservices.operation.auth.service_principal_credentials import (
            ServicePrincipalCredentials,
        )
        from adobe.pdfservices.operation.exception.exceptions import (
            SdkException,
            ServiceApiException,
            ServiceUsageException,
        )
        from adobe.pdfservices.operation.pdf_services import PDFServices
        from adobe.pdfservices.operation.pdf_services_media_type import (
            PDFServicesMediaType,
        )
        from adobe.pdfservices.operation.pdfjobs.jobs.compress_pdf_job import (
            CompressPDFJob,
        )
        from adobe.pdfservices.operation.pdfjobs.params.compress_pdf.compress_pdf_params import (
            CompressPDFParams,
        )
        from adobe.pdfservices.operation.pdfjobs.params.compress_pdf.compression_level import (
            CompressionLevel,
        )
        from adobe.pdfservices.operation.pdfjobs.result.compress_pdf_result import (
            CompressPDFResult,
        )

        compression_level = {
            "low": CompressionLevel.LOW,
            "medium": CompressionLevel.MEDIUM,
            "high": CompressionLevel.HIGH,
        }.get(level, CompressionLevel.MEDIUM)

        try:
            # Flujo de Adobe: subir PDF, lanzar job, esperar resultado y descargar contenido.
            credentials = ServicePrincipalCredentials(
                client_id=self.account.client_id,
                client_secret=self.account.client_secret,
            )
            pdf_services = PDFServices(credentials=credentials)
            input_asset = pdf_services.upload(
                input_stream=BytesIO(pdf_bytes),
                mime_type=PDFServicesMediaType.PDF,
            )
            params = CompressPDFParams(compression_level=compression_level)
            job = CompressPDFJob(input_asset=input_asset, compress_pdf_params=params)
            location = pdf_services.submit(job)
            job_result = pdf_services.get_job_result(location, CompressPDFResult)
            result_asset = job_result.get_result().get_asset()
            stream_asset = pdf_services.get_content(result_asset)
            content = stream_asset.get_input_stream()

            if hasattr(content, "read"):
                return content.read()
            if isinstance(content, bytes):
                return content

            raise TypeError(
                f"Tipo de contenido inesperado devuelto por Adobe: {type(content).__name__}"
            )
        except (ServiceApiException, ServiceUsageException, SdkException) as exc:
            logger.warning(
                "Compresion Adobe fallo cuenta=%s error=%s",
                self.account_email,
                exc,
            )
            raise self._classify_error(exc) from exc

    # Convierte errores del SDK de Adobe en el contrato comun de la app.
    def _classify_error(self, exc: Exception) -> ProviderError:
        # Adapta excepciones del SDK a un formato comun para el resto del sistema.
        message = str(exc).strip() or "Error desconocido en Adobe PDF Services."
        credits_exhausted = has_credit_errors(
            message,
            extra_tokens=["usage limit", "rate limit", "service usage", "exceeded"],
        )
        return ProviderError(
            self.name,
            (
                "Adobe no tiene creditos disponibles o ha alcanzado su limite de uso."
                if credits_exhausted
                else f"Fallo Adobe PDF Services: {message}"
            ),
            code="credits_exhausted" if credits_exhausted else "provider_error",
            credits_exhausted=credits_exhausted,
            status_code=402 if credits_exhausted else 502,
        )

    # Registra el uso de Adobe en el archivo JSON compartido.
    def _record_usage(self) -> None:
        try:
            usage_increment(self.account_email)
            increment_month(self.account_email)
        except Exception:
            pass
