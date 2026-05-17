# Installation

Lyra Reader can be deployed in two ways: via **Docker Compose** (recommended for production) or **manually** for local development.

---

## Option A — Docker Compose (Recommended)

### Prerequisites
- [Docker](https://docs.docker.com/get-docker/) ≥ 24
- [Docker Compose](https://docs.docker.com/compose/) ≥ 2 (included in Docker Desktop)

### Steps

**1. Download `docker-compose.yml`**

```bash
curl -O https://raw.githubusercontent.com/Shirobaka/Lyra-Reader/main/docker-compose.yml
```

**2. Create `.env`**

```bash
cp .env.example .env   # or create the file manually
```

Edit `.env` and set at minimum:

| Variable | Notes |
|---|---|
| `SECRET_KEY` | Generate with `openssl rand -hex 32` |
| `SESSION_SECRET_KEY` | Generate with `openssl rand -hex 32` |
| `DATABASE_USER` | MySQL username |
| `DATABASE_PASSWORD` | MySQL password |
| `DATABASE_NAME` | MySQL database name |

See [Configuration](Configuration) for the full variable reference.

**3. Start the stack**

```bash
docker compose up -d
```

The application will be available at **http://localhost:8000**.

The database schema and default settings are created automatically on the first start — no manual SQL import is needed.

**4. (Optional) Expose via reverse proxy**

Place Nginx or Caddy in front of the app container and forward requests to `http://app:8000`. Enable `SECURITY_HEADERS_ENABLED=True` so that HSTS and full CSP headers are sent.

---

## Option B — Manual / Local

### Prerequisites
- Python 3.11+
- MySQL 8

### Steps

**1. Clone the repository**

```bash
git clone https://github.com/Shirobaka/Lyra-Reader.git
cd Lyra-Reader
```

**2. Create a virtual environment**

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate
```

**3. Install dependencies**

```bash
pip install -r backend/requirements.txt
```

**4. Create `.env`**

Copy `.env.example` to `.env` and fill in your values. See [Configuration](Configuration) for details.

**5. Set up the MySQL database**

```sql
CREATE DATABASE `lyra-reader`
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_general_ci;

CREATE USER 'lyra-reader'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON `lyra-reader`.* TO 'lyra-reader'@'localhost';
FLUSH PRIVILEGES;
```

Make sure `DATABASE_HOST` in `.env` is set to `localhost` (not `db`, which is the Docker Compose service name).

**6. Run the application**

```bash
python run.py
```

Tables and default settings are created automatically on the first startup.

---

## First Login

The **first account to register** is automatically granted full admin privileges:

```
Admin, Team Member, Chapter Upload, Manga Manage, User Manage
```

The account is also immediately active and email-verified, so no SMTP configuration is needed just to get started.

---

## Updating

### Docker Compose

```bash
docker compose pull
docker compose up -d
```

### Manual

```bash
git pull
pip install -r backend/requirements.txt
# restart the process
```

Database migrations are currently handled by SQLAlchemy's `create_all` on startup (adds new tables / columns that don't exist yet). Existing data is not modified.

---

## Directory Layout

```
Lyra-Reader/
├── backend/
│   ├── app.py              # FastAPI application, all routes
│   ├── auth.py             # JWT + password helpers
│   ├── database.py         # SQLAlchemy models
│   ├── requirements.txt
│   └── middleware/
│       └── security.py     # SecurityHeadersMiddleware
├── frontend/
│   ├── locales/            # Babel translation files (de, en)
│   ├── static/             # CSS, images
│   └── templates/          # Jinja2 HTML templates
├── uploads/
│   ├── chapters/           # Extracted chapter images
│   ├── covers/             # Manga cover images
│   └── temp/               # Temporary ZIP uploads
├── run.py                  # Uvicorn entrypoint
├── Dockerfile
└── docker-compose.yml
```
