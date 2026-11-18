// What the backend is doing -> how the orbs move, and what the caption says.
//
// Plain English: each step of the pipeline has its own "mood" (rhythm):
//   calm    recalling / understanding      wide, unhurried drift; slow breathing
//   write   reading tables / writing SQL   droplets swirl fast and close, like busy hands
//   retry   fixing a failed query          an urgent, slightly jittery swirl
//   check   safety check / privacy filter  everything pulls into one drop, held still and tight
//   query   asking the database            a heartbeat: the core beats, the droplets ride the pulse
//   read    reading FDA labels             the droplets spread wide and drift slowly, "browsing"
//   flow    writing the answer             smooth, steady flowing
//   verify  checking numbers               small, quick ticks — one number after another
//   idle    the welcome screen             the slowest, laziest drift

import type { Progress } from "../../api/types";

export type Mood = "idle" | "calm" | "write" | "retry" | "check" | "query" | "read" | "flow" | "verify";

export interface MoodShape {
  speed: number;   // how fast time runs for the droplets (1 = normal)
  spread: number;  // how far droplets swing from the centre (1 = normal)
  pulse: "breathe" | "heartbeat" | "tick" | "hold";
  beat: number;    // seconds per pulse of the core
  core: number;    // core size (radius in drawing units)
  spin: number;    // degrees per second the whole cluster turns
  jitter: number;  // tiny random tremble (0 = none)
}

export const MOODS: Record<Mood, MoodShape> = {
  idle:   { speed: 0.45, spread: 1.0,  pulse: "breathe",   beat: 5.0,  core: 31, spin: 9,  jitter: 0 },
  calm:   { speed: 0.8,  spread: 1.05, pulse: "breathe",   beat: 3.2,  core: 31, spin: 14, jitter: 0 },
  write:  { speed: 2.1,  spread: 0.62, pulse: "breathe",   beat: 1.4,  core: 30, spin: 48, jitter: 0 },
  retry:  { speed: 2.8,  spread: 0.75, pulse: "breathe",   beat: 0.9,  core: 29, spin: 70, jitter: 2.2 },
  check:  { speed: 0.6,  spread: 0.22, pulse: "hold",      beat: 1.0,  core: 36, spin: 6,  jitter: 0 },
  query:  { speed: 1.1,  spread: 0.9,  pulse: "heartbeat", beat: 1.05, core: 30, spin: 20, jitter: 0 },
  read:   { speed: 0.55, spread: 1.4,  pulse: "breathe",   beat: 3.8,  core: 27, spin: 8,  jitter: 0 },
  flow:   { speed: 1.25, spread: 1.0,  pulse: "breathe",   beat: 2.2,  core: 32, spin: 22, jitter: 0 },
  verify: { speed: 0.9,  spread: 0.5,  pulse: "tick",      beat: 0.42, core: 31, spin: 12, jitter: 0 },
};

export function moodFor(progress: Progress | null): Mood {
  if (!progress) return "calm";
  switch (progress.step) {
    case "contextualize":
    case "route":
    case "plan":
      return "calm";
    case "inject_schema":
      return "write";
    case "generate_sql":
      return progress.retry ? "retry" : "write";
    case "validate":
    case "row_filter":
      return "check";
    case "execute":
    case "merge":
      return "query";
    case "retrieve":
      return "read";
    case "synthesize":
      return "flow";
    case "verify_numbers":
      return "verify";
  }
}

const DB_LABEL = { clinical: "clinical_db", billing: "billing_db" } as const;

export function phaseLabel(progress: Progress | null): string {
  if (!progress) return "Starting";
  switch (progress.step) {
    case "contextualize":
      return "Recalling the conversation";
    case "route":
      return "Understanding the question";
    case "plan":
      return "Planning across both databases";
    case "inject_schema":
      return "Reading the table map";
    case "generate_sql":
      return progress.retry ? "Fixing the SQL" : "Writing SQL";
    case "validate":
      return "Checking safety";
    case "row_filter":
      return "Applying the privacy filter";
    case "execute":
      return progress.db ? `Querying ${DB_LABEL[progress.db]}` : "Querying the database";
    case "merge":
      return "Combining the results";
    case "retrieve":
      return "Reading FDA labels";
    case "synthesize":
      return "Writing the answer";
    case "verify_numbers":
      return "Checking numbers";
  }
}
