# Admin Panel

The admin panel is available at `/admin` and is accessible to users with any of the following roles: `Admin`, `Manga Manage`, or `Chapter Upload`.

---

## Dashboard — `/admin`

Displays site-wide statistics pulled in real time:

- Total manga / chapters / users
- Total chapter views and downloads
- Recent chapter releases

---

## Manga Management — `/admin/manga`

**Required role:** `Admin`, `Manga Manage`, or `Chapter Upload`

### Creating a Manga

1. Click **New Manga**.
2. Fill in the fields:

| Field | Notes |
|---|---|
| **Name** | Display name for the manga. |
| **URL Slug** | URL-friendly identifier used in `/project/{slug}`. Must be unique. |
| **Description** | Shown on the manga's project page. |
| **Tags** | Comma-separated genre tags. |
| **Status** | `Active`, `On Hold`, `Finished`, `Cancelled`, `Planned`, or `Licensed`. |
| **Hidden Status** | Who can see the manga. See [Visibility Levels](User-Roles-and-Permissions#manga-visibility-levels). |
| **Age Rating** | Minimum age (integer). |
| **Reader Mode** | `single_page` or `long_stripe`. |
| **Cover Image** | Upload a `.jpg`, `.jpeg`, `.png`, `.webp`, or `.gif` file. |

3. Click **Save**.

### Editing / Deleting

Use the action buttons in the manga list table. Deleting a manga also removes all its associated chapters and image files.

---

## Chapter Management — `/admin/manga` → Chapter list

**Required role:** `Admin`, `Manga Manage`, or `Chapter Upload`

### Uploading a Chapter

1. Open the manga entry and click **Add Chapter**.
2. Fill in the fields:

| Field | Notes |
|---|---|
| **Chapter Number** | Decimal supported (e.g. `12.5` for a special chapter). |
| **Volume Number** | Integer; used for grouping. Set to `0` if not applicable. |
| **Chapter Name** | Optional display title. |
| **Regular Release Date** | When the chapter becomes available to regular users. |
| **Patreon Release Date** | When Patreon supporters can access the chapter early. Must be ≤ Regular Release Date. |
| **ZIP Archive** | ZIP containing the page images. Files are extracted and sorted naturally (001.jpg, 002.jpg, …). |

3. Click **Upload**.

> **ZIP requirements:** The archive must contain only image files (`.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`). Nested folders are flattened. Files are renamed sequentially after extraction.

### Deleting a Chapter

Deletes the database record and the extracted image directory from `uploads/chapters/{id}/`.

---

## User Management — `/admin/users`

**Required role:** `Admin` or `User Manage`

| Action | Notes |
|---|---|
| **View users** | Lists all registered accounts with roles, status, and registration date. |
| **Create user** | Creates an account directly (skips email verification). |
| **Edit user** | Change username, email, password, roles, and active status. |
| **Delete user** | Permanently removes the account and all associated data. |

---

## Partner Management

**Required role:** `Admin`

Partners are external links displayed on the site. Each link has a click counter.

| Field | Description |
|---|---|
| **Name** | Display name. |
| **URL** | Destination URL. Must pass `is_safe_url` validation (http / https only). |

Partner clicks are tracked anonymously — a redirect through `/partner/{id}` increments the counter before forwarding.

---

## Site Settings — `/admin/settings`

**Required role:** `Admin`

All settings are stored in the `settings` database table and editable here without restarting the server. See [Configuration → Database-Stored Settings](Configuration#database-stored-settings) for a full reference.

### SMTP / Email

Fill in the SMTP fields and click **Test Email** to send a test message to the admin's email address. This confirms connectivity and credentials before enabling email verification for users.

### reCAPTCHA

Enable reCAPTCHA and paste the site key and secret key from [Google reCAPTCHA Admin](https://www.google.com/recaptcha/admin). v2 Checkbox is supported.

---

## API / Swagger Docs

When `DEBUG_MODE=True` is set in `.env`, interactive API documentation is available at:

- **Swagger UI** — `/admin/docs`
- **ReDoc** — `/admin/redoc`

> **Never enable `DEBUG_MODE` in a publicly accessible production instance.**
