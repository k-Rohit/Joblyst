// Types mirror the FastAPI response models in src/joblyst/api/schemas.py.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Profile = {
  name: string | null;
  seniority: "junior" | "mid" | "senior" | "lead" | "unknown";
  primary_roles: string[];
  skills: string[];
  projects: string[];
  years_experience: number | null;
  locations: string[];
  remote_ok: boolean;
  raw_summary: string;
};

export type JobPosting = {
  job_id: string;
  title: string;
  company: string;
  location: string;
  remote: boolean;
  description: string;
  url: string;
  tags: string[];
  source: string;
};

export type RankedJob = {
  job: JobPosting;
  fit_score: number;
  fit_explanation: string;
  matched_skills: string[];
  gaps: string[];
};

export type SearchResponse = {
  thread_id: string;
  jobs: RankedJob[];
  sources: string[];
  reformulation_count: number;
};

export type TailoredBullet = { text: string; corpus_ref: string };

export type CVContent = {
  headline: string;
  summary: string;
  experience: { role: string; company: string; dates: string; bullets: TailoredBullet[] }[];
  project: { project_domain: string; project_skills: string[]; project_bullets: TailoredBullet[] }[];
  skills: string[];
  education: string[];
};

export type FlaggedClaim = { where: string; text: string; reason: string; stage: string };

export type TailorResponse = {
  thread_id: string;
  pack: { cv: CVContent; cover_letter: string; honesty_note: string };
  fabrication_report: { flags: number; claims_checked: number; flagged: FlaggedClaim[] };
  // corpus_ref -> the original CV line the bullet was rewritten from
  sources: Record<string, string>;
};

export type UploadResponse = { thread_id: string; profile: Profile; experience: string[] };

// The API's error bodies are {"detail": "..."} for our own errors, and
// {"detail": [{msg, ...}]} for request validation (422).
async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail) && body.detail[0]?.msg) return body.detail[0].msg;
  } catch {
    // not JSON; fall through
  }
  return `Request failed (${res.status}). Please try again.`;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

export async function uploadCv(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_URL}/api/profile`, { method: "POST", body: form });
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

export function tailor(threadId: string, jobId: string): Promise<TailorResponse> {
  return postJson("/api/tailor", { thread_id: threadId, selected_job_id: jobId });
}

export function tailorExternal(threadId: string, jobDesc: string): Promise<TailorResponse> {
  return postJson("/api/external-job", { thread_id: threadId, job_desc: jobDesc });
}

export function pdfUrl(threadId: string): string {
  return `${API_URL}/api/tailor/${threadId}/pdf`;
}

export type SearchPrefs = { locations: string[]; remote_ok: boolean; target_role: string | null };

// The browser's EventSource only does GET, and the search is a POST, so read the
// stream with fetch and split it into events ourselves. Each event is a block of
// "event: <name>" and "data: <json>" lines, ended by a blank line.
export async function streamSearch(
  threadId: string,
  prefs: SearchPrefs,
  onProgress: (message: string) => void,
): Promise<SearchResponse> {
  const res = await fetch(`${API_URL}/api/search/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ thread_id: threadId, ...prefs }),
  });
  // A 404 (unknown thread) or 422 arrives as a normal JSON error before any stream.
  if (!res.ok || !res.body) throw new Error(await errorMessage(res));

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value.replace(/\r\n/g, "\n");
    let end;
    while ((end = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      let event = "message";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
        // lines starting with ":" are keep-alive comments; ignore them
      }
      if (!data) continue;
      const payload = JSON.parse(data);
      if (event === "progress") onProgress(payload.message);
      else if (event === "error") throw new Error(payload.detail);
      else if (event === "result") return payload as SearchResponse;
    }
  }
  throw new Error("The search ended without a result. Please try again.");
}
