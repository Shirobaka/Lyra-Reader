# Architecture & Security

---

## Tech Stack

| Layer | Technology | Version |
|---|---|---|
| Web framework | FastAPI | 0.136.1 |
| ASGI server | Uvicorn | 0.47.0 |
| Database ORM | SQLAlchemy | 2.0.49 |
| Database driver | PyMySQL | 1.1.3 |
| Database | MySQL | 8.0 |
| Templates | Jinja2 | 3.1.6 |
| Auth (JWT) | python-jose + PyJWT | 3.5.0 / 2.12.1 |
| Password hashing | passlib + bcrypt | 1.7.4 / 3.2.2 |
| Rate limiting | slowapi | 0.1.9 |
| i18n | Babel | 2.18.0 |
| Email | smtplib (stdlib) | — |
| Session middleware | itsdangerous / Starlette | 2.2.0 / 0.46.2 |
| HTTP client | requests | 2.34.2 |
| Containerization | Docker + Docker Compose | — |

---

## Database Schema

### `users`

| Column | Type | Notes |
|---|---|---|
| `id` | INT PK | Auto-increment. |
| `username` | VARCHAR(50) | Unique, indexed. |
| `email` | VARCHAR(100) | Unique, indexed. |
| `password_hash` | VARCHAR(255) | bcrypt hash. |
| `rights` | JSON | Array of role strings, e.g. `["Admin","Team Member"]`. |
| `email_verified` | BOOLEAN | `False` until verification link clicked. |
| `is_active` | BOOLEAN | Soft-disable without deleting the account. |
| `created_at` | DATETIME | Set by `func.now()`. |

### `user_preferences`

| Column | Type | Notes |
|---|---|---|
| `id` | INT PK | |
| `user_id` | INT FK → users | Unique (one-to-one). |
| `accent_color` | VARCHAR(7) | Hex color, default `#6366f1`. |
| `theme` | ENUM | `light`, `dark`, `auto` (default `auto`). |
| `created_at` | DATETIME | |
| `updated_at` | DATETIME | Updated on every save. |

### `manga`

| Column | Type | Notes |
|---|---|---|
| `id` | INT PK | |
| `name` | VARCHAR(255) | |
| `reader_mode` | ENUM | `single_page`, `long_stripe`. |
| `cover_path` | VARCHAR(500) | Relative path to cover image. |
| `url_slug` | VARCHAR(255) | Unique, used in URLs. |
| `tags` | JSON | Array of tag strings. |
| `description` | TEXT | |
| `age_rating` | INT | Minimum age. |
| `status` | ENUM | `Active`, `Cancelled`, `Planned`, `On Hold`, `Finished`, `Licensed`. |
| `hidden_status` | ENUM | `All`, `Logged-In`, `Patreon`, `Licensed`. |
| `created_at` | DATETIME | |

### `chapters`

| Column | Type | Notes |
|---|---|---|
| `id` | INT PK | |
| `manga_id` | INT FK → manga | |
| `name` | VARCHAR(255) | |
| `chapter_number` | DECIMAL(5,2) | Supports half-chapters (e.g. `12.50`). |
| `volume_number` | INT | |
| `release_date_regular` | DATETIME | Public release date. |
| `release_date_patreon` | DATETIME | Early-access date for Patreon users. |
| `clicks` | INT | View counter (incremented per page load). |
| `downloads` | INT | Download counter. |
| `file_path` | VARCHAR(500) | Path to the directory containing extracted page images. |
| `created_at` | DATETIME | |

### `chapter_visits`

| Column | Type | Notes |
|---|---|---|
| `id` | INT PK | |
| `user_id` | INT FK → users | |
| `chapter_id` | INT FK → chapters | |
| `visited_at` | DATETIME | Only one record per user per chapter per day. |

### `email_verifications`

| Column | Type | Notes |
|---|---|---|
| `id` | INT PK | |
| `user_id` | INT FK → users | |
| `email` | VARCHAR(100) | Target address (for change verification). |
| `verification_token` | VARCHAR(255) | Unique UUID token. |
| `expires_at` | DATETIME | |
| `verified` | BOOLEAN | |
| `created_at` | DATETIME | |

### `partners_table`

| Column | Type | Notes |
|---|---|---|
| `id` | INT PK | |
| `name` | VARCHAR(100) | |
| `url` | VARCHAR(255) | |
| `clicks` | INT | |

### `settings`

| Column | Type | Notes |
|---|---|---|
| `setting_key` | VARCHAR(100) PK | |
| `setting_value` | TEXT | |

---

## Security Architecture

### Password Hashing

Passwords are hashed with **bcrypt** via passlib's `CryptContext`. Plain-text passwords are never stored or logged.

### JWT Authentication

- Algorithm: **HS256**
- Tokens are stored in **httponly** cookies, preventing JavaScript access.
- Token lifetime is configurable via `ACCESS_TOKEN_EXPIRE_DAYS` (default 30 days).
- Tokens can also be passed via an `Authorization: Bearer` header for API clients.
- The auto-refresh endpoint (`POST /api/refresh-token`) issues a new token before the current one expires.

### Per-Request CSP Nonce

A cryptographically random nonce (`secrets.token_urlsafe(16)`) is generated for every HTTP request via an ASGI middleware and stored in a `ContextVar`. The nonce is injected into both the CSP header and all inline `<script>` tags via the Jinja2 template context. This prevents XSS payloads from executing even if injected into the page.

### Security Headers Middleware

When `SECURITY_HEADERS_ENABLED=True`, `SecurityHeadersMiddleware` appends the following headers to every response:

| Header | Value |
|---|---|
| `X-Frame-Options` | `DENY` |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `X-XSS-Protection` | `1; mode=block` |
| `X-Permitted-Cross-Domain-Policies` | `none` |
| `Permissions-Policy` | Disables geolocation, microphone, camera, payment, USB, etc. |
| `Content-Security-Policy` | Per-nonce policy; restricts scripts, frames, and connections. |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains; preload` *(production only)* |

Admin and API routes also receive aggressive cache-busting headers (`Cache-Control: no-store`).

### Rate Limiting

Login (`POST /api/login`) is rate-limited to **10 requests per minute per IP** using [slowapi](https://github.com/laurentS/slowapi).

### ZIP Extraction Safety

When extracting chapter ZIP archives, each member path is resolved with `os.path.realpath` and compared against the expected extraction directory. Any path that escapes the target directory (path traversal) causes an immediate `400` error and halts extraction.

### API Token Comparison

The `api_token` setting used by `/api/latest_releases` is compared with `hmac.compare_digest` to prevent timing attacks.

### URL Validation

Partner URLs are validated with `is_safe_url` before being stored or followed. Only `http://` and `https://` schemes are permitted.

---

## Request Lifecycle

```
Client
  │
  ▼
set_csp_nonce middleware     ← generates nonce, stores in ContextVar + request.state
  │
  ▼
SessionMiddleware             ← loads/saves signed session cookie
  │
  ▼
SecurityHeadersMiddleware     ← appends security headers (if enabled)
  │
  ▼
Route handler                 ← business logic, DB access via SQLAlchemy session
  │
  ▼
Jinja2 template               ← nonce injected into <script nonce="..."> tags
  │
  ▼
Response → Client
```
