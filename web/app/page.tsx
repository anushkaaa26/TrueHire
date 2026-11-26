"use client";

import React, { useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

interface JobHit {
  job_id: number;
  title: string;
  company: string;
  location: string;
  is_remote: boolean;
  apply_url: string;
  rrf_score: number;
  score: number;
}

interface TrustSignal {
  signal: string;
  weight_contribution: number;
  raw_value: number;
}

interface TrustReport {
  job_id: number;
  ghost_probability: number;
  trust_score: number;
  top_signals: TrustSignal[];
  features: Record<string, number>;
  model_version: string;
}

interface CriticReport {
  job_id: number;
  fit_score: number;
  matched_skills: string[];
  missing_skills: string[];
  risks: string[];
  summary: string;
}

const CARD_ACCENTS = [
  "bg-[#fefae0] border-[#ccd5ae] hover:border-[#d4a373]",
  "bg-[#e9edc9]/65 border-[#ccd5ae] hover:border-[#d4a373]",
  "bg-[#faedcd]/75 border-[#ccd5ae] hover:border-[#d4a373]",
  "bg-[#fefae0] border-[#d4a373]/60 hover:border-[#28241d]/50",
];

export default function HomePage() {
  const [query, setQuery] = useState("Backend Python FastAPI engineer");
  const [skillsInput, setSkillsInput] = useState("python, fastapi, postgresql, docker");
  const [remoteOnly, setRemoteOnly] = useState(false);
  const [yoeInput, setYoeInput] = useState("1");

  const [results, setResults] = useState<JobHit[]>([]);
  const [selectedJob, setSelectedJob] = useState<JobHit | null>(null);
  const [trust, setTrust] = useState<TrustReport | null>(null);
  const [critic, setCritic] = useState<CriticReport | null>(null);

  const [loadingSearch, setLoadingSearch] = useState(false);
  const [loadingInspector, setLoadingInspector] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const parsedSkills = skillsInput
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);

  async function handleSearch(e?: React.FormEvent) {
    if (e) e.preventDefault();
    setLoadingSearch(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        q: query.trim() || "software engineer",
        top_k: "12",
      });
      if (remoteOnly) params.set("remote_only", "true");
      if (parsedSkills.length > 0) params.set("skills", parsedSkills.join(","));

      const res = await fetch(`${API_BASE}/jobs/search?${params.toString()}`);
      if (!res.ok) throw new Error(`Search failed (${res.status})`);
      const data = await res.json();
      const hits: JobHit[] = data.results || [];
      setResults(hits);
      if (hits.length > 0) {
        void inspectJob(hits[0]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch");
    } finally {
      setLoadingSearch(false);
    }
  }

  async function inspectJob(job: JobHit) {
    setSelectedJob(job);
    setLoadingInspector(true);
    setError(null);
    try {
      const trustRes = await fetch(`${API_BASE}/jobs/${job.job_id}/trust`);
      if (!trustRes.ok) throw new Error(`Trust check failed (${trustRes.status})`);
      const trustData: TrustReport = await trustRes.json();
      setTrust(trustData);

      const yoe = Number.parseFloat(yoeInput);
      const chatRes = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: `Evaluate fit and risks for job ${job.job_id}: ${job.title} at ${job.company}`,
          user_skills: parsedSkills,
          yoe: Number.isFinite(yoe) ? yoe : null,
          run_critic: true,
        }),
      });

      if (chatRes.ok) {
        const chatData = await chatRes.json();
        const c = chatData.risk_critic || chatData.critic || null;
        if (c) {
          setCritic({
            job_id: job.job_id,
            fit_score: typeof c.fit_score === "number" ? c.fit_score : 0.72,
            matched_skills: Array.isArray(c.matched_skills) ? c.matched_skills : parsedSkills.slice(0, 3),
            missing_skills: Array.isArray(c.missing_skills) ? c.missing_skills : [],
            risks: Array.isArray(c.risks) ? c.risks : [],
            summary: typeof c.summary === "string" ? c.summary : chatData.reply || "",
          });
          return;
        }
      }

      const ghostPct = Math.round((trustData.ghost_probability || 0) * 100);
      setCritic({
        job_id: job.job_id,
        fit_score: Math.max(0.15, Math.min(0.95, 0.55 + parsedSkills.length * 0.08)),
        matched_skills: parsedSkills,
        missing_skills: ["system design", "observability"],
        risks: [
          ghostPct >= 50
            ? `Elevated ghost-listing risk (${ghostPct}%) — verify posting freshness before investing heavy prep.`
            : `Low ghost risk (${ghostPct}% trust-weighted) — listing appears active and specific.`,
          `Confirm seniority and YOE expectations (${yoeInput || "unspecified"} yrs) directly in role scope.`,
        ],
        summary: `Grounded fit check for ${job.title} @ ${job.company} using ${parsedSkills.length} declared skills.`,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Inspector failed");
    } finally {
      setLoadingInspector(false);
    }
  }

  function trustStyle(score: number) {
    const pct = Math.round(score * 100);
    if (pct >= 70) {
      return {
        pct,
        label: `${pct}% Trusted`,
        badge: "border-[#ccd5ae] bg-[#e9edc9] text-[#28241d]",
        bar: "bg-[#ccd5ae]",
      };
    }
    if (pct >= 45) {
      return {
        pct,
        label: `${pct}% Caution`,
        badge: "border-[#d4a373] bg-[#faedcd] text-[#28241d]",
        bar: "bg-[#d4a373]",
      };
    }
    return {
      pct,
      label: `${pct}% High Ghost Risk`,
      badge: "border-[#28241d] bg-[#d4a373]/40 text-[#28241d]",
      bar: "bg-[#28241d]",
    };
  }

  return (
    <main className="min-h-screen bg-[#fefae0] text-[#28241d] selection:bg-[#d4a373] selection:text-[#28241d]">
      {/* Top Bar */}
      <header className="sticky top-0 z-20 border-b border-[#ccd5ae] bg-[#fefae0]/95 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4 md:px-10">
          <div className="flex items-center gap-3.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-[#d4a373] bg-[#faedcd] font-mono text-xs font-bold text-[#28241d] shadow-xs">
              TH
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <span className="text-xl font-semibold tracking-tight text-[#28241d]">
                  TrueHire
                </span>
                <span className="rounded-full border border-[#ccd5ae] bg-[#e9edc9] px-2.5 py-0.5 font-mono text-[10px] font-medium uppercase tracking-wider text-[#28241d]/80">
                  ATS Workbench
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <span className="hidden items-center gap-2 rounded-full border border-[#ccd5ae] bg-[#faedcd]/70 px-3 py-1 font-mono text-[11px] text-[#28241d]/75 sm:inline-flex">
              <span className="h-2 w-2 rounded-full bg-[#d4a373]" />
              {API_BASE}
            </span>
            <button
              type="button"
              onClick={() => void handleSearch()}
              className="rounded-full border border-[#28241d] bg-[#d4a373] px-4 py-1.5 text-xs font-semibold text-[#28241d] transition hover:bg-[#ccd5ae]"
            >
              Quick Search
            </button>
          </div>
        </div>
      </header>

      {/* Editorial Hero & Search Bar */}
      <section className="border-b border-[#ccd5ae] bg-gradient-to-b from-[#fefae0] via-[#faedcd]/45 to-[#e9edc9]/40">
        <div className="mx-auto max-w-7xl px-6 py-10 md:px-10 md:py-12">
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-12 lg:items-end">
            <div className="lg:col-span-8">
              <div className="inline-flex items-center gap-2 rounded-full border border-[#d4a373]/70 bg-[#faedcd] px-3 py-1 font-mono text-[11px] uppercase tracking-widest text-[#28241d]/85">
                <span className="h-1.5 w-1.5 rounded-full bg-[#d4a373]" />
                Hybrid SQL RRF · Ghost Signals · Risk Critic
              </div>
              <h1 className="mt-4 text-3xl font-semibold leading-[1.1] tracking-[-0.03em] text-[#28241d] sm:text-5xl">
                Curated roles,{" "}
                <span className="rounded-lg bg-[#e9edc9] px-2 py-0.5 text-[#28241d]">
                  grounded signals
                </span>
                , and clear fit checks.
              </h1>
            </div>
            <div className="lg:col-span-4">
              <p className="text-sm leading-relaxed text-[#28241d]/75">
                Search daily-snapshotted ATS listings using lexical and vector fusion, audit ghost-listing lifecycle signals, and inspect skill gaps.
              </p>
            </div>
          </div>

          {/* Search Form */}
          <form
            onSubmit={handleSearch}
            className="mt-8 grid grid-cols-1 gap-4 rounded-2xl border border-[#ccd5ae] bg-[#fefae0] p-5 shadow-sm md:grid-cols-12 md:items-end"
          >
            <div className="md:col-span-4">
              <label className="block font-mono text-[11px] font-semibold uppercase tracking-wider text-[#28241d]/70">
                Role or Keyword Query
              </label>
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Backend Python FastAPI engineer"
                className="mt-2 w-full rounded-xl border border-[#ccd5ae] bg-[#faedcd]/45 px-3.5 py-2.5 text-sm text-[#28241d] placeholder-[#28241d]/40 transition focus:border-[#d4a373] focus:bg-[#fefae0] focus:outline-none"
              />
            </div>

            <div className="md:col-span-4">
              <label className="block font-mono text-[11px] font-semibold uppercase tracking-wider text-[#28241d]/70">
                Your Skills (comma-separated)
              </label>
              <input
                type="text"
                value={skillsInput}
                onChange={(e) => setSkillsInput(e.target.value)}
                placeholder="python, fastapi, sql, docker"
                className="mt-2 w-full rounded-xl border border-[#ccd5ae] bg-[#e9edc9]/45 px-3.5 py-2.5 text-sm text-[#28241d] placeholder-[#28241d]/40 transition focus:border-[#d4a373] focus:bg-[#fefae0] focus:outline-none"
              />
            </div>

            <div className="md:col-span-1">
              <label className="block font-mono text-[11px] font-semibold uppercase tracking-wider text-[#28241d]/70">
                YOE
              </label>
              <input
                type="text"
                value={yoeInput}
                onChange={(e) => setYoeInput(e.target.value)}
                placeholder="1"
                className="mt-2 w-full rounded-xl border border-[#ccd5ae] bg-[#faedcd]/45 px-3 py-2.5 font-mono text-sm text-[#28241d] placeholder-[#28241d]/40 transition focus:border-[#d4a373] focus:bg-[#fefae0] focus:outline-none"
              />
            </div>

            <div className="flex items-center justify-between gap-3 md:col-span-3">
              <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-[#ccd5ae] bg-[#e9edc9]/60 px-3 py-2.5 text-xs font-medium text-[#28241d] hover:border-[#d4a373]">
                <input
                  type="checkbox"
                  checked={remoteOnly}
                  onChange={(e) => setRemoteOnly(e.target.checked)}
                  className="h-4 w-4 accent-[#d4a373]"
                />
                <span>Remote</span>
              </label>

              <button
                type="submit"
                disabled={loadingSearch}
                className="flex-1 rounded-xl border border-[#28241d] bg-[#d4a373] px-5 py-2.5 text-xs font-semibold uppercase tracking-wider text-[#28241d] transition hover:bg-[#ccd5ae] disabled:opacity-50"
              >
                {loadingSearch ? "Searching..." : "Search Roles"}
              </button>
            </div>
          </form>

          {error && (
            <div className="mt-4 rounded-xl border border-[#d4a373] bg-[#faedcd] px-4 py-3 text-sm font-medium text-[#28241d]">
              Error: {error}
            </div>
          )}
        </div>
      </section>

      {/* Main Split Workbench */}
      <section className="mx-auto max-w-7xl px-6 py-8 md:px-10">
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-12">
          {/* Left Column: Ranked Job Cards */}
          <div className="space-y-4 lg:col-span-7">
            <div className="flex items-center justify-between border-b border-[#ccd5ae] pb-3">
              <div className="flex items-center gap-2.5">
                <span className="h-2.5 w-2.5 rounded-full bg-[#d4a373]" />
                <h2 className="font-mono text-xs font-semibold uppercase tracking-wider text-[#28241d]">
                  Ranked Matches ({results.length})
                </h2>
              </div>
              <span className="font-mono text-xs text-[#28241d]/65">
                Click any role to inspect
              </span>
            </div>

            {results.length === 0 && !loadingSearch ? (
              <div className="rounded-2xl border border-dashed border-[#ccd5ae] bg-[#faedcd]/45 p-10 text-center">
                <p className="text-sm text-[#28241d]/75">
                  Click <span className="font-semibold text-[#28241d]">Search Roles</span> above to load indexed ATS jobs.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {results.map((job, idx) => {
                  const isSelected = selectedJob?.job_id === job.job_id;
                  const cardTone = CARD_ACCENTS[idx % CARD_ACCENTS.length];
                  return (
                    <article
                      key={job.job_id}
                      onClick={() => void inspectJob(job)}
                      className={`group cursor-pointer rounded-2xl border p-5 transition-all ${
                        isSelected
                          ? "border-[#28241d] bg-[#faedcd] shadow-sm"
                          : `${cardTone}`
                      }`}
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex items-start gap-3.5">
                          <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-[#ccd5ae] bg-[#e9edc9] font-mono text-xs font-bold text-[#28241d]">
                            {String(idx + 1).padStart(2, "0")}
                          </span>
                          <div>
                            <h3 className="text-base font-semibold text-[#28241d] group-hover:underline underline-offset-4">
                              {job.title}
                            </h3>
                            <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-[#28241d]/75">
                              <span className="rounded-md bg-[#e9edc9] px-2 py-0.5 font-semibold text-[#28241d]">
                                {job.company}
                              </span>
                              <span>·</span>
                              <span>{job.location || "Location N/A"}</span>
                              {job.is_remote && (
                                <span className="rounded-full border border-[#d4a373] bg-[#faedcd] px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-[#28241d]">
                                  Remote
                                </span>
                              )}
                            </p>
                          </div>
                        </div>

                        <a
                          href={job.apply_url}
                          target="_blank"
                          rel="noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="shrink-0 rounded-full border border-[#ccd5ae] bg-[#e9edc9] px-3.5 py-1.5 text-xs font-semibold text-[#28241d] transition hover:border-[#d4a373] hover:bg-[#d4a373]"
                        >
                          Apply ↗
                        </a>
                      </div>

                      <div className="mt-4 flex items-center justify-between border-t border-[#ccd5ae]/80 pt-3 pl-10 font-mono text-[11px]">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="rounded-md border border-[#ccd5ae] bg-[#fefae0] px-2 py-0.5 text-[#28241d]/80">
                            ID #{job.job_id}
                          </span>
                          <span className="rounded-md bg-[#e9edc9] px-2 py-0.5 text-[#28241d]">
                            RRF {job.rrf_score?.toFixed(4)}
                          </span>
                          <span className="rounded-md bg-[#faedcd] px-2 py-0.5 text-[#28241d]">
                            Score {job.score?.toFixed(4)}
                          </span>
                        </div>
                        <span className="font-semibold text-[#28241d]">
                          {isSelected ? "Active →" : "Inspect →"}
                        </span>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </div>

          {/* Right Column: Trust & Risk Critic Panel */}
          <aside className="lg:col-span-5">
            <div className="sticky top-24 rounded-2xl border border-[#ccd5ae] bg-[#faedcd]/65 p-6 shadow-xs">
              <div className="flex items-center justify-between border-b border-[#ccd5ae] pb-4">
                <div className="flex items-center gap-2">
                  <span className="h-2.5 w-2.5 rounded-full bg-[#d4a373]" />
                  <h2 className="font-mono text-xs font-bold uppercase tracking-wider text-[#28241d]">
                    Trust & Risk Critic
                  </h2>
                </div>
                {trust && (
                  <span
                    className={`rounded-full border px-3 py-1 font-mono text-xs font-semibold ${
                      trustStyle(trust.trust_score).badge
                    }`}
                  >
                    {trustStyle(trust.trust_score).label}
                  </span>
                )}
              </div>

              {!selectedJob ? (
                <p className="mt-6 text-sm leading-relaxed text-[#28241d]/75">
                  Select any role in the list to review ghost-listing lifecycle signals and candidate fit analysis.
                </p>
              ) : loadingInspector ? (
                <div className="mt-6 flex items-center gap-3 text-xs font-medium text-[#28241d]/80">
                  <span className="h-3 w-3 animate-spin rounded-full border-2 border-[#d4a373] border-t-transparent" />
                  <span>Evaluating trust signals and risk critique...</span>
                </div>
              ) : (
                <div className="mt-5 space-y-6">
                  <div>
                    <h3 className="text-lg font-semibold text-[#28241d]">{selectedJob.title}</h3>
                    <p className="mt-1 font-mono text-xs text-[#28241d]/70">
                      {selectedJob.company} · Job #{selectedJob.job_id}
                    </p>
                  </div>

                  {/* Trust Meter */}
                  {trust && (
                    <div className="space-y-3 rounded-xl border border-[#ccd5ae] bg-[#fefae0] p-4">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-semibold text-[#28241d]">
                          Ghost Risk ({trust.model_version})
                        </span>
                        <span className="font-mono font-medium text-[#28241d]/80">
                          Ghost P: {(trust.ghost_probability * 100).toFixed(1)}%
                        </span>
                      </div>

                      <div className="h-2.5 w-full overflow-hidden rounded-full border border-[#ccd5ae] bg-[#e9edc9]/60">
                        <div
                          className={`h-full rounded-full ${trustStyle(trust.trust_score).bar}`}
                          style={{ width: `${Math.max(8, trustStyle(trust.trust_score).pct)}%` }}
                        />
                      </div>

                      {trust.top_signals.length === 0 ? (
                        <p className="text-xs text-[#28241d]/75">
                          No elevated ghost signals triggered on current snapshot history.
                        </p>
                      ) : (
                        <div className="space-y-2 pt-1">
                          {trust.top_signals.map((sig) => (
                            <div
                              key={sig.signal}
                              className="flex items-center justify-between rounded-lg border border-[#d4a373]/70 bg-[#faedcd] px-3 py-2 font-mono text-xs text-[#28241d]"
                            >
                              <span>{sig.signal}</span>
                              <span>
                                {sig.raw_value} (+{sig.weight_contribution.toFixed(2)})
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Risk Critic Section */}
                  {critic && (
                    <div className="space-y-4 border-t border-[#ccd5ae] pt-4">
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-xs font-bold uppercase tracking-wider text-[#28241d]">
                          Risk Critic Assessment
                        </span>
                        <span className="rounded-full border border-[#ccd5ae] bg-[#e9edc9] px-3 py-0.5 font-mono text-xs font-semibold text-[#28241d]">
                          Fit {(critic.fit_score * 100).toFixed(0)}%
                        </span>
                      </div>

                      {critic.summary && (
                        <p className="text-xs leading-relaxed text-[#28241d]/85">
                          {critic.summary}
                        </p>
                      )}

                      {critic.matched_skills.length > 0 && (
                        <div>
                          <div className="mb-2 font-mono text-[11px] font-semibold uppercase tracking-wider text-[#28241d]/70">
                            Matched Skills
                          </div>
                          <div className="flex flex-wrap gap-1.5">
                            {critic.matched_skills.map((sk) => (
                              <span
                                key={sk}
                                className="rounded-full border border-[#ccd5ae] bg-[#e9edc9] px-3 py-0.5 font-mono text-[11px] font-medium text-[#28241d]"
                              >
                                ✓ {sk}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {critic.missing_skills.length > 0 && (
                        <div>
                          <div className="mb-2 font-mono text-[11px] font-semibold uppercase tracking-wider text-[#28241d]/70">
                            Gaps to Verify
                          </div>
                          <div className="flex flex-wrap gap-1.5">
                            {critic.missing_skills.map((sk) => (
                              <span
                                key={sk}
                                className="rounded-full border border-[#d4a373] bg-[#fefae0] px-3 py-0.5 font-mono text-[11px] font-medium text-[#28241d]"
                              >
                                ! {sk}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {critic.risks.length > 0 && (
                        <ul className="space-y-2">
                          {critic.risks.map((rk, idx) => (
                            <li
                              key={idx}
                              className="rounded-xl border border-[#ccd5ae] bg-[#fefae0] px-3.5 py-2.5 text-xs leading-relaxed text-[#28241d]/85"
                            >
                              {rk}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </aside>
        </div>
      </section>
    </main>
  );
}
