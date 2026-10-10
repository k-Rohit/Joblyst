"use client";

import { useState } from "react";
import { uploadCv, type UploadResponse } from "@/utils/api";

const MAX_MB = 5;

export default function UploadStep({ onUploaded }: { onUploaded: (upload: UploadResponse) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function pick(f: File | undefined) {
    setError(null);
    if (!f) return;
    if (f.type !== "application/pdf") return setError(`${f.name} is not a PDF. Upload your CV as a PDF.`);
    if (f.size > MAX_MB * 1024 * 1024) return setError(`${f.name} is over ${MAX_MB} MB.`);
    setFile(f);
  }

  async function read() {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      onUploaded(await uploadCv(file));
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="container">
      <div className="row" style={{ gap: 48 }}>
        <section className="col-main" style={{ flex: "1 1 420px" }}>
          <h1 className="hero">Find jobs that fit your CV, then tailor it without making things up.</h1>
          <p className="lede">
            Upload your CV. Joblyst reads your experience, searches live job boards, scores every match, and rewrites
            your CV for the one you pick. Every claim it adds is checked against what your CV actually says.
          </p>
          <ul className="arrows">
            <li><span>→</span>Searches several job boards at once</li>
            <li><span>→</span>Fit score from 0 to 100 for each job, with the reasons</li>
            <li><span>→</span>Flags any tailored line your CV can&apos;t back up</li>
          </ul>
        </section>

        <section className="card" style={{ flex: "1 1 440px", minWidth: 0, padding: 32 }}>
          <label
            className={`drop${over ? " over" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setOver(true);
            }}
            onDragLeave={() => setOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setOver(false);
              pick(e.dataTransfer.files[0]);
            }}
          >
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ color: "var(--accent)" }}>
              <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
              <path d="M14 3v5h5" />
              <path d="M12 17v-6" />
              <path d="M9 14l3-3 3 3" />
            </svg>
            <span style={{ fontSize: 18, fontWeight: 500 }}>Drop your CV here, or choose a file</span>
            <span className="muted" style={{ fontSize: 14 }}>PDF only · up to {MAX_MB} MB</span>
            <input type="file" accept="application/pdf" aria-label="Choose your CV" disabled={busy} onChange={(e) => pick(e.target.files?.[0])} />
          </label>

          {file && (
            <div className="file-row">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true" style={{ color: "var(--muted)", flex: "none" }}>
                <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
                <path d="M14 3v5h5" />
              </svg>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 15, fontWeight: 500, overflowWrap: "anywhere" }}>{file.name}</div>
                <div className="mono muted" style={{ fontSize: 12 }}>
                  {busy ? "Reading your experience… this takes about 10–20 seconds" : `${(file.size / 1024).toFixed(0)} KB · ready`}
                </div>
              </div>
              {busy && <div className="bar" aria-hidden="true"><div /></div>}
            </div>
          )}

          {error && <p className="error" role="alert">{error}</p>}

          <button type="button" className="btn btn-primary" disabled={!file || busy} onClick={read}>
            {busy ? "Reading your CV…" : "Read my CV"}
          </button>
          <p className="small muted" style={{ margin: 0 }}>
            Your CV is stored only to run your search and tailoring, and is deleted when your session expires.
          </p>
        </section>
      </div>
    </div>
  );
}
