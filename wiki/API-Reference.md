# API Reference

All API endpoints are served by the FastAPI application. JSON is used for request/response bodies unless stated otherwise.

---

## Authentication

Most write endpoints and all admin endpoints require a valid JWT.

Tokens are set as an **httponly cookie** (`access_token`) on login and refreshed automatically. You can also pass the token in an `Authorization: Bearer <token>` header.

---

## Authentication Endpoints

### `POST /api/login`

Authenticates a user and sets the `access_token` cookie.

**Rate limit:** 10 requests / minute per IP.

**Request body (form data)**

| Field | Type | Description |
|---|---|---|
| `username` | string | Username or email address. |
| `password` | string | Account password. |

**Responses**

| Status | Description |
|---|---|
| `200` | Login successful. Sets `access_token` cookie. Returns `{"message": "Login successful"}`. |
| `401` | Invalid credentials or account not verified / inactive. |
| `429` | Rate limit exceeded. |

---

### `POST /api/logout`

Clears the `access_token` cookie.

**Auth required:** No.

**Responses:** `200` always.

---

### `POST /api/refresh-token`

Exchanges a valid (possibly near-expiry) token for a fresh one.

**Auth required:** Yes (cookie or header).

**Responses**

| Status | Description |
|---|---|
| `200` | New cookie set. |
| `401` | Token missing, invalid, or expired. |

---

### `POST /api/register`

Registers a new user account and sends a verification email.

**Request body (JSON)**

| Field | Type | Description |
|---|---|---|
| `username` | string | 3–50 characters, alphanumeric + underscores. |
| `email` | string | Valid email address. |
| `password` | string | Minimum 8 characters. |
| `recaptcha_token` | string | Required only when `RECAPTCHA_ENABLED=True`. |

**Responses**

| Status | Description |
|---|---|
| `200` | Account created; verification email sent. |
| `400` | Validation error, username/email taken, or registration disabled. |

---

### `GET /verify-email`

Verifies a user's email address via a token sent in the verification email.

**Query parameters:** `token` (string)

---

### `GET /verify-email-change`

Confirms an email address change via a token sent to the new address.

**Query parameters:** `token` (string)

---

## Profile Endpoints

### `GET /api/profile/stats/{userid}`

Returns reading statistics for a user.

**Auth required:** No (public profile stats).

**Response**

```json
{
  "chapters_read": 42,
  "manga_started": 7
}
```

---

### `POST /api/profile/preferences`

Updates the current user's theme and accent color.

**Auth required:** Yes.

**Request body (JSON)**

| Field | Type | Description |
|---|---|---|
| `theme` | string | `light`, `dark`, or `auto`. |
| `accent_color` | string | Hex color code (e.g. `#6366f1`). |

---

### `POST /api/profile/password`

Changes the current user's password.

**Auth required:** Yes.

**Request body (JSON)**

| Field | Type | Description |
|---|---|---|
| `current_password` | string | Existing password for verification. |
| `new_password` | string | New password (min. 8 characters). |

---

### `POST /api/profile/email`

Initiates an email address change. Sends a verification email to the new address.

**Auth required:** Yes.

**Request body (JSON)**

| Field | Type | Description |
|---|---|---|
| `new_email` | string | New email address. |
| `password` | string | Current password for verification. |

---

## Manga Endpoints

### `GET /api/manga/{manga_id}`

Returns full details for a single manga.

**Auth required:** No (subject to visibility rules).

---

### `POST /api/manga`

Creates a new manga entry.

**Auth required:** `Manga Manage` or `Admin`.

**Request:** multipart/form-data

| Field | Type | Description |
|---|---|---|
| `name` | string | Manga title. |
| `url_slug` | string | URL identifier. |
| `description` | string | Synopsis. |
| `tags` | JSON array string | Genre tags. |
| `status` | string | `Active`, `On Hold`, `Finished`, `Cancelled`, `Planned`, `Licensed`. |
| `hidden_status` | string | `All`, `Logged-In`, `Patreon`, `Licensed`. |
| `age_rating` | integer | Minimum age. |
| `reader_mode` | string | `single_page` or `long_stripe`. |
| `cover` | file | Cover image (optional). |

---

### `PUT /api/manga/{manga_id}`

Updates an existing manga.

**Auth required:** `Manga Manage` or `Admin`.

Same fields as `POST /api/manga`.

---

### `DELETE /api/manga/{manga_id}`

Deletes a manga and all its chapters and image files.

**Auth required:** `Manga Manage` or `Admin`.

---

### `GET /api/manga/{manga_id}/chapters`

Lists all chapters for a manga (public endpoint, release-date and visibility filtered).

**Response**

```json
[
  {
    "id": 1,
    "chapter_number": "1.00",
    "volume_number": 1,
    "name": "The Beginning",
    "release_date_regular": "2024-01-15T00:00:00",
    "release_date_patreon": "2024-01-08T00:00:00",
    "clicks": 2341,
    "downloads": 87
  }
]
```

---

## Chapter Endpoints

### `POST /api/chapter`

Uploads a new chapter.

**Auth required:** `Chapter Upload`, `Manga Manage`, or `Admin`.

**Request:** multipart/form-data

| Field | Type | Description |
|---|---|---|
| `manga_id` | integer | Parent manga ID. |
| `chapter_number` | decimal | e.g. `12` or `12.5`. |
| `volume_number` | integer | Volume grouping (0 if n/a). |
| `name` | string | Optional chapter title. |
| `release_date_regular` | datetime string | ISO 8601. |
| `release_date_patreon` | datetime string | ISO 8601. |
| `file` | file | ZIP archive containing page images. |

---

### `DELETE /api/chapter/{chapter_id}`

Deletes a chapter and its image directory.

**Auth required:** `Manga Manage` or `Admin`.

---

### `GET /api/download/{chapter_id}`

Serves the chapter as a downloadable ZIP archive. Increments the download counter.

**Auth required:** Subject to the manga's visibility rules.

---

## User Management Endpoints (Admin)

### `POST /api/users`

Creates a user account (admin bypass — no email verification required).

**Auth required:** `User Manage` or `Admin`.

**Request body (JSON)**

| Field | Type | Description |
|---|---|---|
| `username` | string | |
| `email` | string | |
| `password` | string | |
| `rights` | array | List of role strings. |

---

### `GET /api/users/{user_id}`

Returns a single user's data.

**Auth required:** `User Manage` or `Admin`.

---

### `PUT /api/users/{user_id}`

Updates a user (username, email, password, roles, active status).

**Auth required:** `User Manage` or `Admin`.

---

### `DELETE /api/users/{user_id}`

Permanently deletes a user.

**Auth required:** `Admin`.

---

## Partner Endpoints (Admin)

### `GET /api/partners`

Lists all partner links.

**Auth required:** `Admin`.

---

### `POST /api/partners`

Creates a partner link.

**Auth required:** `Admin`.

**Request body (JSON):** `name` (string), `url` (string).

---

### `DELETE /api/partners/{partner_id}`

Deletes a partner link.

**Auth required:** `Admin`.

---

## Settings Endpoints (Admin)

### `POST /api/settings`

Creates or updates a setting key-value pair.

**Auth required:** `Admin`.

**Request body (JSON):** `key` (string), `value` (string).

---

### `DELETE /api/settings/{setting_key}`

Deletes a setting entry.

**Auth required:** `Admin`.

---

## Misc Endpoints

### `GET /api/admin/stats`

Returns aggregate site statistics.

**Auth required:** `Admin`, `Manga Manage`, or `Chapter Upload`.

**Response**

```json
{
  "total_manga": 12,
  "total_chapters": 184,
  "total_users": 530,
  "total_views": 94210,
  "total_downloads": 3841
}
```

---

### `GET /api/latest_releases`

Returns the latest chapter releases. Intended for external widgets or bots.

**Auth required:** API token via `?token=` query parameter (compared with `hmac.compare_digest`).

**Query parameters**

| Parameter | Description |
|---|---|
| `token` | API token configured in Admin → Settings (`api_token`). |
| `release_type` | `regular` (default) or `patreon`. |

---

### `GET /api/test-email`

Sends a test email to the admin's address using the current SMTP settings.

**Auth required:** `Admin`.

---

### `GET /partner/{partner_id}`

Increments the click counter for a partner and redirects to their URL.

**Auth required:** No.
