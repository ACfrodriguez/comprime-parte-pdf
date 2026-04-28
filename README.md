<a id="readme-top"></a>

<div align="center">

![python-shield]
![fastapi-shield]
![adobe-shield]
![version-shield]

</div>

<br />
<div align="center">
  <h1>API de Compresion de PDFs</h1>
  <h3 align="center">Servicio FastAPI para comprimir PDFs con Adobe PDF Services</h3>
  <p align="center">
    API interna para recibir un PDF, comprimirlo con Adobe y devolver el archivo resultante con logging y alertas por correo.
  </p>
</div>

<details>
  <summary>Tabla de Contenidos</summary>
  <ol>
    <li><a href="#sobre-el-proyecto">Sobre el Proyecto</a></li>
    <li><a href="#caracteristicas">Caracteristicas</a></li>
    <li><a href="#estructura">Estructura</a></li>
    <li><a href="#configuracion">Configuracion</a></li>
    <li><a href="#ejecucion-local">Ejecucion Local</a></li>
    <li><a href="#uso-de-la-api">Uso de la API</a></li>
    <li><a href="#errores-y-logs">Errores y Logs</a></li>
  </ol>
</details>

---

## Sobre el Proyecto

La API expone un endpoint `POST /compress` que recibe un archivo PDF por `multipart/form-data`, lo comprime usando Adobe PDF Services y devuelve directamente el PDF comprimido.

El servicio soporta:

* compresion con Adobe PDF Services
* rotacion entre varias cuentas de Adobe cargadas desde JSON
* validaciones de entrada con respuesta JSON clara
* logs en fichero y consola
* alertas por correo mediante la API de Gmail

<p align="right">(<a href="#readme-top">volver arriba</a>)</p>

## Caracteristicas

| Caracteristica | Descripcion |
| :--- | :--- |
| Subida de PDF | Recibe un archivo PDF en `POST /compress` |
| Niveles de compresion | `low`, `medium`, `high` |
| Proveedor forzado | Permite `provider=adobe` |
| Multicuenta | Usa varias credenciales de Adobe desde `adobe_accounts.json` |
| Validacion de credenciales | Devuelve error si no hay cuentas Adobe configuradas |
| Logging | Guarda requests, validaciones y errores en `logs/api.log` |
| Alertas por correo | Envia emails cuando falla la API o hay una excepcion no controlada |
| Uso de cuentas | `GET /usage` devuelve el resumen total y `GET /usage/{email}` el de una cuenta |
| Dashboard | `GET /dashboard` protege el panel con token, permite alta/baja de cuentas y muestra metricas |
| Swagger UI | Disponible en `/docs` |

<p align="right">(<a href="#readme-top">volver arriba</a>)</p>

## Estructura

La aplicacion esta separada por responsabilidades para mantener `main.py` pequeno y facil de seguir:

```text
src/
  __init__.py
  api_errors.py
  compression_service.py
  config.py
  dashboard/
    __init__.py
    auth.py
    renderer.py
    static/
      dashboard.css
    templates/
      dashboard.html
      login.html
  main.py
  models.py
  notifier.py
  providers.py
logs/
  api.log
```

Resumen de modulos:

* [src/main.py](src/main.py): endpoints, middleware y registro de handlers
* [src/compression_service.py](src/compression_service.py): coordinacion entre el flujo de compresion, rotacion de cuentas y gestion de credenciales
* [src/dashboard/](src/dashboard/): autenticacion, renderizado y estilos del panel web
* [src/providers.py](src/providers.py): integracion con Adobe PDF Services por cuenta
* [src/notifier.py](src/notifier.py): envio de alertas por Gmail
* [src/api_errors.py](src/api_errors.py): respuestas de error y validaciones
* [src/models.py](src/models.py): modelos y utilidades compartidas
* [src/adobe_accounts.py](src/adobe_accounts.py): carga y validacion de cuentas Adobe desde JSON
* [src/config.py](src/config.py): `.env`, rutas base, JSON de cuentas y logging

<p align="right">(<a href="#readme-top">volver arriba</a>)</p>

## Configuracion

### Requisitos

* Python 3.11 o compatible
* Credenciales de Adobe PDF Services
* Dependencias de [requirements.txt](requirements.txt)

Instalacion:

```powershell
pip install -r requirements.txt
```

### Variables de entorno

Configura el archivo `.env` en la raiz del proyecto.

#### Cuentas de Adobe

Las credenciales se cargan desde `adobe_accounts.json` con esta estructura:

```json
{
  "accounts": [
    {
      "email": "correo electronico de esa cuenta",
      "clientId": "el clientid",
      "clientSecret": "el client secret"
    }
  ]
}
```

El mismo archivo guarda también el uso acumulado de cada cuenta para rotar y calcular los creditos disponibles.

Si quieres cambiar la ruta del archivo, define `ADOBE_ACCOUNTS_FILE`.

#### Adobe PDF Services

| Variable | Descripcion |
| :--- | :--- |
| `ADOBE_ACCOUNTS_FILE` | Ruta al JSON con las cuentas de Adobe |
| `MAX_ADOBE_CREDITS` | Creditos mensuales por cuenta |
| `DASHBOARD_ACCESS_TOKEN` | Token para proteger `GET /dashboard` y sus acciones |

#### Alertas por Gmail

| Variable | Descripcion |
| :--- | :--- |
| `GMAIL_CLIENT_ID` | OAuth Client ID de Google |
| `GMAIL_CLIENT_SECRET` | OAuth Client Secret de Google |
| `GMAIL_REFRESH_TOKEN` | Refresh token con permisos para Gmail API |
| `GMAIL_SENDER_EMAIL` | Email remitente |
| `ALERT_RECIPIENT_EMAIL` | Email destinatario de alertas |
| `GMAIL_TOKEN_URI` | Endpoint OAuth de Google, por defecto `https://oauth2.googleapis.com/token` |

Ejemplo:

```env
ADOBE_ACCOUNTS_FILE=adobe_accounts.json
DASHBOARD_ACCESS_TOKEN=pon_un_token_largo_y_unico
GMAIL_CLIENT_ID=tu_google_client_id
GMAIL_CLIENT_SECRET=tu_google_client_secret
GMAIL_REFRESH_TOKEN=tu_refresh_token
GMAIL_SENDER_EMAIL=tu_correo@gmail.com
ALERT_RECIPIENT_EMAIL=alertas@tu-dominio.com
GMAIL_TOKEN_URI=https://oauth2.googleapis.com/token
```

> Si no configuras Gmail, la API sigue funcionando; simplemente no enviara correos de alerta.

> Si no configuras Adobe, `POST /compress` devolvera un error indicando que faltan cuentas.

<p align="right">(<a href="#readme-top">volver arriba</a>)</p>

## Ejecucion Local

Arranque recomendado:

```powershell
uvicorn src.main:app --reload
```

La API queda disponible por defecto en:

```text
http://127.0.0.1:8000
```

Rutas utiles:

* `GET /`
* `GET /usage`
* `GET /usage/{account_email}`
* `GET /dashboard`
* `POST /compress`
* `GET /docs`

<p align="right">(<a href="#readme-top">volver arriba</a>)</p>

## Uso de la API

### Uso de cuentas

```powershell
curl http://127.0.0.1:8000/usage
```

Ejemplo de respuesta:

```json
{
  "provider": "adobe",
  "scope": "all_accounts",
  "used": 240,
  "max": 1000,
  "remaining": 760,
  "accounts": ["cuenta1@correo.com", "cuenta2@correo.com"],
  "providers": ["cuenta1@correo.com", "cuenta2@correo.com"],
  "configured": {
    "cuenta1@correo.com": true,
    "cuenta2@correo.com": true
  },
  "blocked": [],
  "usage": {
    "cuenta1@correo.com": {
      "provider": "adobe",
      "period": "month",
      "used": 120,
      "max": 500,
      "remaining": 380,
      "available": true
    },
    "cuenta2@correo.com": {
      "provider": "adobe",
      "period": "month",
      "used": 120,
      "max": 500,
      "remaining": 380,
      "available": true
    }
  },
  "next_account": "cuenta1@correo.com",
  "log_file": "C:\\ruta\\al\\proyecto\\logs\\api.log"
}
```

`GET /usage/{email}` devuelve el uso de una cuenta concreta. Si usas una direccion con `@`, conviene URL-encodearla:

```powershell
curl "http://127.0.0.1:8000/usage/iv234131%40gmail.com"
```

Ejemplo de respuesta global:

```json
{
  "provider": "adobe",
  "scope": "all_accounts",
  "used": 240,
  "max": 1000,
  "remaining": 760,
  "accounts": [
    "cuenta1@correo.com",
    "cuenta2@correo.com"
  ]
}
```

Ejemplo de respuesta por cuenta:

```json
{
  "provider": "adobe",
  "scope": "account",
  "account": "iv234131@gmail.com",
  "used": 120,
  "max": 500,
  "remaining": 380
}
```

### Dashboard

Abre el panel en:

```text
http://127.0.0.1:8000/dashboard
```

Antes de entrar, define `DASHBOARD_ACCESS_TOKEN` en `.env`. El dashboard te pedira el token una sola vez y lo guardara en una cookie HttpOnly durante la sesion.

Desde el panel puedes:

* ver el uso total y el detalle por cuenta
* agregar nuevas cuentas con sus créditos iniciales
* editar cuentas, credenciales y contadores de uso
* eliminar cuentas existentes
* cerrar sesion

Los cambios se guardan directamente en `adobe_accounts.json`.

### Compresion

```powershell
curl -X POST "http://127.0.0.1:8000/compress?level=medium" ^
  -F "file=@C:\ruta\archivo.pdf" ^
  --output C:\ruta\archivo_comprimido.pdf
```

### Forzar Adobe

```powershell
curl -X POST "http://127.0.0.1:8000/compress?level=high&provider=adobe" ^
  -F "file=@C:\ruta\archivo.pdf" ^
  --output C:\ruta\archivo_adobe.pdf
```

### Swagger UI

FastAPI genera documentacion interactiva en:

```text
http://127.0.0.1:8000/docs
```

<p align="right">(<a href="#readme-top">volver arriba</a>)</p>

## Errores y Logs

### Respuestas de validacion

Cuando la request no es valida, la API devuelve JSON estructurado. Ejemplo:

```json
{
  "detail": {
    "message": "Solo se permiten archivos PDF.",
    "error": "content_type invalido: image/jpeg",
    "code": "validation_error",
    "field": "file"
  }
}
```

Para errores de validacion automaticos de FastAPI, la respuesta incluye `errors` con mas detalle.

### Errores de proveedor

Si falla Adobe, la API devuelve informacion del proveedor, la cuenta y del tipo de error.

```json
{
  "detail": {
    "message": "Fallo Adobe PDF Services: ...",
    "provider": "adobe",
    "account": "cuenta1@correo.com",
    "error": "...",
    "code": "provider_error"
  }
}
```

### Logs

Los logs se guardan en:

```text
logs/api.log
```

Ejemplos de eventos registrados:

* inicio y fin de cada request
* errores de validacion
* cuenta intentada en cada compresion
* errores por creditos agotados
* excepciones no controladas
* fallos al enviar alertas por email

### Alertas por correo

Si Gmail esta configurado, se envia un email cuando:

* falla Adobe
* se produce una excepcion no controlada en la API

<p align="right">(<a href="#readme-top">volver arriba</a>)</p>

---

<div align="center">
  <p><i>Documentacion actualizada para la configuracion actual del proyecto.</i></p>
  <p align="right">(<a href="#readme-top">volver arriba</a>)</p>
</div>

[python-shield]: https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white
[fastapi-shield]: https://img.shields.io/badge/FastAPI-API-009688?style=for-the-badge&logo=fastapi&logoColor=white
[adobe-shield]: https://img.shields.io/badge/Adobe-PDF_Services-FA0F00?style=for-the-badge&logo=adobe&logoColor=white
[version-shield]: https://img.shields.io/badge/version-v1.0.0-blue?style=for-the-badge
