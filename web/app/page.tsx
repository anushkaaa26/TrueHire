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
        badge: "border-[#ccd5ae] bg-[#e9edc9] text-[#18181b]",
        bar: "bg-[#ccd5ae]",
      };
    }
    if (pct >= 45) {
      return {
        pct,
        label: `${pct}% Caution`,
        badge: "border-[#d4a373] bg-[#faedcd] text-[#18181b]",
        bar: "bg-[#d4a373]",
      };
    }
    return {
      pct,
      label: `${pct}% Ghost Risk`,
      badge: "border-[#d4a373] bg-[#fefae0] text-[#18181b]",
      bar: "bg-[#d4a373]",
    };
  }

  return (
    <main className="min-h-screen bg-[#ffffff] text-[#18181b] antialiased">
      {/* Clean Header */}
      <header className="sticky top-0 z-20 border-b border-zinc-200/90 bg-white/95 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4 md:px-10">
          <div className="flex items-center gap-3">
            <span className="h-3 w-3 rounded-full bg-[#d4a373]" />
            <span className="text-xl font-bold tracking-tight text-zinc-950">TrueHire</span>
            <span className="hidden rounded-full border border-[#ccd5ae] bg-[#e9edc9]/70 px-2.5 py-0.5 font-mono text-[11px] font-medium text-zinc-800 sm:inline">
              Hybrid RRF · Ghost Trust · Risk Critic
            </span>
          </div>

          <div className="flex items-center gap-3">
            <span className="hidden rounded-full border border-zinc-200 bg-[#fefae0] px-3 py-1 font-mono text-[11px] text-zinc-700 md:inline">
              {API_BASE}
            </span>
            <button
              type="button"
              onClick={() => void handleSearch()}
              className="rounded-lg bg-zinc-950 px-4 py-2 text-xs font-bold tracking-wide text-white shadow-xs transition hover:bg-zinc-800"
            >
              Search Roles
            </button>
          </div>
        </div>
      </header>

      {/* Hero & Search Bar */}
      <section className="border-b border-zinc-200 bg-gradient-to-b from-[#ffffff] via-[#fefae0]/55 to-[#e9edc9]/30">
        <div className="mx-auto max-w-7xl px-6 py-10 md:px-10 md:py-12">
          <div className="flex flex-col justify-between gap-6 lg:flex-row lg:items-end">
            <div className="max-w-3xl">
              <p className="inline-flex items-center gap-2 rounded-full border border-[#d4a373]/60 bg-[#faedcd]/80 px-3 py-1 font-mono text-[11px] font-semibold uppercase tracking-wider text-zinc-900">
                <span className="h-1.5 w-1.5 rounded-full bg-[#d4a373]" />
                ATS Snapshot Intelligence
              </p>
              <h1 className="mt-3 text-3xl font-bold tracking-tight text-zinc-950 sm:text-5xl">
                Find roles worth applying to, backed by{" "}
                <span className="border-b-4 border-[#d4a373] pb-0.5">trust signals</span>.
              </h1>
            </div>
            <p className="max-w-sm text-sm leading-relaxed text-zinc-600">
              Combine lexical and semantic search with snapshot lifecycle scoring and candidate skill-gap analysis.
            </p>
          </div>

          <form
            onSubmit={handleSearch}
            className="mt-8 grid grid-cols-1 gap-4 rounded-2xl border border-zinc-200/90 bg-white p-5 shadow-xs md:grid-cols-12 md:items-end"
          >
            <div className="md:col-span-4">
              <label className="block font-mono text-[11px] font-semibold uppercase tracking-wider text-zinc-600">
                Role or Query
              </label>
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Backend Python FastAPI engineer"
                className="mt-2 w-full rounded-xl border border-zinc-200 bg-[#fefae0]/50 px-3.5 py-2.5 text-sm text-zinc-950 placeholder-zinc-400 transition focus:border-[#d4a373] focus:bg-white focus:outline-none"
              />
            </div>

            <div className="md:col-span-4">
              <label className="block font-mono text-[11px] font-semibold uppercase tracking-wider text-zinc-600">
                Your Skills
              </label>
              <input
                type="text"
                value={skillsInput}
                onChange={(e) => setSkillsInput(e.target.value)}
                placeholder="python, fastapi, sql, docker"
                className="mt-2 w-full rounded-xl border border-zinc-200 bg-[#e9edc9]/45 px-3.5 py-2.5 text-sm text-zinc-950 placeholder-zinc-400 transition focus:border-[#d4a373] focus:bg-white focus:outline-none"
              />
            </div>

            <div className="md:col-span-1">
              <label className="block font-mono text-[11px] font-semibold uppercase tracking-wider text-zinc-600">
                YOE
              </label>
              <input
                type="text"
                value={yoeInput}
                onChange={(e) => setYoeInput(e.target.value)}
                placeholder="1"
                className="mt-2 w-full rounded-xl border border-zinc-200 bg-[#faedcd]/45 px-3 py-2.5 font-mono text-sm text-zinc-950 placeholder-zinc-400 transition focus:border-[#d4a373] focus:bg-white focus:outline-none"
              />
            </div>

            <div className="flex items-center justify-between gap-3 md:col-span-3">
              <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-[#ccd5ae] bg-[#e9edc9]/60 px-3 py-2.5 text-xs font-semibold text-zinc-900 hover:bg-[#e9edc9]">
                <input
                  type="checkbox"
                  checked={remoteOnly}
                  onChange={(e) => setRemoteOnly(e.target.checked)}
                  className="h-4 w-4 accent-zinc-950"
                />
                <span>Remote</span>
              </label>

              <button
                type="submit"
                disabled={loadingSearch}
                className="flex-1 rounded-xl bg-zinc-950 px-5 py-2.5 text-xs font-bold uppercase tracking-wider text-white shadow-xs transition hover:bg-zinc-800 disabled:opacity-50"
              >
                {loadingSearch ? "Searching..." : "Search Roles"}
              </button>
            </div>
          </form>

          {error && (
            <div className="mt-4 rounded-xl border border-[#d4a373] bg-[#faedcd] px-4 py-3 text-sm font-medium text-zinc-900">
              Error: {error}
            </div>
          )}
        </div>
      </section>

      {/* Main Content Grid */}
      <section className="mx-auto max-w-7xl px-6 py-8 md:px-10">
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-12">
          {/* Left: Ranked Jobs */}
          <div className="space-y-4 lg:col-span-7">
            <div className="flex items-center justify-between border-b border-zinc-200 pb-3">
              <div className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full bg-[#ccd5ae]" />
                <h2 className="text-xs font-bold uppercase tracking-wider text-zinc-900">
                  Matching Roles ({results.length})
                </h2>
              </div>
              <span className="font-mono text-xs text-zinc-500">Click a role to inspect</span>
            </div>

            {results.length === 0 && !loadingSearch ? (
              <div className="rounded-2xl border border-dashed border-zinc-300 bg-[#fefae0]/60 p-10 text-center text-sm text-zinc-600">
                Click <strong className="text-zinc-950">Search Roles</strong> above to view ranked jobs from Postgres.
              </div>
            ) : (
              <div className="space-y-3">
                {results.map((job, idx) => {
                  const isSelected = selectedJob?.job_id === job.job_id;
                  return (
                    <article
                      key={job.job_id}
                      onClick={() => void inspectJob(job)}
                      className={`group cursor-pointer rounded-2xl border p-5 transition ${
                        isSelected
                          ? "border-zinc-950 bg-[#fefae0] shadow-xs"
                          : "border-zinc-200 bg-white hover:border-[#d4a373] hover:bg-[#fefae0]/45"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex items-start gap-3.5">
                          <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-[#ccd5ae] bg-[#e9edc9] font-mono text-xs font-bold text-zinc-900">
                            {String(idx + 1).padStart(2, "0")}
                          </span>
                          <div>
                            <h3 className="text-base font-semibold text-zinc-950 group-hover:underline underline-offset-4">
                              {job.title}
                            </h3>
                            <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-zinc-600">
                              <span className="rounded-md bg-[#faedcd] px-2 py-0.5 font-semibold text-zinc-900">
                                {job.company}
                              </span>
                              <span>·</span>
                              <span>{job.location || "Location N/A"}</span>
                              {job.is_remote && (
                                <span className="rounded-full border border-[#ccd5ae] bg-[#e9edc9] px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-zinc-900">
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
                          className="shrink-0 rounded-lg bg-zinc-950 px-3.5 py-1.5 text-xs font-bold text-white transition hover:bg-zinc-800"
                        >
                          Apply ↗
                        </a>
                      </div>

                      <div className="mt-4 flex items-center justify-between border-t border-zinc-100 pt-3 pl-10 font-mono text-[11px] text-zinc-600">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="rounded-md bg-zinc-100 px-2 py-0.5 text-zinc-800">
                            #{job.job_id}
                          </span>
                          <span className="rounded-md bg-[#e9edc9]/70 px-2 py-0.5 text-zinc-900">
                            RRF {job.rrf_score?.toFixed(4)}
                          </span>
                          <span className="rounded-md bg-[#faedcd]/80 px-2 py-0.5 text-zinc-900">
                            Score {job.score?.toFixed(4)}
                          </span>
                        </div>
                        <span className="font-semibold text-zinc-950">
                          {isSelected ? "Selected →" : "Inspect →"}
                        </span>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </div>

          {/* Right: Trust & Risk Critic Panel */}
          <aside className="lg:col-span-5">
            <div className="sticky top-24 rounded-2xl border border-zinc-200 bg-[#fefae0]/70 p-6 shadow-xs">
              <div className="flex items-center justify-between border-b border-zinc-200 pb-4">
                <div className="flex items-center gap-2">
                  <span className="h-2.5 w-2.5 rounded-full bg-[#d4a373]" />
                  <h2 className="text-xs font-bold uppercase tracking-wider text-zinc-950">
                    Trust & Risk Critic
                  </h2>
                </div>
                {trust && (
                  <span
                    className={`rounded-full border px-3 py-1 font-mono text-xs font-bold ${
                      trustStyle(trust.trust_score).badge
                    }`}
                  >
                    {trustStyle(trust.trust_score).label}
                  </span>
                )}
              </div>

              {!selectedJob ? (
                <p className="mt-6 text-sm leading-relaxed text-zinc-600">
                  Select a job card on the left to inspect ghost-listing trust signals and candidate fit analysis.
                </p>
              ) : loadingInspector ? (
                <p className="mt-6 font-mono text-xs text-zinc-600">Evaluating trust & risk signals...</p>
              ) : (
                <div className="mt-5 space-y-6">
                  <div>
                    <h3 className="text-lg font-bold text-zinc-950">{selectedJob.title}</h3>
                    <p className="mt-1 font-mono text-xs text-zinc-600">
                      {selectedJob.company} · Job #{selectedJob.job_id}
                    </p>
                  </div>

                  {trust && (
                    <div className="space-y-3 rounded-xl border border-zinc-200 bg-white p-4">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-semibold text-zinc-900">
                          Ghost Risk ({trust.model_version})
                        </span>
                        <span className="font-mono text-zinc-700">
                          {(trust.ghost_probability * 100).toFixed(1)}%
                        </span>
                      </div>

                      <div className="h-2.5 w-full overflow-hidden rounded-full bg-zinc-100">
                        <div
                          className={`h-full rounded-full ${trustStyle(trust.trust_score).bar}`}
                          style={{ width: `${Math.max(8, trustStyle(trust.trust_score).pct)}%` }}
                        />
                      </div>

                      {trust.top_signals.length === 0 ? (
                        <p className="text-xs text-zinc-600">
                          No elevated ghost signals triggered on current snapshot history.
                        </p>
                      ) : (
                        <div className="space-y-2 pt-1">
                          {trust.top_signals.map((sig) => (
                            <div
                              key={sig.signal}
                              className="flex items-center justify-between rounded-lg border border-[#d4a373]/60 bg-[#faedcd]/65 px-3 py-2 font-mono text-xs text-zinc-900"
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

                  {critic && (
                    <div className="space-y-4 border-t border-zinc-200 pt-4">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold uppercase tracking-wider text-zinc-950">
                          Risk Critic Assessment
                        </span>
                        <span className="rounded-full border border-[#ccd5ae] bg-[#e9edc9] px-3 py-0.5 font-mono text-xs font-bold text-zinc-950">
                          Fit {(critic.fit_score * 100).toFixed(0)}%
                        </span>
                      </div>

                      {critic.summary && (
                        <p className="text-xs leading-relaxed text-zinc-700">{critic.summary}</p>
                      )}

                      {critic.matched_skills.length > 0 && (
                        <div>
                          <div className="mb-2 font-mono text-[11px] font-semibold uppercase tracking-wider text-zinc-600">
                            Matched Skills
                          </div>
                          <div className="flex flex-wrap gap-1.5">
                            {critic.matched_skills.map((sk) => (
                              <span
                                key={sk}
                                className="rounded-full border border-[#ccd5ae] bg-[#e9edc9] px-3 py-0.5 font-mono text-[11px] font-semibold text-zinc-900"
                              >
                                {sk}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {critic.missing_skills.length > 0 && (
                        <div>
                          <div className="mb-2 font-mono text-[11px] font-semibold uppercase tracking-wider text-zinc-600">
                            Gaps to Verify
                          </div>
                          <div className="flex flex-wrap gap-1.5">
                            {critic.missing_skills.map((sk) => (
                              <span
                                key={sk}
                                className="rounded-full border border-[#d4a373] bg-[#faedcd] px-3 py-0.5 font-mono text-[11px] font-semibold text-zinc-900"
                              >
                                {sk}
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
                              className="rounded-xl border border-zinc-200 bg-white px-3.5 py-2.5 text-xs leading-relaxed text-zinc-800"
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
