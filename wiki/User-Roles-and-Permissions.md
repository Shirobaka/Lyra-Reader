# User Roles & Permissions

Lyra Reader uses a **multi-role system**. Roles are stored as a JSON array on each user record, so a single user can hold multiple roles simultaneously.

---

## Available Roles

| Role | Description |
|---|---|
| `Admin` | Full access to all admin pages and all admin API endpoints. |
| `Manga Manage` | Create, edit, and delete manga entries and chapters; access to the admin manga panel. |
| `Chapter Upload` | Upload new chapter ZIP archives via the admin panel. |
| `User Manage` | View and edit other user accounts. |
| `Team Member` | Displays a "Team" badge on the user's profile page. |
| `Patreon` | Access to chapters with an active Patreon early-release date and to manga with `hidden_status = Patreon`. |

> **Note:** Roles are checked at the route level. Holding `Admin` does **not** automatically imply `Manga Manage` — each right is checked independently, except where explicitly combined in the access logic.

---

## First-User Bootstrap

The very first account to register on a fresh installation is automatically granted:

```json
["Admin", "Team Member", "Chapter Upload", "Manga Manage", "User Manage"]
```

This account is also immediately active and email-verified, so SMTP does not need to be configured before the initial setup.

---

## Manga Visibility Levels

Each manga has a `hidden_status` that controls who can see it.

| `hidden_status` | Who can see the manga |
|---|---|
| `All` | Everyone, including unauthenticated guests. |
| `Logged-In` | Any authenticated user. |
| `Patreon` | Users with the `Patreon` role. |
| `Licensed` | Users with the `Manga Manage` role only. |

---

## Chapter Access Logic

Chapter visibility applies the manga's `hidden_status` **and** chapter release dates:

| Scenario | Access |
|---|---|
| Guest | Only chapters with `release_date_regular ≤ now` on `All` manga. |
| Logged-in user (no special roles) | Chapters with `release_date_regular ≤ now` on `All` + `Logged-In` manga. |
| `Patreon` user | Chapters released on either `release_date_regular` or `release_date_patreon`, on `All` + `Logged-In` + `Patreon` manga. |
| `Chapter Upload` / `Manga Manage` / `Admin` | All chapters regardless of release date or visibility. |

---

## Assigning Roles

Roles are assigned via **Admin → Users → Edit User**. Select any combination of roles from the checklist and save. Changes take effect immediately (the user's next request will use the updated JWT cookie once it expires and refreshes, or after logout/login).
