# Deploying Aether for free

| Part | Where | Free tier notes |
|---|---|---|
| Website (React) | **Vercel** | Static site. |
| Backend (FastAPI) | **Render** web service | 512 MB RAM, so the reranker is off. Sleeps after 15 min idle; the first question after that takes about 1 minute. Disk is wiped on restart. |
| PostgreSQL `clinical_db` | **Neon** | Pauses when idle (wakes in about 1 s). |
| MySQL `billing_db` | **Aiven for MySQL** (free plan), or **TiDB Cloud Serverless** | Aiven is real MySQL 8. TiDB is MySQL-compatible. |

Check each provider's current free limits when you sign up. Aether's data is small: about 55 MB of CSVs.

Because the Render disk is wiped on restart, chat history, saved queries, the usage ledger and the audit log
(SQLite files) start fresh after each restart or deploy. That's fine for a demo.

## 1. Create the databases

**Neon (PostgreSQL)**
1. Create a project. In **Connection details**, turn **off** "Connection pooling". Aether sets a query time
   limit when it connects, and the pooled ("-pooler") host doesn't allow that.
2. Note the host, user and password.

**Aiven (MySQL)**
1. Create a free MySQL service. Note the host, port, user (`avnadmin`) and password, and download the
   **CA certificate** (`ca.pem`).
2. No special settings needed — the setup script handles `sql_require_primary_key` automatically.

(TiDB Cloud instead: create a Serverless cluster, note host, port 4000, user and password. Its certificate is
the normal system one, so no file needs downloading.)

## 2. Load the data (once, from your computer)

Temporarily point `backend/.env` at the cloud databases. Keep a copy of your local `.env`.

```
PG_HOST=<neon host>          PG_ADMIN_USER=<neon user>     PG_ADMIN_PASSWORD=<neon password>
PG_SSLMODE=require
MYSQL_HOST=<aiven host>      MYSQL_PORT=<aiven port>       MYSQL_ADMIN_USER=avnadmin
MYSQL_ADMIN_PASSWORD=<aiven password>
MYSQL_SSL_CA=C:\path\to\ca.pem
MYSQL_RO_HOST=%
RO_PASSWORD=<a new strong password>
RLS_SECRET=<a long random string — write it down, Render needs the same one>
```

Then, from `backend/` (in the activated venv):

```
python -m scripts.setup_databases
```

This creates `clinical_db` and `billing_db`, loads the Synthea data, creates the read-only `chatbot_ro` account in
both, and sets up row-level security on Postgres. It takes a few minutes over the internet.

Check it worked: `python -m scripts.ask "How many patients are there?"` should answer from the cloud databases.

Then restore your local `.env`.

## 3. Backend on Render

1. Push the repo to GitHub.
2. Render → **New → Blueprint** → choose the repo. It reads `render.yaml` and asks for each secret:
   the same database values as step 2, `RO_PASSWORD`, `RLS_SECRET`, `GROQ_API_KEY`, `GEMINI_API_KEY`, and
   `CORS_ORIGINS` (leave this empty for now and fill it in after step 4).
3. Aiven only: Render → the service → **Environment → Secret Files** → add `aiven-ca.pem` with the contents of
   `ca.pem`, and set `MYSQL_SSL_CA=/etc/secrets/aiven-ca.pem`.
   (TiDB: `MYSQL_SSL_CA=/etc/ssl/certs/ca-certificates.crt`.)
4. Deploy. The build also builds the drug-label library from openFDA, which takes about 3–5 minutes.
5. Open `https://<your-service>.onrender.com/health`. It should show both databases as reachable.

## 4. Website on Vercel

1. Vercel → **Add New → Project** → the same repo. Set **Root Directory** to `frontend`. Vercel detects Vite
   (build `npm run build`, output `dist`).
2. Add the environment variable `VITE_API_URL=https://<your-service>.onrender.com`.
3. Deploy, then copy the website's address (e.g. `https://aether.vercel.app`).
4. Back on Render, set `CORS_ORIGINS` to that address (comma-separate several, e.g. preview URLs) and redeploy.

## Things to know

- **No login.** Anyone with the link can ask questions, use up the free Groq allowance (about 200,000 tokens a
  day), and view any synthetic patient. The data is synthetic, so this is fine for a demo.
- `/metrics` (Prometheus counters) is public too. It shows counts and timings only, never questions or answers.
- If the website says "Can't reach the Aether backend. It may be waking up", Render was asleep: wait a minute and ask again.
