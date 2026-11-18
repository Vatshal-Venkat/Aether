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
  options?: string[];                  // a clarifying question's one-click answers
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
