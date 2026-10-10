"use client";

import { useState } from "react";
import type { Profile, SearchPrefs } from "@/utils/api";

const LEVELS: Record<Profile["seniority"], string> = {
  junior: "Junior",
  mid: "Mid",
  senior: "Senior",
  lead: "Lead",
  unknown: "Not clear",
};

// Splits "Data Engineer, Philips, Chennai Nov'25 - Present" into the role part
// and the dates, so the dates can sit on the right like in the design.
const DATES = /\(?\s*((?:[A-Za-z]{3,9}\.?\s*)?(?:(?:19|20)\d{2}|['’]\d{2})\s*[-–—]+\s*(?:(?:[A-Za-z]{3,9}\.?\s*)?(?:(?:19|20)\d{2}|['’]\d{2})|present|current|now))\s*\)?\s*$/i;

function splitRole(line: string): { role: string; dates: string } {
  const m = line.match(DATES);
  return m ? { role: line.slice(0, m.index).replace(/[,\s]+$/, ""), dates: m[1] } : { role: line, dates: "" };
}

export default function PreferencesStep({
  profile,
  experience,
  initial,
  onSearch,
  onBack,
}: {
  profile: Profile;
  experience: string[];
  initial: SearchPrefs;
  onSearch: (prefs: SearchPrefs) => void;
  onBack: () => void;
}) {
  const [locations, setLocations] = useState<string[]>(initial.locations);
  const [draft, setDraft] = useState("");
  const [remote, setRemote] = useState(initial.remote_ok);
  const [role, setRole] = useState(initial.target_role ?? "");
  const [error, setError] = useState<string | null>(null);

  function addLocation(text: string): string[] {
    const city = text.trim().replace(/,$/, "").trim();
    if (!city || locations.some((l) => l.toLowerCase() === city.toLowerCase())) return locations;
    const next = [...locations, city];
    setLocations(next);
    return next;
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    // A city typed but not yet turned into a chip still counts.
    const all = addLocation(draft);
    setDraft("");
    if (all.length === 0 && !remote) {
      setError("Add at least one city, or tick “Include remote jobs”.");
      return;
    }
    onSearch({ locations: all, remote_ok: remote, target_role: role.trim() || null });
  }

  const years = profile.years_experience;

  return (
    <div className="container">
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <h1>Check what we read, then tell us where to look</h1>
      </div>

      <div className="row">
        <section className="card col-main" aria-labelledby="profile-h">
          <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "baseline", gap: 12 }}>
            <h2 id="profile-h">From your CV{profile.name ? `, ${profile.name}` : ""}</h2>
            <button type="button" className="link-btn" style={{ minHeight: 0 }} onClick={onBack}>
              Upload a different CV
            </button>
          </div>

          <dl className="stats">
            <div>
              <dt className="label">Main role</dt>
              <dd>{profile.primary_roles[0] ?? "Not found"}</dd>
            </div>
            <div>
              <dt className="label">Level</dt>
              <dd>{LEVELS[profile.seniority]}</dd>
            </div>
            <div>
              <dt className="label">Paid experience</dt>
              <dd>{years == null ? "Not clear" : `${years} year${years === 1 ? "" : "s"}`}</dd>
            </div>
          </dl>

          {profile.primary_roles.length > 1 && (
            <div className="field">
              <h3 className="label">Other roles that fit</h3>
              <ul className="pills">
                {profile.primary_roles.slice(1).map((r) => <li key={r}>{r}</li>)}
              </ul>
            </div>
          )}

          {profile.skills.length > 0 && (
            <div className="field">
              <h3 className="label">Skills</h3>
              <ul className="pills">
                {profile.skills.map((s) => <li key={s}>{s}</li>)}
              </ul>
            </div>
          )}

          {experience.length > 0 && (
            <div className="field">
              <h3 className="label">Experience</h3>
              <ol className="list-lines">
                {experience.map((line) => {
                  const { role, dates } = splitRole(line);
                  return (
                    <li key={line} style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: 8 }}>
                      <span style={{ fontWeight: 500 }}>{role}</span>
                      {dates && <span className="mono muted" style={{ fontSize: 13 }}>{dates}</span>}
                    </li>
                  );
                })}
              </ol>
            </div>
          )}

          {profile.projects.length > 0 && (
            <div className="field">
              <h3 className="label">Projects</h3>
              <ul className="list-lines">
                {profile.projects.map((p) => <li key={p}>{p}</li>)}
              </ul>
            </div>
          )}

          {profile.raw_summary && (
            <div className="field">
              <h3 className="label">Summary</h3>
              <p className="prose" style={{ fontSize: 15, color: "var(--ink-2)" }}>{profile.raw_summary}</p>
            </div>
          )}
        </section>

        <form className="card col-side" style={{ flex: "1 1 340px" }} onSubmit={submit} aria-labelledby="prefs-h">
          <h2 id="prefs-h">Where should we search?</h2>

          <div className="field">
            <label htmlFor="locations">Locations</label>
            <div className="chips-input">
              {locations.map((city) => (
                <span key={city} className="chip">
                  {city}
                  <button type="button" aria-label={`Remove ${city}`} onClick={() => setLocations(locations.filter((l) => l !== city))}>
                    ×
                  </button>
                </span>
              ))}
              <input
                id="locations"
                type="text"
                placeholder={locations.length ? "Add another city" : "e.g. Bengaluru, then Enter"}
                value={draft}
                onChange={(e) => {
                  setError(null);
                  if (e.target.value.endsWith(",")) {
                    addLocation(e.target.value);
                    setDraft("");
                  } else setDraft(e.target.value);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && draft.trim()) {
                    e.preventDefault();
                    addLocation(draft);
                    setDraft("");
                  } else if (e.key === "Backspace" && !draft && locations.length) {
                    setLocations(locations.slice(0, -1));
                  }
                }}
              />
            </div>
          </div>

          <label className="check" htmlFor="remote">
            <input id="remote" type="checkbox" checked={remote} onChange={(e) => { setRemote(e.target.checked); setError(null); }} />
            Include remote jobs
          </label>

          <div className="field">
            <label htmlFor="target-role">
              Target role <span className="muted" style={{ fontWeight: 400 }}>(optional)</span>
            </label>
            <input id="target-role" className="input" type="text" placeholder="e.g. AI Engineer" value={role} onChange={(e) => setRole(e.target.value)} />
            <p className="small muted" style={{ margin: 0 }}>Leave empty to search for your main role. Fill it to look for a different one.</p>
          </div>

          {error && <p className="error" role="alert">{error}</p>}

          <button type="submit" className="btn btn-primary">Find matching jobs</button>
          <p className="small muted" style={{ margin: 0 }}>A search takes about a minute. You&apos;ll see each step as it happens.</p>
        </form>
      </div>
    </div>
  );
}
