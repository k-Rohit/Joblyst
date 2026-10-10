"use client";

import { useEffect, useState } from "react";
import { tailor, tailorExternal, type RankedJob, type SearchResponse, type TailorResponse } from "@/utils/api";

// Same bar the backend uses (GOOD_FIT_THRESHOLD in graph.py).
const STRONG = 60;
const MIN_JOB_TEXT = 100;

export type SearchState = {
  status: "idle" | "running" | "done" | "error";
  progress: string[];
  result: SearchResponse | null;
  error: string | null;
  startedAt: number;
  finishedAt: number;
};

function useElapsed(search: SearchState): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (search.status !== "running") return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [search.status]);
  const end = search.status === "running" ? now : search.finishedAt;
  return Math.max(0, Math.round((end - search.startedAt) / 1000));
}

export default function MatchesStep({
  threadId,
  search,
  onEditSearch,
  onTailored,
}: {
  threadId: string;
  search: SearchState;
  onEditSearch: () => void;
  onTailored: (result: TailorResponse, job: RankedJob | null) => void;
}) {
  const elapsed = useElapsed(search);
  const [busyJob, setBusyJob] = useState<string | null>(null); // job_id, or "external"
  const [error, setError] = useState<string | null>(null);
  const [jobText, setJobText] = useState("");

  async function run(key: string, call: () => Promise<TailorResponse>, job: RankedJob | null) {
    setBusyJob(key);
    setError(null);
    try {
      onTailored(await call(), job);
    } catch (err) {
      setError((err as Error).message);
      setBusyJob(null);
    }
  }

  const jobs = search.result?.jobs ?? [];
  const running = search.status === "running";

  return (
    <div className="container">
      <div className="row">
        <aside className="col-side">
          <section className="log" aria-labelledby="log-h" aria-live="polite">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12 }}>
              <h2 id="log-h">Search progress</h2>
              <span className={`status${running ? " pulse" : ""}`}>
                {running ? "searching" : search.status === "error" ? "stopped" : "done"} · {elapsed} s
              </span>
            </div>
            <ol>
              {search.progress.map((m, i) => {
                const retry = m.startsWith("Not enough");
                return (
                  <li key={i}>
                    <span className={retry ? "retry" : "ok"} aria-hidden="true">{retry ? "↻" : "✓"}</span>
                    <span>{m}</span>
                  </li>
                );
              })}
              {running && (
                <li className="pulse">
                  <span className="ok" aria-hidden="true">…</span>
                  <span>{search.progress.length ? "Working on the next step" : "Writing a search for your profile"}</span>
                </li>
              )}
            </ol>
          </section>

          <section className="card" style={{ padding: 24, gap: 12 }} aria-labelledby="paste-h">
            <h2 id="paste-h" style={{ fontSize: 16 }}>Found a job somewhere else?</h2>
            <label htmlFor="job-desc" style={{ fontSize: 14, color: "var(--ink-2)" }}>
              Paste the full job description and we&apos;ll score and tailor for it.
            </label>
            <textarea
              id="job-desc"
              className="textarea"
              rows={5}
              placeholder="Paste at least a few lines of the job description…"
              value={jobText}
              onChange={(e) => setJobText(e.target.value)}
            />
            <span className="small muted mono">
              {jobText.trim().length < MIN_JOB_TEXT ? `${MIN_JOB_TEXT - jobText.trim().length} more characters needed` : "Ready"}
            </span>
            <button
              type="button"
              className="btn btn-outline btn-sm"
              disabled={jobText.trim().length < MIN_JOB_TEXT || busyJob !== null}
              onClick={() => run("external", () => tailorExternal(threadId, jobText.trim()), null)}
            >
              {busyJob === "external" ? "Scoring and tailoring… about a minute" : "Score and tailor this job"}
            </button>
          </section>
        </aside>

        <section className="col-main" aria-labelledby="matches-h">
          <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "baseline", gap: 12 }}>
            <h1 id="matches-h" style={{ fontSize: 28 }}>
              {running ? "Searching…" : search.status === "error" ? "The search stopped" : jobs.length ? `${jobs.length} jobs, best fit first` : "No jobs found"}
            </h1>
            <button type="button" className="link-btn" style={{ minHeight: 0 }} onClick={onEditSearch} disabled={running}>
              Change search
            </button>
          </div>

          {search.status === "error" && (
            <p className="error" role="alert">{search.error} You can change the search or run it again.</p>
          )}
          {running && (
            <p className="muted" style={{ margin: 0 }}>
              Your matches will appear here when the search finishes, usually within a minute. Each step shows on the left as it happens.
            </p>
          )}
          {error && <p className="error" role="alert">{error}</p>}
          {search.status === "done" && jobs.length === 0 && (
            <p className="muted" style={{ margin: 0 }}>Try another city, tick remote jobs, or set a different target role.</p>
          )}
          {jobs.length > 0 && (
            <p className="small muted mono" style={{ margin: 0 }}>
              {STRONG}+ is a strong match · from {search.result?.sources.join(", ")}
            </p>
          )}

          {jobs.map((r) => {
            const strong = r.fit_score >= STRONG;
            const busy = busyJob === r.job.job_id;
            return (
              <article key={r.job.job_id} className="job">
                <div className={`score${strong ? "" : " weak"}`}>
                  <b>{r.fit_score}</b>
                  <span>fit</span>
                </div>
                <div className="job-body">
                  <h2>{r.job.title}</h2>
                  <p className="job-meta">
                    {[r.job.company, r.job.location, r.job.remote ? "Remote" : null, `via ${r.job.source}`].filter(Boolean).join(" · ")}
                  </p>
                  <p className="job-why">{r.fit_explanation}</p>
                  {(r.matched_skills.length > 0 || r.gaps.length > 0) && (
                    <div className="tags">
                      {r.matched_skills.slice(0, 6).map((s) => <span key={`m-${s}`} className="tag-ok">{s}</span>)}
                      {r.gaps.slice(0, 4).map((g) => <span key={`g-${g}`} className="tag-gap">Missing: {g}</span>)}
                    </div>
                  )}
                  <div className="actions">
                    <button
                      type="button"
                      className={`btn btn-sm ${strong ? "btn-primary" : "btn-secondary"}`}
                      disabled={busyJob !== null}
                      onClick={() => run(r.job.job_id, () => tailor(threadId, r.job.job_id), r)}
                    >
                      {busy ? "Tailoring… about a minute" : strong ? "Tailor my CV" : "Tailor anyway"}
                    </button>
                    {r.job.url && (
                      <a href={r.job.url} target="_blank" rel="noreferrer" style={{ fontSize: 15 }}>
                        View posting
                      </a>
                    )}
                  </div>
                </div>
              </article>
            );
          })}
        </section>
      </div>
    </div>
  );
}
