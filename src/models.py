import os
from dataclasses import dataclass


# Este script define las estructuras y utilidades compartidas entre los modulos.
# Error comun para homogeneizar respuestas entre proveedores.
class ProviderError(Exception):
    def __init__(
        self,
        provider: str,
        message: str,
        *,
        code: str = "provider_error",
        credits_exhausted: bool = False,
        status_code: int = 502,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.message = message
        self.code = code
        self.credits_exhausted = credits_exhausted
        self.status_code = status_code


@dataclass
class CompressionResult:
    # Resultado normalizado que devuelve cualquier proveedor.
    content: bytes
    filename: str
    provider: str
    original_size: int
    compressed_size: int
    attempts: list[str]
    account_email: str | None = None


def build_output_filename(filename: str) -> str:
    # Mantiene un nombre de salida consistente para todos los proveedores.
    # Si falta extension, se fuerza .pdf para evitar respuestas ambiguas al cliente.
    stem, ext = os.path.splitext(filename or "document.pdf")
    return f"{stem}_compressed{ext or '.pdf'}"
