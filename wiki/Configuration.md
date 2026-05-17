# Configuration

All runtime configuration is read from a `.env` file placed in the project root (next to `docker-compose.yml`).

---

## Environment Variables

### Application

| Variable | Default | Required | Description |
|---|---|---|---|
| `ENVIRONMENT` | `development` | | `production` or `development`. Controls HSTS and other production-only headers. |
| `DEBUG_MODE` | `False` | | Set to `True` to expose `/admin/docs` (Swagger UI) and `/admin/redoc`. **Never enable in production.** |
| `APP_LANGUAGE` | `de` | | UI language. Supported values: `de` (German), `en` (English). |

### Security & Auth

| Variable | Default | Required | Description |
|---|---|---|---|
| `SECRET_KEY` | — | ✅ | Secret used to sign JWT tokens. Generate with `openssl rand -hex 32`. |
| `SESSION_SECRET_KEY` | — | ✅ | Secret for Starlette's session middleware. Generate separately with `openssl rand -hex 32`. |
| `ALGORITHM` | `HS256` | | JWT signing algorithm. |
| `ACCESS_TOKEN_EXPIRE_DAYS` | `30` | | JWT lifetime in days. |
| `SECURITY_HEADERS_ENABLED` | `True` | | When `True`, attaches CSP, X-Frame-Options, HSTS (production only), and other security headers to every response. |

### Database

| Variable | Default | Required | Description |
|---|---|---|---|
| `DATABASE_HOST` | `db` | ✅ | MySQL hostname. Set to `db` in Docker Compose, `localhost` for manual installs. |
| `DATABASE_PORT` | `3306` | | MySQL port. |
| `DATABASE_USER` | — | ✅ | MySQL username. |
| `DATABASE_PASSWORD` | — | ✅ | MySQL password. |
| `DATABASE_NAME` | — | ✅ | MySQL database name. |

### reCAPTCHA

| Variable | Default | Required | Description |
|---|---|---|---|
| `RECAPTCHA_ENABLED` | `False` | | Enable Google reCAPTCHA v2 on the registration form. |
| `RECAPTCHA_SITE_KEY` | — | | reCAPTCHA site key (public). |
| `RECAPTCHA_SECRET_KEY` | — | | reCAPTCHA secret key (server-side verification). |

### Uploads

| Variable | Default | Required | Description |
|---|---|---|---|
| `ALLOWED_IMAGE_EXTENSIONS` | `.jpg,.jpeg,.png,.webp,.gif` | | Comma-separated list of permitted cover / page image extensions. |
| `MAX_UPLOAD_SIZE` | `104857600` | | Maximum upload size in bytes (default: 100 MB). |

---

## `.env.example`

```dotenv
# ── Application ────────────────────────────────────────────────
ENVIRONMENT=development
DEBUG_MODE=False
APP_LANGUAGE=de

# ── Security ───────────────────────────────────────────────────
SECRET_KEY=changeme
SESSION_SECRET_KEY=changeme
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_DAYS=30
SECURITY_HEADERS_ENABLED=True

# ── Database ───────────────────────────────────────────────────
DATABASE_HOST=db
DATABASE_PORT=3306
DATABASE_USER=lyra
DATABASE_PASSWORD=changeme
DATABASE_NAME=lyra_reader

# ── reCAPTCHA (optional) ───────────────────────────────────────
RECAPTCHA_ENABLED=False
RECAPTCHA_SITE_KEY=
RECAPTCHA_SECRET_KEY=

# ── Uploads ────────────────────────────────────────────────────
ALLOWED_IMAGE_EXTENSIONS=.jpg,.jpeg,.png,.webp,.gif
MAX_UPLOAD_SIZE=104857600
```

---

## Database-Stored Settings

The following settings are managed through **Admin → Settings** and are persisted in the `settings` table. They can also be set directly in the database.

### General

| Key | Default | Description |
|---|---|---|
| `site_name` | `Lyra Reader` | Display name shown in the page title and header. |
| `discord_enabled` | `false` | Show Discord widget. |
| `patreon_url` | `` | Patreon page URL (shown in navigation). |
| `kofi_url` | `` | Ko-fi page URL. |
| `discord_url` | `` | Discord invite URL. |
| `allow_registration` | `true` | Allow new user registrations. |
| `api_token` | `` | Bearer token for the public `/api/latest_releases` endpoint. |

### SMTP / Email

| Key | Description |
|---|---|
| `smtp_server` | SMTP hostname (e.g. `smtp.gmail.com`). |
| `smtp_port` | Port — typically `587` for STARTTLS, `465` for SSL. |
| `smtp_username` | SMTP login username. |
| `smtp_password` | SMTP login password. |
| `smtp_from_email` | Sender address (e.g. `noreply@example.com`). |
| `smtp_from_name` | Sender display name. |
| `smtp_use_tls` | `true` to use STARTTLS. |
| `smtp_use_ssl` | `true` to use SMTP over SSL (port 465). |

> Use **Admin → Settings → Test Email** to verify your SMTP configuration without restarting the server.
