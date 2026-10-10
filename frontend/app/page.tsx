"use client";

import { useState } from "react";
import Header, { type Step } from "@/components/Header";
import UploadStep from "@/components/UploadStep";
import PreferencesStep from "@/components/PreferencesStep";
import MatchesStep, { type SearchState } from "@/components/MatchesStep";
import TailoredStep from "@/components/TailoredStep";
import { streamSearch, type Profile, type RankedJob, type SearchPrefs, type TailorResponse } from "@/utils/api";

const EMPTY_SEARCH: SearchState = { status: "idle", progress: [], result: null, error: null, startedAt: 0, finishedAt: 0 };

export default function Home() {
  const [step, setStep] = useState<Step>("upload");
  const [threadId, setThreadId] = useState<string | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [experience, setExperience] = useState<string[]>([]);
  const [prefs, setPrefs] = useState<SearchPrefs>({ locations: [], remote_ok: true, target_role: null });
  const [search, setSearch] = useState<SearchState>(EMPTY_SEARCH);
  const [tailored, setTailored] = useState<{ result: TailorResponse; job: RankedJob | null } | null>(null);

  function startOver() {
    setStep("upload");
    setThreadId(null);
    setProfile(null);
    setSearch(EMPTY_SEARCH);
    setTailored(null);
  }

  async function runSearch(next: SearchPrefs) {
    if (!threadId) return;
    setPrefs(next);
    setStep("matches");
    setSearch({ ...EMPTY_SEARCH, status: "running", startedAt: Date.now() });
    try {
      const result = await streamSearch(threadId, next, (message) =>
        setSearch((s) => ({ ...s, progress: [...s.progress, message] })),
      );
      setSearch((s) => ({ ...s, status: "done", result, finishedAt: Date.now() }));
    } catch (err) {
      setSearch((s) => ({ ...s, status: "error", error: (err as Error).message, finishedAt: Date.now() }));
    }
  }

  return (
    <>
      <Header step={step} onHome={startOver} />
      <main className="page">
        {step === "upload" && (
          <UploadStep
            onUploaded={(u) => {
              setThreadId(u.thread_id);
              setProfile(u.profile);
              setExperience(u.experience);
              setStep("prefs");
            }}
          />
        )}
        {step === "prefs" && profile && (
          <PreferencesStep profile={profile} experience={experience} initial={prefs} onSearch={runSearch} onBack={startOver} />
        )}
        {step === "matches" && threadId && (
          <MatchesStep
            threadId={threadId}
            search={search}
            onEditSearch={() => setStep("prefs")}
            onTailored={(result, job) => {
              setTailored({ result, job });
              setStep("tailored");
            }}
          />
        )}
        {step === "tailored" && threadId && tailored && (
          <TailoredStep
            threadId={threadId}
            name={profile?.name ?? null}
            result={tailored.result}
            job={tailored.job}
            onBack={() => setStep("matches")}
          />
        )}
      </main>
    </>
  );
}
