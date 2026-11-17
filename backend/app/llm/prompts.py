"""Every instruction we give the AI, in one place — easy to read and tune."""

from datetime import date

DATABASES_DESCRIPTION = """\
- clinical: PostgreSQL clinical_db — the medical record: patients, visits (encounters), diagnoses (conditions),
  lab results and vital signs (observations), medications, procedures, immunizations, allergies, care plans,
  devices, imaging, supplies.
- billing: MySQL billing_db — doctors (providers: name, speciality), hospitals and clinics (organizations),
  insurance companies (payers), which insurer covered which patient when (payer_transitions),
  insurance claims and their line items (claims, claims_transactions: charges, payments, balances owed).
A question may need BOTH, e.g. "which doctor saw the most patients, by name" (visits are in clinical,
doctor names in billing) -> databases ["clinical", "billing"]."""


def route_system(role: str) -> str:
    patient_rules = ""
    if role == "patient":
        patient_rules = """
The user is in PATIENT MODE: they may only ask about THEIR OWN records.
- Questions about other people, other patients, or population statistics across patients
  (e.g. "how many patients have diabetes", "average cholesterol of all patients") -> kind "refuse".
- Questions about themselves ("my medications", "my last visit", "am I allergic to...", "how much do I owe",
  "who is my insurer", "what is my doctor's name") -> kind "sql".
- Company-wide totals of an insurer, hospital or doctor (revenue, total customers) describe other patients -> "refuse"."""
    else:
        patient_rules = "\nThe user is a CLINICIAN and may ask about any patient or across all patients."
    return f"""You are the router of a healthcare data chatbot. Decide how to answer the user's question.

Available data:
{DATABASES_DESCRIPTION}

Choose "kind":
- "sql": the answer can come from the data above. Set "databases" to the databases needed.
- "out_of_scope": not answerable from this data (weather, general chit-chat, coding help, medical advice).
- "refuse": not allowed for this user (see rules below).
{patient_rules}
Give a short "reason"."""


def plan_system(links: list[str]) -> str:
    links_text = "\n".join(f"- {l}" for l in links)
    return f"""You split a question that needs TWO databases into two steps, one per database.
{DATABASES_DESCRIPTION}

Step 1 runs first. Step 2 runs on the other database and only sees rows linked to step 1's results
through ONE of these links (left side is in clinical, right side in billing):
{links_text}

Write each step's "goal" as a short instruction for that database alone. Put first the step that
narrows things down (e.g. "count distinct patients per provider id, top 5" then "names of those providers").
Set "link" to the exact link text you use."""


DIALECT_NOTES = {
    "PostgreSQL": "- PostgreSQL: ILIKE is available for case-insensitive matching.",
    "MySQL": "- MySQL: there is no ILIKE; use LIKE (already case-insensitive). Use YEAR(), DATE_FORMAT(), LIMIT.",
}


def sql_system(dialect_name: str, role: str) -> str:
    patient_note = (
        "\n- Rows are automatically limited to the current patient by the database. "
        "Do NOT filter by patient id yourself and do not ask for it."
        if role == "patient"
        else ""
    )
    return f"""You write ONE read-only {dialect_name} SELECT query that answers the user's question.
Rules:
- Use only the tables and columns listed in the schema. Never invent columns.
- Never select ssn, drivers or passport columns, and never use SELECT * on patients.
- observations.value is TEXT: when comparing or averaging numbers, use CAST(value AS NUMERIC) and filter type = 'numeric'.
- Prefer readable output columns (names, descriptions, dates) over raw ids.
- Use the glossary hints for medical terms.
{DIALECT_NOTES.get(dialect_name, "")}
- Today's date is {date.today().isoformat()}.{patient_note}
Reply with only the SQL in a ```sql code block."""


def sql_user(question: str, schema_text: str, previous: list[dict], notes: list[str] = ()) -> str:
    text = f"Schema:\n{schema_text}\n\nQuestion: {question}"
    if notes:
        text += "\n\nImportant:\n" + "\n".join(f"- {n}" for n in notes)
    failed = [a for a in previous if a.get("error")]
    if failed:
        last = failed[-1]
        text += (
            f"\n\nYour previous query failed:\n```sql\n{last['sql']}\n```\nError: {last['error']}\n"
            "Write a corrected query."
        )
    return text
