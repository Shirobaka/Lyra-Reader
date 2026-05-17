# Lyra Reader — Wiki

**Lyra Reader** is a self-hosted manga scanlation website built with **FastAPI** and **MySQL**. It ships with a full-featured admin panel, per-user preferences, Patreon early-access chapters, JWT authentication, i18n support (German / English), and a robust security layer.

---

## Quick Navigation

| Topic | Description |
|---|---|
| [Installation](Installation) | Docker Compose (recommended) and manual setup |
| [Configuration](Configuration) | All environment variables and database settings |
| [User Roles & Permissions](User-Roles-and-Permissions) | Role system, manga visibility levels |
| [Admin Panel](Admin-Panel) | Using the admin interface |
| [API Reference](API-Reference) | All REST endpoints, auth requirements, request/response shapes |
| [Architecture & Security](Architecture-and-Security) | Tech stack, database schema, security measures |

---

## Feature Overview

### Reader
- Browse manga projects and individual chapters
- Single-page and long-strip reader modes
- Chapter navigation (previous / next), visit tracking per user
- Chapter download as ZIP
- Patreon early-access release dates

### User Accounts
- Registration with email verification
- JWT authentication stored in httponly cookies with auto-refresh
- Password change and email change with re-verification
- Per-user theme (light / dark / auto) and custom accent color
- Profile page with reading history

### Admin Panel
- Dashboard with site-wide statistics (manga, chapters, users, views, downloads)
- Manga management — create, edit, delete; cover image upload
- Chapter management — upload ZIP archives, set release dates, delete
- User management — create, edit, assign roles, delete
- Partner link management with click tracking
- Site settings — SMTP, reCAPTCHA, site name, URLs
- Test Email button to verify SMTP configuration

### Security Highlights
- bcrypt password hashing
- JWT (HS256) stored in httponly + secure cookies
- Per-request CSP nonce via `ContextVar`
- Optional `SecurityHeadersMiddleware` (CSP, X-Frame-Options, HSTS, Permissions-Policy, …)
- Rate limiting on login (10 req / min via slowapi)
- Path traversal protection on ZIP extraction
- `hmac.compare_digest` for API token comparison

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web Framework | FastAPI + Uvicorn |
| Database ORM | SQLAlchemy 2 + PyMySQL |
| Database | MySQL 8 |
| Templates | Jinja2 |
| Auth | JWT (python-jose) + bcrypt / passlib |
| i18n | Babel / gettext |
| Email | smtplib (STARTTLS / SSL) |
| Containerization | Docker + Docker Compose |

---

## License

This project is licensed under the [MIT License](https://github.com/Shirobaka/Lyra-Reader/blob/main/LICENSE).
