"use client";

import { useState } from "react";
import { pdfUrl, type CVContent, type FlaggedClaim, type RankedJob, type TailorResponse, type TailoredBullet } from "@/utils/api";

// FlaggedClaim.where looks like "cv_bullet:<corpus_ref>", "skill:<name>",
// "summary:sentence:1" or "cover_letter:sentence:3".
const SECTION: Record<string, string> = {
  cv_bullet: "CV line",
  skill: "Skill",
  summary: "Summary",
  headline: "Headline",
  cover_letter: "Cover letter",
};

function section(where: string): string {
  const key = where.split(":")[0];
  return SECTION[key] ?? key;
}

function cvAsText(cv: CVContent, name: string | null): string {
  const out: string[] = [];
  if (name) out.push(name);
  out.push(cv.headline, "", "SUMMARY", cv.summary);
  if (cv.experience.length) {
    out.push("", "EXPERIENCE");
    for (const e of cv.experience) {
      out.push(`${e.role}, ${e.company}${e.dates ? ` (${e.dates})` : ""}`);
      e.bullets.forEach((b) => out.push(`- ${b.text}`));
    }
  }
  if (cv.project.length) {
    out.push("", "PROJECTS");
    for (const p of cv.project) {
      out.push(p.project_domain);
      if (p.project_skills.length) out.push(p.project_skills.join(", "));
      p.project_bullets.forEach((b) => out.push(`- ${b.text}`));
    }
  }
  if (cv.skills.length) out.push("", "SKILLS", cv.skills.join(", "));
  if (cv.education.length) out.push("", "EDUCATION", ...cv.education);
  return out.join("\n");
}

function Bullets({
  bullets,
  flagFor,
  sources,
}: {
  bullets: TailoredBullet[];
  flagFor: (b: TailoredBullet) => FlaggedClaim | undefined;
  sources: Record<string, string>;
}) {
  return (
    <ul className="bullets">
      {bullets.map((b, i) => {
        const flag = flagFor(b);
        return (
          <li key={`${b.corpus_ref}-${i}`} className={flag ? "flagged" : undefined}>
            {b.text}
            {sources[b.corpus_ref] && sources[b.corpus_ref] !== b.text && (
              <span className="from-cv">
                <span className="mono">From your CV:</span> “{sources[b.corpus_ref]}”
              </span>
            )}
            {flag && (
              <span className="flag-reason">
                <strong>Flagged:</strong> {flag.reason} Edit or remove this line before you send it.
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export default function TailoredStep({
  threadId,
  name,
  result,
  job,
  onBack,
}: {
  threadId: string;
  name: string | null;
  result: TailorResponse;
  job: RankedJob | null;
  onBack: () => void;
}) {
  const [tab, setTab] = useState<"cv" | "letter">("cv");
  const [copied, setCopied] = useState(false);
  const { cv, cover_letter, honesty_note } = result.pack;
  const report = result.fabrication_report;

  const flagFor = (b: TailoredBullet) =>
    report.flagged.find((f) => f.where === `cv_bullet:${b.corpus_ref}` || f.text === b.text);
  const skillFlagged = (s: string) => report.flagged.some((f) => f.where === `skill:${s}`);
  const summaryFlags = report.flagged.filter((f) => f.where.startsWith("summary") || f.where.startsWith("headline"));
  const letterFlags = report.flagged.filter((f) => f.where.startsWith("cover_letter"));
  const bulletFlags = report.flagged.filter((f) => f.where.startsWith("cv_bullet"));
  const skillFlags = report.flagged.filter((f) => f.where.startsWith("skill"));
  // The report has one total, not per-section totals, so each row shows that section's flags.
  const sections = [
    { label: "Summary and headline", flagged: summaryFlags.length },
    { label: "Experience and project lines", flagged: bulletFlags.length },
    { label: "Skills", flagged: skillFlags.length },
    { label: "Cover letter", flagged: letterFlags.length },
  ];

  async function copy() {
    const text = tab === "cv" ? cvAsText(cv, name) : cover_letter;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard blocked (e.g. not https); nothing useful to do
    }
  }

  const title = job ? `${job.job.title} at ${job.job.company}` : "the job you pasted";

  return (
    <div className="container">
      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "flex-end", gap: 16 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 0 }}>
          <button type="button" className="link-btn" style={{ alignSelf: "flex-start", minHeight: 0, padding: 0, fontSize: 14 }} onClick={onBack}>
            ← Back to matches
          </button>
          <h1>Your CV for {title}</h1>
          {job && (
            <p className="muted" style={{ margin: 0, fontSize: 14 }}>
              Fit {job.fit_score} · {job.job.location}{job.job.remote ? " · Remote" : ""}
            </p>
          )}
        </div>
        <div className="actions">
          <button type="button" className="btn btn-secondary btn-sm" onClick={copy}>
            {copied ? "Copied" : tab === "cv" ? "Copy CV text" : "Copy cover letter"}
          </button>
          <a className="btn btn-primary btn-sm" href={pdfUrl(threadId)}>
            Download PDF
          </a>
        </div>
      </div>

      <div className="row" style={{ gap: 28 }}>
        <div className="col-main" style={{ gap: 24 }}>
          <div role="tablist" aria-label="Tailored documents" className="tabs">
            <button type="button" role="tab" className="tab" aria-selected={tab === "cv"} onClick={() => setTab("cv")}>
              Tailored CV
            </button>
            <button type="button" role="tab" className="tab" aria-selected={tab === "letter"} onClick={() => setTab("letter")}>
              Cover letter{letterFlags.length ? ` (${letterFlags.length} flagged)` : ""}
            </button>
          </div>

          {tab === "cv" ? (
            <>
              <section className="card" aria-labelledby="summary-h" style={{ gap: 12 }}>
                <h2 id="summary-h" className="label">Summary</h2>
                <p style={{ margin: 0, fontWeight: 600 }}>{cv.headline}</p>
                <p className="prose">{cv.summary}</p>
                {summaryFlags.map((f, i) => (
                  <p key={i} className="flagged small" style={{ margin: 0, color: "var(--warn-ink)" }}>
                    <strong>Flagged:</strong> “{f.text}” — {f.reason}
                  </p>
                ))}
              </section>

              {cv.experience.length > 0 && (
                <section className="card" aria-labelledby="exp-h" style={{ gap: 18 }}>
                  <h2 id="exp-h" className="label">Experience</h2>
                  {cv.experience.map((e, i) => (
                    <div key={i} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                      <p className="role-line">
                        {e.role}, {e.company}
                        {e.dates && <span className="muted mono" style={{ fontWeight: 400, fontSize: 13 }}> · {e.dates}</span>}
                      </p>
                      <Bullets bullets={e.bullets} flagFor={flagFor} sources={result.sources ?? {}} />
                    </div>
                  ))}
                </section>
              )}

              {cv.project.length > 0 && (
                <section className="card" aria-labelledby="proj-h" style={{ gap: 18 }}>
                  <h2 id="proj-h" className="label">Projects</h2>
                  {cv.project.map((p, i) => (
                    <div key={i} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                      <p className="role-line">{p.project_domain}</p>
                      {p.project_skills.length > 0 && <p className="small muted" style={{ margin: 0 }}>{p.project_skills.join(" · ")}</p>}
                      <Bullets bullets={p.project_bullets} flagFor={flagFor} sources={result.sources ?? {}} />
                    </div>
                  ))}
                </section>
              )}

              {cv.skills.length > 0 && (
                <section className="card" aria-labelledby="skills-h" style={{ gap: 12 }}>
                  <h2 id="skills-h" className="label">Skills, in the order this job cares about</h2>
                  <ul className="pills">
                    {cv.skills.map((s) => (
                      <li key={s} className={skillFlagged(s) ? "skill-flag" : undefined} title={skillFlagged(s) ? "Not found in your CV" : undefined}>
                        {s}{skillFlagged(s) ? " · not in your CV" : ""}
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {cv.education.length > 0 && (
                <section className="card" aria-labelledby="edu-h" style={{ gap: 12 }}>
                  <h2 id="edu-h" className="label">Education</h2>
                  <ul className="list-lines">
                    {cv.education.map((e) => <li key={e}>{e}</li>)}
                  </ul>
                </section>
              )}
            </>
          ) : (
            <section className="card" aria-label="Cover letter">
              <p className="prose">{cover_letter}</p>
              {letterFlags.map((f, i) => (
                <p key={i} className="flagged small" style={{ margin: 0, color: "var(--warn-ink)" }}>
                  <strong>Flagged:</strong> “{f.text}” — {f.reason}
                </p>
              ))}
            </section>
          )}
        </div>

        <aside className="card col-side" style={{ padding: 24, gap: 16 }} aria-labelledby="check-h">
          <h2 id="check-h" style={{ fontSize: 17 }}>Fabrication check</h2>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
            <span className="big-num">{report.flags}</span>
            <span style={{ fontSize: 15, color: "var(--ink-2)" }}>of {report.claims_checked} claims flagged</span>
          </div>
          <p className="small" style={{ margin: 0, color: "var(--ink-2)", fontSize: 14 }}>
            Every rewritten line was compared with your original CV. Skills are matched exactly; sentences are reviewed by a second model.
          </p>
          <ul className="flag-list" aria-label="Flags by section">
            {sections.map((s) => (
              <li key={s.label} style={{ flexDirection: "row", justifyContent: "space-between", gap: 12 }}>
                <span>{s.label}</span>
                <span className="mono" style={{ color: s.flagged ? "var(--warn-ink)" : "var(--accent)" }}>
                  {s.flagged ? `${s.flagged} flagged` : "ok"}
                </span>
              </li>
            ))}
          </ul>
          {report.flagged.length > 0 && (
            <ul className="flag-list">
              {report.flagged.map((f, i) => (
                <li key={i}>
                  <span className="label">{section(f.where)}</span>
                  <span>“{f.text}”</span>
                  <span className="muted small">{f.reason}</span>
                </li>
              ))}
            </ul>
          )}
          {honesty_note && (
            <div className="note">
              <strong>Gaps to be upfront about:</strong> {honesty_note}
            </div>
          )}
          <p className="small muted" style={{ margin: 0 }}>The check can miss things or flag fair rewordings. Read the CV before you send it.</p>
        </aside>
      </div>
    </div>
  );
}
