# Lyra Reader

A self-hosted manga scanlation website built with FastAPI and MySQL. Supports multiple user roles, Patreon early-access chapters, per-request CSP nonces, i18n (German/English), and a full admin panel.

---

## Features

### Reader
- Browse manga projects and chapters
- Single-page and long-strip reader modes
- Chapter visit tracking per user
- Chapter download as ZIP
- Patreon early-access release dates

### User Accounts
- Registration with email verification
- JWT authentication (httponly cookie, auto-refresh)
- Password change
- Email change with re-verification
- Per-user theme (light / dark / auto) and accent color
- Profile page with reading history

### Admin Panel (`/admin`)
- Dashboard with site statistics (manga, chapters, users, views, downloads)
- Manga management: create, edit, delete; cover image upload
- Chapter management: upload ZIP archives, set release dates, delete
- User management: create, edit, assign roles, delete
- Partner link management with click tracking
- Site settings (SMTP, reCAPTCHA, site name, URLs, etc.)
- Test email button to verify SMTP configuration

### Security
- bcrypt password hashing
- JWT tokens (HS256) stored in httponly secure cookies
- Per-request CSP nonce via `ContextVar`
- Optional `SecurityHeadersMiddleware` (X-Frame-Options, CSP, Permissions-Policy, etc.)
- Rate limiting on login (10 req/min via slowapi)
- Path traversal protection on ZIP extraction
- `hmac.compare_digest` for API token comparison

### i18n
- Babel/gettext translations
- German and English locale files included
- Language configured via `APP_LANGUAGE` env var

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI + Uvicorn |
| Database ORM | SQLAlchemy 2 + PyMySQL |
| Database | MySQL 8 |
| Templates | Jinja2 |
| Auth | JWT (PyJWT / python-jose) + bcrypt |
| i18n | Babel / gettext |
| Email | smtplib (STARTTLS / SSL) |
| Containerization | Docker + Docker Compose |

---

## Installation

### Option A — Docker Compose (recommended)

**Requirements:** Docker and Docker Compose installed.

1. Download `docker-compose.yml`:
   ```bash
   curl -O https://raw.githubusercontent.com/Shirobaka/Lyra-Reader/main/docker-compose.yml
   ```

2. Create a `.env` file in the same directory (see [Environment Variables](#environment-variables)):
   ```bash
   cp .env.example .env   # or create it manually
   ```
   Edit `.env` and set at minimum `SECRET_KEY`, `SESSION_SECRET_KEY`, `DATABASE_USER`, `DATABASE_PASSWORD`, and `DATABASE_NAME`.

3. Start the stack:
   ```bash
   docker compose up -d
   ```

The app will be available at `http://localhost:8000`.

On first start the database schema and default settings are created automatically — no manual SQL import needed.

---

### Option B — Manual / Local

**Requirements:** Python 3.11+, MySQL 8.

1. Clone the repository:
   ```bash
   git clone https://github.com/Shirobaka/Lyra-Reader.git
   cd Lyra-Reader
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate        # Windows
   source .venv/bin/activate     # Linux / macOS
   ```

3. Install dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```

4. Create a `.env` file (see [Environment Variables](#environment-variables)).

5. Create the MySQL database:
   ```sql
   CREATE DATABASE lyra-reader CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
   CREATE USER 'lyra-reader'@'localhost' IDENTIFIED BY 'your_password';
   GRANT ALL PRIVILEGES ON lyra-reader.* TO 'lyra-reader'@'localhost';
   ```

6. Run the application:
   ```bash
   python run.py
   ```

   Tables and default settings are created automatically on first startup.

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the values.

| Variable | Default | Description |
|---|---|---|
| `ENVIRONMENT` | `development` | `production` or `development` |
| `DEBUG_MODE` | `False` | Enables `/admin/docs` and `/admin/redoc` when `True` |
| `APP_LANGUAGE` | `de` | UI language (`de` or `en`) |
| `SECRET_KEY` | — | **Required.** Secret for JWT signing. Generate with `openssl rand -hex 32` |
| `SESSION_SECRET_KEY` | — | **Required.** Secret for session middleware. Generate with `openssl rand -hex 32` |
| `ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_DAYS` | `30` | Default JWT lifetime in days |
| `SECURITY_HEADERS_ENABLED` | `True` | Adds security headers (CSP, X-Frame-Options, etc.) |
| `DATABASE_HOST` | `db` | MySQL host (automatically overridden to `db` in Docker Compose) |
| `DATABASE_PORT` | `3306` | MySQL port |
| `DATABASE_USER` | — | **Required.** MySQL username |
| `DATABASE_PASSWORD` | — | **Required.** MySQL password |
| `DATABASE_NAME` | — | **Required.** MySQL database name |
| `RECAPTCHA_ENABLED` | `False` | Enable Google reCAPTCHA v2 on registration |
| `RECAPTCHA_SITE_KEY` | — | reCAPTCHA site key |
| `RECAPTCHA_SECRET_KEY` | — | reCAPTCHA secret key |
| `ALLOWED_IMAGE_EXTENSIONS` | `.jpg,.jpeg,.png,.webp,.gif` | Allowed cover/page image extensions |
| `MAX_UPLOAD_SIZE` | `104857600` | Max upload size in bytes (default 100 MB) |

---

## First Login

The **first user to register** is automatically granted full admin rights:

```
Admin, Team Member, Chapter Upload, Manga Manage, User Manage
```

Their account is also immediately active and email-verified, so no SMTP setup is required for the initial setup.

---

## User Roles

Roles are stored as a JSON array on the user record. Multiple roles can be assigned.

| Role | Access |
|---|---|
| `Admin` | Full access to all admin pages and APIs |
| `Manga Manage` | Create, edit, delete manga and chapters |
| `Chapter Upload` | Upload chapters |
| `User Manage` | View and edit other users |
| `Team Member` | Team badge on profile |
| `Patreon` | Access to Patreon early-release chapters |

---

## Manga Visibility

| `hidden_status` | Who can see it |
|---|---|
| `All` | Everyone including guests |
| `Logged-In` | Logged-in users only |
| `Patreon` | Users with the `Patreon` role |
| `Licensed` | Users with `Manga Manage` only |

---

## SMTP / Email

Email is used for account verification and email-change confirmation. Configure via the Admin → Settings page or directly in the database.

| Setting Key | Description |
|---|---|
| `smtp_server` | SMTP hostname |
| `smtp_port` | Port (typically `587` for STARTTLS, `465` for SSL) |
| `smtp_username` | SMTP login username |
| `smtp_password` | SMTP login password |
| `smtp_from_email` | Sender address |
| `smtp_from_name` | Sender display name |
| `smtp_use_tls` | `true` to use STARTTLS |
| `smtp_use_ssl` | `true` to use SMTP over SSL (port 465) |

Use the **Test Email** button in Admin → Settings to verify your configuration.

---

## API Endpoints

### Public
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/manga/{id}/chapters` | List chapters for a manga |
| `GET` | `GET /api/latest_releases?token=&release_type=` | Latest releases (requires API token) |

### Authenticated
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/login` | Login |
| `POST` | `/api/logout` | Logout |
| `POST` | `/api/register` | Register |
| `POST` | `/api/refresh-token` | Refresh JWT cookie |
| `GET` | `/api/download/{chapter_id}` | Download chapter as ZIP |
| `GET` | `/api/profile/stats/{userid}` | Reading statistics |
| `POST` | `/api/profile/preferences` | Update theme / accent color |
| `POST` | `/api/profile/password` | Change password |
| `POST` | `/api/profile/email` | Request email change |

### Admin only
| Method | Path | Description |
|---|---|---|
| `POST/PUT/DELETE` | `/api/manga` | Manage manga |
| `POST/DELETE` | `/api/chapter` | Manage chapters |
| `POST/PUT/DELETE` | `/api/users` | Manage users |
| `POST/DELETE` | `/api/partners` | Manage partners |
| `POST/DELETE` | `/api/settings` | Manage settings |
| `GET` | `/api/admin/stats` | Site statistics |
| `GET` | `/api/test-email` | Send test email |

---

## Project Structure

```
.
├── backend/
│   ├── app.py              # All routes and business logic
│   ├── auth.py             # JWT helpers, password hashing
│   ├── database.py         # SQLAlchemy models and engine
│   ├── requirements.txt
│   └── middleware/
│       └── security.py     # Security headers middleware
├── frontend/
│   ├── locales/            # Babel translation files (de, en)
│   ├── static/
│   │   └── css/
│   └── templates/
│       ├── base.html
│       ├── index.html
│       ├── project.html
│       ├── projects.html
│       ├── reader.html
│       ├── profile.html
│       ├── admin/
│       └── auth/
├── uploads/                # Covers, chapter images, temp ZIPs (persisted as Docker volume)
├── run.py                  # Entrypoint
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

## License

This project is licensed under the [MIT License](LICENSE).
