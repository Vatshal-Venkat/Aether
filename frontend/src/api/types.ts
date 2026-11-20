// The shapes of what the Aether backend sends and receives. They mirror the Python models in
// backend/app/graph/runner.py (ChatResult and friends) and backend/app/api/*.py, so TypeScript
// can warn us if the website and the backend disagree.

export type Role = "clinician" | "patient";
export type AnswerKind = "answer" | "clarification" | "refusal" | "out_of_scope" | "error";

export interface SqlRecord {
  db: "clinical" | "billing";
  query: string;
  error: string | null;
}

export interface QueryResult {
  columns: string[];
  rows: unknown[][];
  total_rows: number;
  truncated: boolean;
  result_id?: string | null; // ticket for fetching more pages of a big table
}

export interface ResultPage {
  columns: string[];
  rows: unknown[][];
  page: number;
  pages: number;
  total_rows: number;
}

export interface DocumentRef {
  label: string;
  source_url: string;
  excerpt: string;
}

export interface ChatResult {
  answer: string;
  kind: AnswerKind;
  sql: SqlRecord[];
  sources: string[];
  table: QueryResult | null;
  unverified_numbers: string[];
  documents: DocumentRef[];
  timings: Record<string, number>;
  route?: string | null;
  standalone_question?: string | null; // a follow-up rewritten as a full question
  options?: string[];
  /** Optional: the exact question each option sends ("" = send nothing; the person asks again). */
  option_questions?: Record<string, string>;
  /** Set when a backup AI model wrote the answer (the main one hit its daily limit). */
  model_notice?: string | null;                  // a clarifying question's one-click answers
  cached?: boolean;                    // answered instantly from the answer cache
  /** The SQL was reused from the first time this question was asked — same query, so the same numbers. */
  saved_query?: boolean;
}

export interface ChatRequest {
  message: string;
  role: Role;
  patient_id?: string;
  session_id: string;
}

export interface Patient {
  id: string;
  name: string;
  birthdate: string;
  gender: string;
}

/** One AI model's free daily allowance (GET /api/usage), in fallback order. */
export interface ModelUsage {
  model: string;
  name: string;                         // "gpt-oss-120b"
  role: "main" | "backup" | "last resort";
  status: "available" | "resting";      // resting = hit its daily limit
  back_in_s: number | null;
  daily_limit: number | null;           // null = the provider doesn't say
  used: number;                         // tokens in the last 24 hours
  remaining: number | null;
  exact: boolean;                       // the provider's own figure (else our count)
  complete: boolean;                    // our count covers the full 24 hours (else earlier use is missing)
  counting_since: number;               // when counting started (seconds since 1970)
}

export interface Health {
  status: "ok" | "degraded";
  clinical: string;
  billing: string;
  drug_labels: string;
  llm_provider: string;
}

/** One "a step is starting" event from POST /api/chat/stream. */
export type Step =
  | "contextualize" | "route" | "plan" | "inject_schema" | "generate_sql" | "validate" | "row_filter" | "execute"
  | "merge" | "retrieve" | "synthesize" | "verify_numbers";

export interface Progress {
  step: Step;
  db?: "clinical" | "billing";
  retry?: boolean;
}
