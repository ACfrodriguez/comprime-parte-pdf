import json
import threading
from datetime import date
from pathlib import Path
from typing import Any, Optional

from .config import ADOBE_ACCOUNTS_FILE


# JSON store for Adobe account usage counters.
# The same adobe_accounts.json file stores credentials and usage metadata.
_FILE_LOCK = threading.Lock()


def _usage_file() -> Path:
    return ADOBE_ACCOUNTS_FILE


def _read_payload() -> dict[str, Any]:
    path = _usage_file()
    if not path.exists():
        return {"accounts": []}

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise RuntimeError("El JSON de cuentas Adobe debe ser un objeto.")

    accounts = payload.get("accounts")
    if accounts is None:
        payload["accounts"] = []
    elif not isinstance(accounts, list):
        raise RuntimeError("La clave 'accounts' del JSON de Adobe debe ser una lista.")

    return payload


def list_accounts() -> list[dict[str, Any]]:
    with _FILE_LOCK:
        payload = _read_payload()
        accounts = payload.get("accounts", [])
        return [
            _normalize_account(account)
            for account in accounts
            if isinstance(account, dict)
        ]


def get_account(email: str) -> dict[str, Any] | None:
    normalized_email = email.strip().lower()
    if not normalized_email:
        return None

    with _FILE_LOCK:
        payload = _read_payload()
        _, account = _find_account(payload, normalized_email)
        if account is None:
            return None
        return _normalize_account(account)


def add_account(email: str, client_id: str, client_secret: str) -> None:
    add_account_with_usage(email, client_id, client_secret, day_used=0, month_used=0)


def add_account_with_usage(
    email: str,
    client_id: str,
    client_secret: str,
    *,
    day_used: int = 0,
    month_used: int = 0,
) -> None:
    normalized_email = email.strip().lower()
    if not normalized_email:
        raise ValueError("El email de la cuenta no puede estar vacio.")
    if not client_id.strip() or not client_secret.strip():
        raise ValueError("El clientId y el clientSecret no pueden estar vacios.")

    with _FILE_LOCK:
        payload = _read_payload()
        accounts = payload.setdefault("accounts", [])
        for account in accounts:
            if not isinstance(account, dict):
                continue
            existing_email = str(account.get("email", "")).strip().lower()
            if existing_email == normalized_email:
                raise ValueError(f"Ya existe una cuenta configurada para {email}.")

        accounts.append(
            {
                "email": email.strip(),
                "clientId": client_id.strip(),
                "clientSecret": client_secret.strip(),
                "usage": {
                    "day": {date.today().isoformat(): int(day_used)},
                    "month": {date.today().strftime("%Y-%m"): int(month_used)},
                },
            }
        )
        _write_payload(payload)


def update_account(
    original_email: str,
    email: str,
    client_id: str,
    client_secret: str,
    *,
    day_used: int | None = None,
    month_used: int | None = None,
) -> None:
    normalized_original = original_email.strip().lower()
    normalized_email = email.strip().lower()
    if not normalized_original:
        raise ValueError("La cuenta original no puede estar vacia.")
    if not normalized_email:
        raise ValueError("El email de la cuenta no puede estar vacio.")
    if not client_id.strip() or not client_secret.strip():
        raise ValueError("El clientId y el clientSecret no pueden estar vacios.")

    with _FILE_LOCK:
        payload = _read_payload()
        accounts = payload.setdefault("accounts", [])
        target_index: int | None = None
        for index, account in enumerate(accounts):
            if not isinstance(account, dict):
                continue
            existing_email = str(account.get("email", "")).strip().lower()
            if existing_email == normalized_original:
                target_index = index
                break

        if target_index is None:
            raise ValueError(f"No existe una cuenta configurada para {original_email}.")

        for index, account in enumerate(accounts):
            if index == target_index or not isinstance(account, dict):
                continue
            existing_email = str(account.get("email", "")).strip().lower()
            if existing_email == normalized_email:
                raise ValueError(f"Ya existe una cuenta configurada para {email}.")

        current = accounts[target_index]
        current_usage = current.get("usage") if isinstance(current, dict) else {}
        normalized_usage = current_usage if isinstance(current_usage, dict) else {"day": {}, "month": {}}
        day_bucket = normalized_usage.get("day", {}) if isinstance(normalized_usage.get("day", {}), dict) else {}
        month_bucket = normalized_usage.get("month", {}) if isinstance(normalized_usage.get("month", {}), dict) else {}
        today = date.today().isoformat()
        current_month = date.today().strftime("%Y-%m")
        if day_used is not None:
            day_bucket[today] = int(day_used)
        if month_used is not None:
            month_bucket[current_month] = int(month_used)

        accounts[target_index] = {
            "email": email.strip(),
            "clientId": client_id.strip(),
            "clientSecret": client_secret.strip(),
            "usage": {
                "day": {str(key): int(value) for key, value in day_bucket.items()},
                "month": {str(key): int(value) for key, value in month_bucket.items()},
            },
        }
        _write_payload(payload)


def delete_account(email: str) -> bool:
    normalized_email = email.strip().lower()
    if not normalized_email:
        raise ValueError("El email de la cuenta no puede estar vacio.")

    with _FILE_LOCK:
        payload = _read_payload()
        accounts = payload.setdefault("accounts", [])
        filtered: list[dict[str, Any]] = []
        removed = False
        for account in accounts:
            if not isinstance(account, dict):
                continue
            existing_email = str(account.get("email", "")).strip().lower()
            if existing_email == normalized_email:
                removed = True
                continue
            filtered.append(account)

        payload["accounts"] = filtered
        _write_payload(payload)
        return removed


def _write_payload(payload: dict[str, Any]) -> None:
    path = _usage_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temp_path.replace(path)


def _normalize_account(account: dict[str, Any]) -> dict[str, Any]:
    usage = account.get("usage")
    if not isinstance(usage, dict):
        usage = {}

    day_usage = usage.get("day")
    if not isinstance(day_usage, dict):
        day_usage = {}

    month_usage = usage.get("month")
    if not isinstance(month_usage, dict):
        month_usage = {}

    account["usage"] = {
        "day": {str(key): int(value) for key, value in day_usage.items()},
        "month": {str(key): int(value) for key, value in month_usage.items()},
    }
    return account


def _find_account(
    payload: dict[str, Any], provider: str
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    accounts = payload.setdefault("accounts", [])
    normalized = provider.strip().lower()
    for account in accounts:
        if not isinstance(account, dict):
            continue
        email = str(account.get("email", "")).strip().lower()
        if email == normalized:
            return payload, account
    return payload, None


def init_usage_store() -> None:
    with _FILE_LOCK:
        path = _usage_file()
        if not path.exists():
            _write_payload({"accounts": []})
            return

        payload = _read_payload()
        accounts = payload.get("accounts", [])
        payload["accounts"] = [
            _normalize_account(account)
            for account in accounts
            if isinstance(account, dict)
        ]
        _write_payload(payload)


init_db = init_usage_store


def _upsert_usage(
    *,
    provider: str,
    period_type: str,
    period: str,
    by: int,
) -> None:
    with _FILE_LOCK:
        payload = _read_payload()
        _, account = _find_account(payload, provider)
        if account is None:
            raise KeyError(f"No existe una cuenta Adobe configurada para {provider}.")

        account = _normalize_account(account)
        bucket = account["usage"].setdefault(period_type, {})
        bucket[period] = int(bucket.get(period, 0)) + by
        _write_payload(payload)


def _set_usage(
    *, provider: str, period_type: str, period: str, used: int
) -> None:
    with _FILE_LOCK:
        payload = _read_payload()
        _, account = _find_account(payload, provider)
        if account is None:
            raise KeyError(f"No existe una cuenta Adobe configurada para {provider}.")

        account = _normalize_account(account)
        account["usage"].setdefault(period_type, {})[period] = int(used)
        _write_payload(payload)


def _get_usage(*, provider: str, period_type: str, period: str) -> int:
    with _FILE_LOCK:
        payload = _read_payload()
        _, account = _find_account(payload, provider)
        if account is None:
            return 0

        account = _normalize_account(account)
        bucket = account["usage"].get(period_type, {})
        return int(bucket.get(period, 0))


def increment(provider: str, by: int = 1, for_day: Optional[str] = None) -> None:
    """Incrementa el contador diario para `provider`.
    `for_day` debe estar en formato YYYY-MM-DD si se pasa.
    """
    day = for_day or date.today().isoformat()
    _upsert_usage(provider=provider, period_type="day", period=day, by=by)


# Fija el contador diario para `provider`.
def set_daily_used(provider: str, used: int, for_day: Optional[str] = None) -> None:
    """Fija el contador diario para `provider` a `used`.
    `for_day` debe estar en formato YYYY-MM-DD si se pasa.
    """
    day = for_day or date.today().isoformat()
    _set_usage(provider=provider, period_type="day", period=day, used=used)


def increment_month(
    provider: str, by: int = 1, for_month: Optional[str] = None
) -> None:
    """Incrementa el contador mensual para `provider`.
    `for_month` debe estar en formato YYYY-MM si se pasa.
    """
    month = for_month or date.today().strftime("%Y-%m")
    _upsert_usage(provider=provider, period_type="month", period=month, by=by)


def set_monthly_used(provider: str, used: int, for_month: Optional[str] = None) -> None:
    """Fija el contador mensual para `provider` a `used`.
    `for_month` debe estar en formato YYYY-MM si se pasa.
    """
    month = for_month or date.today().strftime("%Y-%m")
    _set_usage(provider=provider, period_type="month", period=month, used=used)


def get_monthly_used(provider: str, for_month: Optional[str] = None) -> int:
    month = for_month or date.today().strftime("%Y-%m")
    return _get_usage(provider=provider, period_type="month", period=month)


def get_used(provider: str, for_day: Optional[str] = None) -> int:
    day = for_day or date.today().isoformat()
    return _get_usage(provider=provider, period_type="day", period=day)
