# Setting up Aether on Windows

Everything here is free. Do the steps in order; each says **why** it's needed.

## 1. Install PostgreSQL 18 — the "medical records room"
*Why:* stores patients, visits, diagnoses, lab results and medicines.

1. Go to https://www.postgresql.org/download/windows/ → **Download the installer** (EDB) → newest 18.x.
2. Components: **PostgreSQL Server**, **pgAdmin 4**, **Command Line Tools** (Stack Builder not needed).
3. Choose a password for the `postgres` admin user — write it down. Keep port **5432**.

## 2. Install MySQL (8.4 LTS, or 8.0 if already installed) — the "billing office"
*Why:* stores doctors, hospitals, insurers and claims.

1. Go to https://dev.mysql.com/downloads/mysql/ → version **8.4 LTS** → **Windows MSI Installer**.
2. Config type **Development Computer**, port **3306**, set a **root** password — write it down.
3. Keep "Configure as Windows Service". *Tip:* set the service's startup type to **Automatic**
   (Windows → Services) or start it by hand after each reboot. Never run two MySQL services
   on the same data folder at once.

## 3. Get a free AI key
*Why:* the AI writes SQL and the final answers.

- **Groq (default):** https://console.groq.com → API Keys → create.
- Optional **Gemini:** https://aistudio.google.com → Get API key.
- Optional offline **Ollama:** https://ollama.com/download, then `ollama pull qwen2.5-coder:7b`.

## 4. Python environment
*Why:* installs the libraries the backend uses, isolated from the rest of your computer.

```bash
cd backend
py -3.13 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 5. Fill in `backend/.env`
*Why:* passwords and keys live here — never in code, never committed to git.

Copy `backend/.env.example` to `backend/.env` and fill in:
`PG_ADMIN_PASSWORD`, `MYSQL_ADMIN_PASSWORD`, `GROQ_API_KEY`, and invent a new `RO_PASSWORD`
(the setup script creates the read-only `chatbot_ro` account with it).

## 6. Load the data
*Why:* creates both databases, loads the 111 fake patients, creates the read-only account,
and switches on the patient privacy filter.

```bash
python -m scripts.setup_databases --reset
```

If you already downloaded Synthea, unzip it into `backend/data/synthea/` and the script reuses it.

**Changed the PostgreSQL admin password or `RLS_SECRET` later?** Re-apply only the privacy rules
(fast, keeps all data): `python -m scripts.setup_databases --rls-only`. Otherwise patient-mode and
clinician-mode questions will return no rows, because the signature check no longer matches.

## 6b. Build the drug-label library (for drug questions)
*Why:* lets Aether answer "what are the side effects of metformin?" from official FDA labels.
Needs internet once (about 150 small requests to the free openFDA service, plus a one-time
~80 MB download of the small search model). Takes a few minutes; re-runs are quick.

```bash
python -m scripts.build_drug_index
```

Skip it and everything else still works — drug questions will just say the library isn't built.

## 7. Check everything
```bash
python -m pytest
```
Database tests say **skipped** (with the reason) if a database or password isn't set up yet.

## 8. Run the website
*Why:* the chat page you use in the browser. Needs **Node.js 20.19 or newer** (free, nodejs.org — the LTS installer).

Two terminals:

```bash
# terminal 1 — the backend (from backend/, venv active)
uvicorn app.main:app --port 8000

# terminal 2 — the website (from frontend/)
npm install        # first time only
npm run dev
```

Open **http://localhost:5173**. The small dot top-right breathes while the backend is running and goes
hollow if it isn't. Run the website's own tests with `npm test`.

## Optional: look at the data yourself
**DBeaver Community** (https://dbeaver.io) opens both databases side by side. pgAdmin
(installed with PostgreSQL) and MySQL Workbench also work.
