import asyncio
import threading
from typing import Any

from fastapi import HTTPException

from .adobe_accounts import load_adobe_accounts
from .config import LOG_FILE, MAX_ADOBE_CREDITS, logger
from .models import CompressionResult, ProviderError
from .notifier import GmailNotifier
from .providers import AdobePdfProvider
from .usage_store import get_monthly_used


# This module coordinates Adobe account rotation, fallback, and the main compression flow.
class RotatingCompressionService:
    def __init__(self, notifier: GmailNotifier | None = None) -> None:
        self._request_index = 0
        self._lock = threading.Lock()
        self._notifier = notifier

    def get_status(self) -> dict[str, Any]:
        configured = self._configured_providers()
        available = self._available_providers()
        configured_names = [p.account_email for p in configured]
        available_names = [p.account_email for p in available]
        blocked = [n for n in configured_names if n not in available_names]

        usage: dict[str, dict[str, Any]] = {}
        for provider in configured:
            email = provider.account_email
            used = self._provider_used(email)
            max_ = self._provider_max_credits(email)
            usage[email] = {
                "provider": provider.name,
                "period": self._provider_period(email),
                "used": used,
                "max": max_,
                "remaining": max_ - used,
            }

        current = self._ordered_providers(available)[0].account_email if available else None

        return {
            "provider": "adobe",
            "providers": available_names,
            "accounts": configured_names,
            "configured": {email: True for email in configured_names},
            "blocked": blocked,
            "usage": usage,
            "next_provider": current,
            "next_account": current,
            "log_file": str(LOG_FILE),
        }

    def get_credit_summary(self) -> dict[str, Any]:
        configured = self._configured_providers()
        providers: list[dict[str, Any]] = []
        configured_names = {p.account_email for p in configured}
        for provider in configured:
            email = provider.account_email
            max_ = self._provider_max_credits(email)
            used = self._provider_used(email)
            remaining = max_ - used
            providers.append(
                {
                    "provider": provider.name,
                    "email": email,
                    "configured": True,
                    "period": self._provider_period(email),
                    "used": used,
                    "max": max_,
                    "remaining": remaining,
                    "available": remaining > 0,
                }
            )

        if not providers and not configured_names:
            providers.append(
                {
                    "provider": "adobe",
                    "email": None,
                    "configured": False,
                    "period": "month",
                    "used": None,
                    "max": MAX_ADOBE_CREDITS,
                    "remaining": None,
                    "available": False,
                }
            )

        return {"provider": "adobe", "providers": providers, "accounts": providers}

    def get_usage(self, identifier: str | None = None) -> dict[str, Any]:
        normalized = (identifier or "").strip().lower()
        if not normalized or normalized == "adobe":
            configured = self._configured_providers()
            available = self._available_providers()
            configured_names = [provider.account_email for provider in configured]
            available_names = [provider.account_email for provider in available]
            blocked = [name for name in configured_names if name not in available_names]
            usage: dict[str, dict[str, Any]] = {}
            used = 0
            for provider in configured:
                email = provider.account_email
                provider_used = self._provider_used(email)
                max_ = self._provider_max_credits(email)
                usage[email] = {
                    "provider": provider.name,
                    "period": self._provider_period(email),
                    "used": provider_used,
                    "max": max_,
                    "remaining": max_ - provider_used,
                    "available": (max_ - provider_used) > 0,
                }
                used += provider_used
            max_ = len(configured) * MAX_ADOBE_CREDITS
            remaining = max_ - used
            current = self._ordered_providers(available)[0].account_email if available else None
            return {
                "provider": "adobe",
                "scope": "all_accounts",
                "used": used,
                "max": max_,
                "remaining": remaining,
                "accounts": configured_names,
                "providers": available_names,
                "configured": {email: True for email in configured_names},
                "blocked": blocked,
                "usage": usage,
                "next_provider": current,
                "next_account": current,
                "log_file": str(LOG_FILE),
            }

        provider = self._find_provider_by_email(normalized)
        if provider is None:
            raise HTTPException(
                status_code=400,
                detail="Solo se admite 'adobe' o el email de una cuenta configurada.",
            )

        used = self._provider_used(provider.account_email)
        max_ = self._provider_max_credits(provider.account_email)
        remaining = max_ - used
        return {
            "provider": "adobe",
            "scope": "account",
            "account": provider.account_email,
            "configured": True,
            "period": self._provider_period(provider.account_email),
            "used": used,
            "max": max_,
            "remaining": remaining,
            "available": remaining > 0,
        }

    async def compress(
        self,
        pdf_bytes: bytes,
        filename: str,
        level: str,
        force_provider: str | None = None,
    ) -> CompressionResult:
        providers = self._available_providers()
        if not providers:
            raise HTTPException(
                status_code=500,
                detail="Configura al menos una cuenta de Adobe en adobe_accounts.json para usar la compresion.",
            )

        if force_provider and force_provider.strip().lower() != "adobe":
            raise HTTPException(
                status_code=400,
                detail="Solo se admite el proveedor 'adobe'.",
            )

        ordered_providers = self._ordered_providers(providers)
        attempted: list[str] = []
        errors: list[dict[str, Any]] = []

        for provider in ordered_providers:
            attempted.append(provider.account_email)
            try:
                turn = len(attempted)
                logger.info(
                    "Intentando compresion archivo=%s nivel=%s turno=%s/%s cuenta=%s",
                    filename,
                    level,
                    turn,
                    len(ordered_providers),
                    provider.account_email,
                )
                result = await provider.compress(pdf_bytes, filename, level)
                result.attempts = attempted.copy()
                self._advance_rotation(providers, provider.account_email)
                if len(attempted) > 1:
                    logger.warning(
                        "Compresion completada tras fallback archivo=%s turno_final=%s/%s cuenta_final=%s intentos=%s",
                        filename,
                        turn,
                        len(ordered_providers),
                        result.account_email or result.provider,
                        ",".join(attempted),
                    )
                else:
                    logger.info(
                        "Compresion completada archivo=%s turno=%s/%s cuenta=%s",
                        filename,
                        turn,
                        len(ordered_providers),
                        result.account_email or result.provider,
                    )
                return result
            except ProviderError as exc:
                self._handle_provider_error(
                    filename,
                    level,
                    exc,
                    attempted.copy(),
                    account_email=provider.account_email,
                )
                errors.append(
                    {
                        "provider": exc.provider,
                        "account": provider.account_email,
                        "error": exc.message,
                        "code": exc.code,
                        "credits_exhausted": exc.credits_exhausted,
                    }
                )

        all_credits_exhausted = bool(errors) and all(
            error["credits_exhausted"] for error in errors
        )
        raise HTTPException(
            status_code=402 if all_credits_exhausted else 502,
            detail={
                "message": (
                    "No quedan creditos disponibles en ninguna de las cuentas configuradas."
                    if all_credits_exhausted
                    else "Todas las cuentas de Adobe fallaron al intentar comprimir el PDF."
                ),
                "attempted_providers": attempted,
                "attempted_accounts": attempted,
                "accounts": errors,
            },
        )

    def _load_providers(self) -> list[AdobePdfProvider]:
        accounts = load_adobe_accounts()
        return [AdobePdfProvider(account) for account in accounts]

    def _find_provider_by_email(self, email: str) -> AdobePdfProvider | None:
        normalized = email.strip().lower()
        for provider in self._load_providers():
            if provider.account_email.lower() == normalized:
                return provider
        return None

    def _configured_providers(self) -> list[AdobePdfProvider]:
        return [provider for provider in self._load_providers() if provider.is_configured]

    def _available_providers(self) -> list[AdobePdfProvider]:
        providers: list[AdobePdfProvider] = []
        for provider in self._configured_providers():
            remaining = self._remaining_for_provider(provider)
            if remaining > 0:
                providers.append(provider)
        return providers

    def _ordered_providers(
        self, providers: list[AdobePdfProvider]
    ) -> list[AdobePdfProvider]:
        # Rotacion estricta por turnos: respeta el orden del JSON y avanza una cuenta por request.
        if not providers:
            return []

        with self._lock:
            start_idx = self._request_index % len(providers)

        return providers[start_idx:] + providers[:start_idx]

    def _advance_rotation(
        self, providers: list[AdobePdfProvider], provider_email: str
    ) -> None:
        with self._lock:
            if providers:
                for idx, provider in enumerate(providers):
                    if provider.account_email.lower() == provider_email.lower():
                        self._request_index = (idx + 1) % len(providers)
                        break
                else:
                    self._request_index = (self._request_index + 1) % len(providers)
            else:
                self._request_index = 0

    def _remaining_for_provider(self, provider: AdobePdfProvider) -> int:
        return self._provider_max_credits(provider.account_email) - self._provider_used(
            provider.account_email
        )

    def _provider_max_credits(self, provider_email: str) -> int:
        return MAX_ADOBE_CREDITS

    def _provider_period(self, provider_email: str) -> str:
        return "month"

    def _provider_used(self, provider_email: str) -> int:
        return get_monthly_used(provider_email)

    def _handle_provider_error(
        self,
        filename: str,
        level: str,
        exc: ProviderError,
        attempted: list[str],
        *,
        account_email: str | None = None,
    ) -> None:
        logger.warning(
            (
                "Fallo de cuenta archivo=%s nivel=%s cuenta=%s proveedor=%s code=%s "
                "credits_exhausted=%s intentos=%s error=%s"
            ),
            filename,
            level,
            account_email,
            exc.provider,
            exc.code,
            exc.credits_exhausted,
            ",".join(attempted),
            exc.message,
        )
        if self._notifier:
            asyncio.create_task(
                self._notify_provider_failure(
                    filename, level, exc, attempted, account_email=account_email
                )
            )

    async def _notify_provider_failure(
        self,
        filename: str,
        level: str,
        exc: ProviderError,
        attempted: list[str],
        *,
        account_email: str | None = None,
    ) -> None:
        try:
            await self._notifier.send_provider_failure_email(
                filename=filename,
                level=level,
                provider=exc.provider,
                account_email=account_email,
                error_code=exc.code,
                error_message=exc.message,
                attempted=attempted,
            )
        except Exception:
            logger.exception(
                "No se pudo enviar el correo de alerta para proveedor=%s cuenta=%s archivo=%s",
                exc.provider,
                account_email,
                filename,
            )
