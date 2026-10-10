export type Step = "upload" | "prefs" | "matches" | "tailored";

const STEPS: { id: Step; label: string }[] = [
  { id: "upload", label: "Upload CV" },
  { id: "prefs", label: "Preferences" },
  { id: "matches", label: "Matches" },
  { id: "tailored", label: "Tailor" },
];

export default function Header({ step, onHome }: { step: Step; onHome: () => void }) {
  const current = STEPS.findIndex((s) => s.id === step);
  return (
    <header className="topbar">
      <div className="topbar-inner">
        <button type="button" className="brand" onClick={onHome}>
          Joblyst
        </button>
        <ol className="stepper" aria-label="Progress">
          {STEPS.map((s, i) => {
            const state = i < current ? "done" : i === current ? "current" : "todo";
            return (
              <li key={s.id} className={`step step-${state}`} aria-current={state === "current" ? "step" : undefined}>
                <span className="step-dot" aria-hidden="true">{state === "done" ? "✓" : i + 1}</span>
                <span className="step-label">{s.label}</span>
                {state === "done" && <span className="sr-only"> (done)</span>}
              </li>
            );
          })}
        </ol>
        <span aria-hidden="true" />
      </div>
    </header>
  );
}
