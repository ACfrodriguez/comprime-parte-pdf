from __future__ import annotations

import html
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi.responses import HTMLResponse, Response

_BASE_DIR = Path(__file__).resolve().parent
_TEMPLATES_DIR = _BASE_DIR / "templates"
_STATIC_DIR = _BASE_DIR / "static"


def _read_template(name: str) -> str:
    return (_TEMPLATES_DIR / name).read_text(encoding="utf-8")


def _read_static(name: str) -> str:
    return (_STATIC_DIR / name).read_text(encoding="utf-8")


def _count_span(value: int | float | str) -> str:
    numeric = str(value)
    return f'<span class="count-up" data-count="{html.escape(numeric)}">{html.escape(numeric)}</span>'


EDIT_ICON = """
<svg class="action-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
  <path d="M4 16.5V20h3.5L18.6 8.9l-3.5-3.5L4 16.5Zm15.7-9.2a1 1 0 0 0 0-1.4l-1.6-1.6a1 1 0 0 0-1.4 0l-1.3 1.3 3.5 3.5 1.3-1.8Z" fill="currentColor"/>
</svg>
"""

DELETE_ICON = """
<svg class="action-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
  <path d="M9 3.5h6l1 1.5H20v2H4v-2h4l1-1.5Zm1.5 6.5h2v8h-2v-8Zm3 0h2v8h-2v-8ZM7 8h10l-.7 11.2A2 2 0 0 1 14.3 21H9.7a2 2 0 0 1-1.99-1.8L7 8Z" fill="currentColor"/>
</svg>
"""


def render_css() -> Response:
    return Response(
        content=_read_static("dashboard.css"),
        media_type="text/css; charset=utf-8",
    )


def render_login_page(*, error: str | None = None) -> HTMLResponse:
    message = f"<p class='notice error'>{html.escape(error)}</p>" if error else ""
    disabled_note = ""
    from .auth import is_dashboard_enabled

    if not is_dashboard_enabled():
        disabled_note = (
            "<p class='notice warn'>Configura <code>DASHBOARD_ACCESS_TOKEN</code> "
            "en tu <code>.env</code> para habilitar el dashboard.</p>"
        )

    body = _read_template("login.html")
    body = body.replace("__MESSAGE__", message)
    body = body.replace("__DISABLED_NOTE__", disabled_note)
    return HTMLResponse(body)


def render_dashboard_page(
    *,
    metrics: dict[str, Any],
    accounts: list[dict[str, Any]],
    editing_account: dict[str, Any] | None = None,
    message: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    usage = metrics.get("usage", {})
    account_rows = []
    detail_cards = []
    today = date.today().isoformat()
    month = date.today().strftime("%Y-%m")
    for account in accounts:
        email = str(account.get("email", "")).strip()
        info = usage.get(email, {})
        account_usage = account.get("usage", {}) if isinstance(account.get("usage", {}), dict) else {}
        day_usage = account_usage.get("day", {}) if isinstance(account_usage.get("day", {}), dict) else {}
        month_usage = (
            account_usage.get("month", {}) if isinstance(account_usage.get("month", {}), dict) else {}
        )
        today_used = int(day_usage.get(today, 0))
        month_used = int(month_usage.get(month, 0))
        max_ = int(info.get("max", 0))
        month_remaining = max_ - month_used
        day_rows = "".join(
            f"<li><span>{html.escape(str(period))}</span><strong>{html.escape(str(value))}</strong></li>"
            for period, value in sorted(day_usage.items(), reverse=True)[:7]
        )
        month_rows = "".join(
            f"<li><span>{html.escape(str(period))}</span><strong>{html.escape(str(value))}</strong></li>"
            for period, value in sorted(month_usage.items(), reverse=True)[:6]
        )
        if not day_rows:
            day_rows = "<li class='empty-small'>Sin registros diarios</li>"
        if not month_rows:
            month_rows = "<li class='empty-small'>Sin registros mensuales</li>"
        account_rows.append(
            f"""
            <tr>
              <td>{html.escape(email)}</td>
              <td>{_count_span(today_used)}</td>
              <td>{_count_span(month_used)}</td>
              <td>{_count_span(month_remaining)}</td>
              <td>{_count_span(max_)}</td>
              <td>{'Si' if info.get("available") else 'No'}</td>
                  <td>
                <div class="row-actions">
                  <a class="ghost mini action-btn" href="/dashboard?edit={quote(email, safe='')}">
                    {EDIT_ICON}
                    <span>Editar</span>
                  </a>
                  <form method="post" action="/dashboard/accounts/delete" style="margin:0;">
                    <input type="hidden" name="email" value="{html.escape(email)}" />
                    <button type="submit" class="danger mini action-btn">
                      {DELETE_ICON}
                      <span>Eliminar</span>
                    </button>
                  </form>
                </div>
              </td>
            </tr>
            """
        )
        detail_cards.append(
            f"""
            <article class="account-detail">
              <header>
                <h3>{html.escape(email)}</h3>
                <p>Uso hoy: <strong>{_count_span(today_used)}</strong> | Uso mes: <strong>{_count_span(month_used)}</strong> | Max: <strong>{_count_span(max_)}</strong></p>
              </header>
              <div class="detail-grid">
                <section>
                  <h4>Ultimos dias</h4>
                  <ul class="usage-list">
                    {day_rows}
                  </ul>
                </section>
                <section>
                  <h4>Ultimos meses</h4>
                  <ul class="usage-list">
                    {month_rows}
                  </ul>
                </section>
              </div>
            </article>
            """
        )

    if not account_rows:
        account_rows.append(
            "<tr><td colspan='7' class='empty'>No hay cuentas configuradas todavia.</td></tr>"
        )
        detail_cards.append(
            "<article class='account-detail'><p class='empty-small'>No hay detalles disponibles.</p></article>"
        )

    notices = []
    if message:
        notices.append(f"<p class='notice success'>{html.escape(message)}</p>")
    if error:
        notices.append(f"<p class='notice error'>{html.escape(error)}</p>")

    editing_email = ""
    editing_client_id = ""
    editing_client_secret = ""
    editing_day_used = "0"
    editing_month_used = "0"
    form_title = "Agregar cuenta"
    form_action = "/dashboard/accounts"
    submit_label = "Guardar cuenta"
    cancel_html = ""
    if editing_account:
        editing_email = html.escape(str(editing_account.get("email", "")).strip())
        editing_client_id = html.escape(str(editing_account.get("clientId", "")).strip())
        editing_client_secret = html.escape(str(editing_account.get("clientSecret", "")).strip())
        account_usage = (
            editing_account.get("usage", {})
            if isinstance(editing_account.get("usage", {}), dict)
            else {}
        )
        day_usage = account_usage.get("day", {}) if isinstance(account_usage.get("day", {}), dict) else {}
        month_usage = (
            account_usage.get("month", {}) if isinstance(account_usage.get("month", {}), dict) else {}
        )
        editing_day_used = html.escape(str(int(day_usage.get(today, 0))))
        editing_month_used = html.escape(str(int(month_usage.get(month, 0))))
        form_title = f"Editar cuenta: {editing_email}"
        form_action = "/dashboard/accounts/update"
        submit_label = "Actualizar cuenta"
        cancel_html = "<a class='ghost mini' href='/dashboard'>Cancelar edicion</a>"

    body = _read_template("dashboard.html")
    body = body.replace("__NOTICES__", "".join(notices))
    body = body.replace("__ACCOUNT_ROWS__", "".join(account_rows))
    body = body.replace("__DETAIL_CARDS__", "".join(detail_cards))
    body = body.replace("__FORM_TITLE__", form_title)
    body = body.replace("__FORM_ACTION__", form_action)
    body = body.replace("__SUBMIT_LABEL__", submit_label)
    body = body.replace("__CANCEL_EDIT__", cancel_html)
    body = body.replace("__EDIT_EMAIL__", editing_email)
    body = body.replace("__EDIT_CLIENT_ID__", editing_client_id)
    body = body.replace("__EDIT_CLIENT_SECRET__", editing_client_secret)
    body = body.replace("__EDIT_DAY_USED__", editing_day_used)
    body = body.replace("__EDIT_MONTH_USED__", editing_month_used)
    body = body.replace("__USED__", _count_span(metrics.get("used", 0)))
    body = body.replace("__MAX__", _count_span(metrics.get("max", 0)))
    body = body.replace("__REMAINING__", _count_span(metrics.get("remaining", 0)))
    body = body.replace("__ACCOUNTS_COUNT__", _count_span(len(metrics.get("accounts", []))))
    return HTMLResponse(body)
