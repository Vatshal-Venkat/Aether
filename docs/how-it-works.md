# How Aether Works — explained for everyone

*This document grows as Aether is built. Sections marked 🚧 are still being built.*

---

## 1. What is Aether?

Aether is a **chatbot for health data**. You type a question in normal English —
*"What medications am I taking?"* or *"Which patients have high blood sugar?"* — and
Aether finds the answer inside a hospital's computer records and replies in plain words.

The tricky part: a hospital doesn't keep everything in one place. Medical records sit in
one system, billing and insurance in another, and drug information in documents. Aether's
job is to know **where** each answer lives, **fetch** it safely, and **combine** it.

> **Think of Aether as a very fast, very careful hospital librarian.**
> You ask a question at the front desk. The librarian knows which room holds which
> records, walks to the right shelves, copies out only what you're allowed to see,
> double-checks the numbers, and hands you a short written answer — plus a note saying
> exactly which shelf each fact came from.

---

## 2. The data — and why it's fake

Real patient records are private and protected by law. So Aether uses **Synthea**, a free
tool that invents realistic but completely **fake patients**: their visits, illnesses,
lab results, medicines, doctors, insurers and bills. You may notice odd names like
**"Abe604 Bode78"** — the numbers are added on purpose so nobody mistakes them for real people.

Our sample has **111 fake patients** and about **180,000 records** spread over 18 tables
(a *table* is like a spreadsheet tab: rows of records, columns of details).

---

## 3. Where the data lives (two "databases")

A **database** is a program that stores tables and lets you ask questions of them very
quickly. Aether uses two different ones on purpose — just like a real hospital would:

| Room in our "library" | Database program | What's inside |
|---|---|---|
| **Medical records room** | PostgreSQL (`clinical_db`) | patients, visits, diagnoses, lab results, medicines, procedures, vaccines, allergies |
| **Billing office** | MySQL (`billing_db`) | doctors, hospitals, insurance companies, claims and payments |
| **Reference shelf** 🚧 | ChromaDB | official FDA drug-label text (side effects, warnings) |

Both are free, open-source programs running on this laptop.

---

## 4. How Aether is being built (progress log)

### Step 1 — The settings card ✅
**What we built:** a small settings file the app reads when it starts: database addresses,
the AI service to use, and safety limits (for example: *give up on a slow query after 10
seconds*, *try fixing a broken query at most 3 times*).

**Why it matters:** passwords and API keys (the "key" that lets us use the free AI service)
are kept in a private file called `.env` that is **never** shared or uploaded. The code
only ever asks the settings card — so no secret is written inside the program itself.

**Analogy:** the librarian keeps the master keys in a locked drawer, not taped to the doors.

### Step 2 — Sorting the boxes ✅
**What we built:** a sorter for Synthea's 18 spreadsheets. It decides which room each one
goes into (medical → PostgreSQL, money → MySQL), writes column names in lower case,
turns text like `2017-02-22T04:27:13Z` into real dates, and marks ID columns as fixed-size labels.

**Why it matters:** the AI writes far fewer mistakes when names are simple and consistent,
and real dates let us ask things like "visits in the last year".

### Step 3 — Building the rooms (setup script) ✅ *(waiting for database passwords to run)*
**What we built:** one command, `python -m scripts.setup_databases --reset`, that creates both
databases, copies every spreadsheet in, adds fast lookup lists (*indexes*) by patient, and
creates a special account called **`chatbot_ro`** ("read-only").

**Why it matters:** the chatbot logs in **only** as `chatbot_ro`, which can *look* but can
never change or delete anything. Even if the AI wrote a harmful command, the database
would refuse it. **Analogy:** the librarian gets a visitor's pass — reading room only.

### Step 4 — The privacy filter (row-level security) ✅ *(waiting for passwords to test)*
**What we built:** a rule inside PostgreSQL itself: *"a clinician may see every row; a patient
may only see rows that belong to them."* Before every question, Aether pins a small note
on the request — "this is a clinician" or "this is patient X" — and the database filters
rows on its own. The note disappears after each question, so nobody inherits someone else's view.
If no note is pinned at all, the database shows **nothing** — the safe default.

**Analogy:** every filing cabinet has a lock that only opens the drawers with your name on them.

### Step 5 — Phone lines and a health check ✅
**What we built:** permanent "phone lines" (*connections*) to both databases with a built-in
stopwatch — any search taking more than 10 seconds is cancelled — plus a web address,
`/health`, that answers "are both databases reachable?".

### Step 6 — The table of contents and the dictionary ✅
**What we built:**
- A **catalog**: when Aether starts, it asks each database what tables and columns it has,
  removes private columns (social security, driver's licence, passport numbers), and keeps
  the rest as a table of contents.
- A **glossary** (a "semantic layer"): a plain dictionary saying what things mean —
  *"HbA1c = the lab test called 'Hemoglobin A1c/Hemoglobin.total in Blood'"*,
  *"active medication = no stop date"*, *"money owed questions come from the billing database"*.

**Why it matters:** the AI is only shown the few relevant pages of the table of contents plus the
dictionary — never the private columns, never the whole database. Short, accurate context
means better SQL. And because everyone uses the same dictionary, "revenue" or "HbA1c"
always means the same thing.

### Step 7 — The safety inspector ✅
**What we built:** a checker that reads every AI-written query *before* it runs. It doesn't
just search for scary words — it takes the query apart into its pieces (like diagramming a
sentence in grammar class) and inspects each piece. A query is rejected if it:
- tries to **change** anything (insert, update, delete, drop…), or contains two commands at once;
- tries to **save** results somewhere else;
- calls a **dangerous function** — including one that could secretly change "who is asking";
- uses a table that **isn't on our list**;
- touches **private columns** — directly, through `SELECT *`, or through a sneaky trick that packs a
  whole person's record into one value (we found and blocked this one while testing!).

It also adds a **LIMIT** so nobody accidentally pulls a million rows.

**Analogy:** a security guard who reads every book request slip, word by word, before the
librarian is allowed to walk to the shelf.

### Step 8 — The AI connection ✅
**What we built:** one doorway to the AI service. By default it's **Groq** (free, very fast);
switching to Gemini or a local model is one line in the settings. If the free service says
"too many requests", Aether waits and tries again (up to 4 times), then switches to the backup
provider. It can also force the AI to reply in a strict, machine-readable format (JSON).
A live test call answered in about 3 seconds.

### Steps 9–12 — The pipeline (the librarian's routine) ✅
This is the heart of Aether. It is built with **LangGraph**, a free tool that runs a series of
small steps like a flowchart. See the next section for what each step does.

### Step 13 — The front desk (web API) ✅
**What we built:** three web addresses that any app (our future React website) can call:
- `POST /api/chat` — ask a question; say whether you're a doctor or which patient you are.
- `GET /api/patients` — the list of fake patients, for the "view as patient" picker (no private data).
- `GET /api/schema` — the table of contents, so a website can show what data exists.

FastAPI also gives a free interactive page at `http://localhost:8000/docs` to try them by hand.

---

## 5. What happens when you ask a question

```
 Your question
     │
 ① ROUTE ──── not about our data? ──► "I can only answer questions about health records…"
     │   └─── patient asking about others? ──► "I can only answer about your own records."
     ▼
 ② PICK TABLES ── shows the AI only the few relevant tables + dictionary entries
     ▼
 ③ WRITE SQL ── the AI writes a database query
     ▼
 ④ SAFETY CHECK ── rejected? ──┐
     ▼                         │  ⑥ RETRY: the AI sees its own mistake and the exact
 ⑤ RUN (privacy filter on) ─ error? ─┘     error message, and fixes it (max 3 tries)
     ▼
 ⑦ WRITE ANSWER ── using ONLY the rows that came back (none? → "No records found")
     ▼
 ⑧ CHECK NUMBERS ── every number must exist in the results; else one rewrite, else a ⚠ warning
     ▼
 Answer + the SQL used + sources + timings
```

| Step | What it does | Librarian analogy |
|---|---|---|
| ① Route | Decides: answerable from our data? allowed for this person? | The front-desk clerk deciding which room you need — or that the library can't help |
| ② Pick tables | Scores tables by matching words; adds dictionary hints (e.g. HbA1c) | Opening the catalog only at the relevant pages |
| ③ Write SQL | The AI writes the precise request | Filling in the book request slip |
| ④ Safety check | The inspector from Step 7 | The guard reading the slip |
| ⑤ Run | Runs it on the read-only account with the privacy filter | Fetching the books — only from drawers you may open |
| ⑥ Retry | On error, the AI gets its failed slip back with the reason | "That shelf doesn't exist — try again" |
| ⑦ Answer | The AI writes a short answer from the rows, naming sources | Writing the summary card, with shelf numbers |
| ⑧ Check numbers | Code compares every number to the results | A second librarian proofreading the card |

Every answer comes back with **the SQL that was run** (including failed attempts), **the
sources** (e.g. `clinical_db.medications`) and **how long each step took** — nothing is hidden.

*A real example traced through every step will be added after the first live run.* 🚧

## 6. Doctor view vs Patient view

There is no login (this is a practice project). Instead, each question says who is asking:

| | Doctor (clinician) | Patient |
|---|---|---|
| Can see | every patient's records | only their **own** records |
| Questions about other patients or totals across patients | ✅ allowed | ❌ politely refused |
| How it's enforced | — | ① the router refuses; ② the **database itself** hides other rows (row-level security) |

Private ID numbers (social security, driver's licence, passport) are hidden from **everyone** —
the AI never even learns those columns exist.

## 7. Why a cloud AI — and why that's only OK with fake data

Running an AI model on this laptop is free but slow (10–30 seconds per question). Groq's free
cloud service answers in about a second per step, and its larger models write better SQL.

The catch: questions and query results are **sent to the AI company**. That's fine here only
because every patient is fake. With real patient data you could **not** do this on a free tier —
US health-privacy law (HIPAA) requires a signed agreement with any company that handles patient
data, and free tiers may use what you send to improve their products. A real hospital would
use a paid service with that agreement, or run the AI on its own servers.

## 8. Glossary
- **Database** — a program that stores tables of records and answers questions about them fast.
- **Table** — like one spreadsheet tab: rows are records, columns are details.
- **API key** — a private password that lets our app use an outside service (here: the free AI).
- **`.env` file** — the private file where secrets are kept, never uploaded anywhere.
- **SQL** — the language used to ask a database for data ("give me the names of patients born after 1990").
- **Query** — one such request written in SQL.
- **LLM / AI model** — the program that understands English and writes SQL and answers.
- **Schema** — the list of tables and columns a database has (its table of contents).
- **Semantic layer / glossary** — a shared dictionary of what business and medical terms mean in the data.
- **Read-only account** — a database login that can look but never change anything.
- **Row-level security (RLS)** — a database rule that hides rows you're not allowed to see.
- **API** — a set of web addresses that programs use to talk to each other.
- **LangGraph** — a free tool for running a series of AI steps as a flowchart, with loops (like our retry).
- **Pipeline** — the chain of steps a question goes through.
- **PII** — "personally identifiable information": details that identify a real person (SSN, passport…).
