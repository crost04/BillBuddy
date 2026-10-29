# Deployment: BillBuddy on the internet (free)

BillBuddy runs on two free services:

| Part | Service | Why |
|------|---------|-----|
| App (FastAPI + web app) | [Render](https://render.com) – free web service | Builds and starts the app straight from GitHub, HTTPS included |
| Database (PostgreSQL) | [Neon](https://neon.com) – free plan | Keeps the data permanently; Render's free instances lose files on restart and its free database is deleted after 30 days |

```
Phone ──HTTPS──▶ Render (billbuddy-fr85.onrender.com) ──▶ Neon PostgreSQL
```

## Limits of the free plans
- **Sleep:** Render stops the app after about 15 minutes without requests. The next visit
  wakes it up, which takes roughly one minute. After that it is fast again.
  BillBuddy works around this (see *Keeping the server awake* below).
- **Storage:** Neon's free plan offers 1 GB per project – years of expenses.
- **Restore window:** Neon can only restore the database to a point within the last few hours,
  so this is no replacement for an export/backup.

Check the current limits on the providers' pricing pages; free plans change from time to time.

## One-time setup

### 1. Code on GitHub
Render deploys from a GitHub repository, so the code has to be pushed there first.

### 2. Create the database on Neon
1. Sign up at neon.com (e.g. with the GitHub account).
2. Create a project: name `billbuddy`, region **AWS Europe Central (Frankfurt)**.
3. On the project dashboard click **Connect** and copy the connection string.
   It looks like `postgresql://user:password@ep-....eu-central-1.aws.neon.tech/neondb?sslmode=require`.
   It contains the database password – never put it into the repository.

### 3. Create the app on Render
1. Sign up at render.com with the GitHub account.
2. **New → Blueprint**, choose the `BillBuddy` repository. Render reads `render.yaml`.
3. Render asks for `DATABASE_URL`: paste the Neon connection string.
4. Click **Apply**. The first build takes a few minutes.
5. The app is now online at `https://billbuddy-xxxx.onrender.com` (shown on the Render dashboard).

### 4. Use it on the phone
1. Open the Render URL on the phone and create an account.
2. Add it to the home screen: Safari → Share → *Add to Home Screen* (iPhone),
   or Chrome → ⋮ → *Add to Home screen* (Android).
3. Invite the others: *Gruppe → Link teilen*.

## Keeping the server awake
- **Keep-alive:** the GitHub Actions workflow `.github/workflows/keep-alive.yml` calls
  `/api/health` every 10 minutes, so Render does not put the app to sleep. One service running
  all month fits into Render's 750 free instance hours (a month has at most 744 hours).
  The health endpoint does not touch the database, so Neon can still sleep when nobody uses the app.
  GitHub sometimes starts scheduled runs late, so a short sleep can still happen.
  The workflow can also be started by hand: *GitHub → Actions → Keep server awake → Run workflow*.
- **Instant start:** the service worker serves the app files from the phone's cache right away
  and updates them in the background. If the server is still waking up, the app shows a hint and
  retries automatically.

## Updates
Every `git push` to the `main` branch makes Render build and deploy the new version.
Database migrations (`migrations/`) run automatically when the app starts, so the data is kept.
Because of the cache, a phone shows a new version from the next start of the app on.

## Configuration
| Variable | Meaning |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string (Neon). Without it the app uses a local SQLite file. |
| `BILLBUDDY_SECURE_COOKIES` | `true` on the server: the login cookie is only sent over HTTPS. |
| `PYTHON_VERSION` | Python version Render uses. |

## Security notes
- Passwords are stored as salted scrypt hashes, login sessions as SHA-256 hashes of random tokens.
- The login cookie is `HttpOnly`, `Secure` and `SameSite=Lax`.
- After 10 failed logins for one email address, logins are blocked for 15 minutes.
- Everyone can create an account, but only sees groups they created or joined via invitation link.
