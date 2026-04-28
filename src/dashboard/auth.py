from __future__ import annotations

from fastapi import Request

from ..config import DASHBOARD_ACCESS_TOKEN

DASHBOARD_COOKIE = "dashboard_access"


def is_dashboard_enabled() -> bool:
    return bool(DASHBOARD_ACCESS_TOKEN.strip())


def get_dashboard_token(request: Request) -> str:
    return request.cookies.get(DASHBOARD_COOKIE, "").strip()


def is_authenticated(request: Request) -> bool:
    return is_dashboard_enabled() and get_dashboard_token(request) == DASHBOARD_ACCESS_TOKEN
