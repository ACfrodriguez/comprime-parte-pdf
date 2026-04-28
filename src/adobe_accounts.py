import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import ADOBE_ACCOUNTS_FILE, logger


@dataclass(frozen=True)
class AdobeAccount:
    email: str
    client_id: str
    client_secret: str


def load_adobe_accounts(path: Path | None = None) -> list[AdobeAccount]:
    accounts_path = path or ADOBE_ACCOUNTS_FILE
    if not accounts_path.exists():
        logger.warning("No se encontro el archivo de cuentas Adobe: %s", accounts_path)
        return []

    try:
        payload = json.loads(accounts_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(
            f"No se pudo leer el archivo de cuentas Adobe: {accounts_path}"
        ) from exc

    accounts_data = payload.get("accounts")
    if not isinstance(accounts_data, list):
        raise RuntimeError(
            "El archivo de cuentas Adobe debe contener una clave 'accounts' con una lista."
        )

    accounts: list[AdobeAccount] = []
    seen_emails: set[str] = set()
    for index, item in enumerate(accounts_data, start=1):
        account = _parse_account(item, index=index)
        normalized_email = account.email.lower()
        if normalized_email in seen_emails:
            raise RuntimeError(
                f"Cuenta Adobe duplicada en el JSON: {account.email}"
            )
        seen_emails.add(normalized_email)
        accounts.append(account)

    return accounts


def _parse_account(item: Any, *, index: int) -> AdobeAccount:
    if not isinstance(item, dict):
        raise RuntimeError(
            f"La cuenta #{index} de Adobe debe ser un objeto con email, clientId y clientSecret."
        )

    email = str(item.get("email", "")).strip()
    client_id = str(item.get("clientId", "")).strip()
    client_secret = str(item.get("clientSecret", "")).strip()

    if not email or not client_id or not client_secret:
        raise RuntimeError(
            f"La cuenta #{index} de Adobe debe incluir email, clientId y clientSecret."
        )

    return AdobeAccount(
        email=email,
        client_id=client_id,
        client_secret=client_secret,
    )
