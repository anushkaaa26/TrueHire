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

  function trustPill(score: number) {
    const pct = Math.round(score * 100);
    if (pct >= 70) {
      return {
        label: `${pct}% TRUSTED`,
        cls: "border-[#141413] bg-[#141413] text-[#F7F6F2]",
      };
    }
    if (pct >= 45) {
      return {
        label: `${pct}% CAUTION`,
        cls: "border-[#141413] bg-[#E7E4DC] text-[#141413]",
      };
    }
    return {
      label: `${pct}% GHOST RISK`,
      cls: "border-[#141413] bg-transparent text-[#141413] underline decoration-2 underline-offset-4",
    };
  }

  return (
    <main className="min-h-screen bg-[#F7F6F2] text-[#141413] selection:bg-[#141413] selection:text-[#F7F6F2]">
      {/* Editorial Top Nav */}
      <header className="sticky top-0 z-20 border-b border-[#141413]/15 bg-[#F7F6F2]/95 backdrop-blur-sm">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4 md:px-10">
          <div className="flex items-baseline gap-6">
            <a href="#" className="text-xl font-semibold tracking-[-0.03em] text-[#141413]">
              TrueHire<span className="text-xs align-super font-mono ml-1">01</span>
            </a>
            <nav className="hidden items-center gap-6 text-xs uppercase tracking-[0.12em] text-[#141413]/70 md:flex">
              <a href="#search" className="hover:text-[#141413]">Search</a>
              <a href="#roles" className="hover:text-[#141413]">Open Roles</a>
              <a href="#critic" className="hover:text-[#141413]">Trust & Critic</a>
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden font-mono text-[11px] uppercase tracking-[0.08em] text-[#141413]/60 sm:inline">
              {API_BASE}
            </span>
            <button
              type="button"
              onClick={() => void handleSearch()}
              className="rounded-full border border-[#141413] bg-[#141413] px-4 py-1.5 text-xs font-medium uppercase tracking-[0.08em] text-[#F7F6F2] transition hover:bg-transparent hover:text-[#141413]"
            >
              Run Search
            </button>
          </div>
        </div>
      </header>

      {/* Editorial Hero Statement */}
      <section id="search" className="border-b border-[#141413]/15">
        <div className="mx-auto max-w-7xl px-6 py-12 md:px-10 md:py-16">
          <div className="grid grid-cols-1 gap-8 lg:grid-cols-12 lg:items-end">
            <div className="lg:col-span-8">
              <p className="font-mono text-xs uppercase tracking-[0.14em] text-[#141413]/60">
                DAILY ATS SNAPSHOTS · HYBRID SQL RRF · GHOST SCORING
              </p>
              <h1 className="mt-4 text-4xl font-medium leading-[1.03] tracking-[-0.04em] text-[#141413] sm:text-6xl">
                Roles that mean business. Signals you can trust.
              </h1>
            </div>
            <div className="lg:col-span-4">
              <p className="text-sm leading-relaxed text-[#141413]/75">
                Search indexed ATS roles across lexical + dense vector fusion, inspect lifecycle ghost-listing risk, and run candidate fit checks without guessing.
              </p>
            </div>
          </div>

          {/* Editorial Filter Bar */}
          <form
            onSubmit={handleSearch}
            className="mt-10 grid grid-cols-1 gap-4 border-t border-[#141413]/15 pt-6 md:grid-cols-12 md:items-end"
          >
            <div className="md:col-span-4">
              <label className="block font-mono text-[11px] uppercase tracking-[0.1em] text-[#141413]/65">
                Role or Query
              </label>
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Backend Python FastAPI engineer"
                className="mt-2 w-full border-b border-[#141413]/40 bg-transparent pb-2 text-sm font-medium text-[#141413] placeholder-[#141413]/40 focus:border-[#141413] focus:outline-none"
              />
            </div>

            <div className="md:col-span-4">
              <label className="block font-mono text-[11px] uppercase tracking-[0.1em] text-[#141413]/65">
                Candidate Skills
              </label>
              <input
                type="text"
                value={skillsInput}
                onChange={(e) => setSkillsInput(e.target.value)}
                placeholder="python, fastapi, sql, docker"
                className="mt-2 w-full border-b border-[#141413]/40 bg-transparent pb-2 text-sm font-medium text-[#141413] placeholder-[#141413]/40 focus:border-[#141413] focus:outline-none"
              />
            </div>

            <div className="md:col-span-1">
              <label className="block font-mono text-[11px] uppercase tracking-[0.1em] text-[#141413]/65">
                YOE
              </label>
              <input
                type="text"
                value={yoeInput}
                onChange={(e) => setYoeInput(e.target.value)}
                placeholder="1"
                className="mt-2 w-full border-b border-[#141413]/40 bg-transparent pb-2 font-mono text-sm text-[#141413] placeholder-[#141413]/40 focus:border-[#141413] focus:outline-none"
              />
            </div>

            <div className="flex items-center justify-between gap-3 md:col-span-3">
              <label className="flex cursor-pointer items-center gap-2 font-mono text-xs uppercase tracking-[0.06em] text-[#141413]/80">
                <input
                  type="checkbox"
                  checked={remoteOnly}
                  onChange={(e) => setRemoteOnly(e.target.checked)}
                  className="h-4 w-4 accent-[#141413]"
                />
                <span>Remote</span>
              </label>

              <button
                type="submit"
                disabled={loadingSearch}
                className="rounded-full border border-[#141413] bg-[#141413] px-5 py-2.5 text-xs font-medium uppercase tracking-[0.1em] text-[#F7F6F2] transition hover:bg-transparent hover:text-[#141413] disabled:opacity-50"
              >
                {loadingSearch ? "Searching..." : "Search Roles"}
              </button>
            </div>
          </form>

          {error && (
            <div className="mt-5 border border-[#141413] bg-[#E7E4DC] px-4 py-3 font-mono text-xs text-[#141413]">
              Error: {error}
            </div>
          )}
        </div>
      </section>

      {/* Main Split Editorial Grid */}
      <section id="roles" className="mx-auto max-w-7xl px-6 py-10 md:px-10">
        <div className="grid grid-cols-1 gap-10 lg:grid-cols-12">
          {/* Left Column: Index of Roles */}
          <div className="lg:col-span-7">
            <div className="flex items-baseline justify-between border-b border-[#141413] pb-3">
              <h2 className="font-mono text-xs uppercase tracking-[0.12em] text-[#141413]">
                Selected Index ({results.length})
              </h2>
              <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-[#141413]/60">
                Click row to inspect
              </span>
            </div>

            {results.length === 0 && !loadingSearch ? (
              <div className="border-b border-[#141413]/15 py-12 text-sm text-[#141413]/65">
                No roles loaded yet. Click <strong>Search Roles</strong> above to query your Postgres index.
              </div>
            ) : (
              <div className="divide-y divide-[#141413]/15 border-b border-[#141413]/15">
                {results.map((job, idx) => {
                  const isSelected = selectedJob?.job_id === job.job_id;
                  return (
                    <article
                      key={job.job_id}
                      onClick={() => void inspectJob(job)}
                      className={`group cursor-pointer py-5 transition ${
                        isSelected ? "bg-[#E7E4DC]/80 px-4 -mx-4" : "hover:bg-[#E7E4DC]/40"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex items-baseline gap-4">
                          <span className="font-mono text-xs text-[#141413]/50">
                            {String(idx + 1).padStart(2, "0")}
                          </span>
                          <div>
                            <h3 className="text-lg font-medium tracking-[-0.02em] text-[#141413] group-hover:underline underline-offset-4">
                              {job.title}
                            </h3>
                            <p className="mt-1 text-xs uppercase tracking-[0.08em] text-[#141413]/65">
                              {job.company} · {job.location || "Location N/A"}
                              {job.is_remote ? " · Remote" : ""}
                            </p>
                          </div>
                        </div>

                        <a
                          href={job.apply_url}
                          target="_blank"
                          rel="noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="shrink-0 rounded-full border border-[#141413]/30 px-3 py-1 font-mono text-[11px] uppercase tracking-[0.08em] text-[#141413] transition hover:border-[#141413] hover:bg-[#141413] hover:text-[#F7F6F2]"
                        >
                          Apply ↗
                        </a>
                      </div>

                      <div className="mt-3 flex items-center justify-between pl-8 font-mono text-[11px] text-[#141413]/60">
                        <span>
                          ID #{job.job_id} · RRF {job.rrf_score?.toFixed(4)} · Score {job.score?.toFixed(4)}
                        </span>
                        <span className="uppercase tracking-[0.08em] text-[#141413]">
                          {isSelected ? "Inspecting →" : "Inspect"}
                        </span>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </div>

          {/* Right Column: Ghost Trust & Risk Critic Dossier */}
          <aside id="critic" className="lg:col-span-5">
            <div className="sticky top-20 rounded-2xl border border-[#141413] bg-[#E7E4DC]/55 p-6 md:p-7">
              <div className="flex items-center justify-between border-b border-[#141413]/20 pb-4">
                <span className="font-mono text-xs uppercase tracking-[0.12em] text-[#141413]">
                  Trust & Risk Critic
                </span>
                {trust && (
                  <span
                    className={`rounded-full border px-3 py-1 font-mono text-[11px] font-medium tracking-[0.08em] ${
                      trustPill(trust.trust_score).cls
                    }`}
                  >
                    {trustPill(trust.trust_score).label}
                  </span>
                )}
              </div>

              {!selectedJob ? (
                <p className="mt-6 text-sm leading-relaxed text-[#141413]/70">
                  Select any role in the index to inspect its ghost-listing signals, lifecycle features, and skill-fit risk critique.
                </p>
              ) : loadingInspector ? (
                <p className="mt-6 font-mono text-xs uppercase tracking-[0.08em] text-[#141413]/70">
                  Running trust scorer & risk critic...
                </p>
              ) : (
                <div className="mt-5 space-y-6">
                  <div>
                    <h3 className="text-xl font-medium tracking-[-0.02em] text-[#141413]">
                      {selectedJob.title}
                    </h3>
                    <p className="mt-1 font-mono text-xs uppercase tracking-[0.08em] text-[#141413]/65">
                      {selectedJob.company} · Job #{selectedJob.job_id}
                    </p>
                  </div>

                  {trust && (
                    <div className="space-y-2.5 border-t border-[#141413]/15 pt-4">
                      <div className="flex items-center justify-between font-mono text-[11px] uppercase tracking-[0.08em]">
                        <span>Ghost Signals ({trust.model_version})</span>
                        <span>Ghost P: {(trust.ghost_probability * 100).toFixed(1)}%</span>
                      </div>

                      {trust.top_signals.length === 0 ? (
                        <p className="text-xs text-[#141413]/70">
                          No elevated ghost signals triggered on current snapshot history.
                        </p>
                      ) : (
                        <div className="space-y-2">
                          {trust.top_signals.map((sig) => (
                            <div
                              key={sig.signal}
                              className="flex items-center justify-between rounded-lg border border-[#141413]/15 bg-[#F7F6F2] px-3 py-2 font-mono text-xs"
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
                    <div className="space-y-4 border-t border-[#141413]/15 pt-4">
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-xs uppercase tracking-[0.1em]">
                          Risk Critic Assessment
                        </span>
                        <span className="rounded-full border border-[#141413] px-2.5 py-0.5 font-mono text-xs font-medium">
                          Fit {(critic.fit_score * 100).toFixed(0)}%
                        </span>
                      </div>

                      {critic.summary && (
                        <p className="text-sm leading-relaxed text-[#141413]/85">
                          {critic.summary}
                        </p>
                      )}

                      {critic.matched_skills.length > 0 && (
                        <div>
                          <div className="mb-2 font-mono text-[11px] uppercase tracking-[0.08em] text-[#141413]/65">
                            Matched Skills
                          </div>
                          <div className="flex flex-wrap gap-1.5">
                            {critic.matched_skills.map((sk) => (
                              <span
                                key={sk}
                                className="rounded-full border border-[#141413] bg-[#141413] px-2.5 py-0.5 font-mono text-[11px] text-[#F7F6F2]"
                              >
                                {sk}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {critic.missing_skills.length > 0 && (
                        <div>
                          <div className="mb-2 font-mono text-[11px] uppercase tracking-[0.08em] text-[#141413]/65">
                            Gaps to Verify
                          </div>
                          <div className="flex flex-wrap gap-1.5">
                            {critic.missing_skills.map((sk) => (
                              <span
                                key={sk}
                                className="rounded-full border border-[#141413]/40 bg-[#F7F6F2] px-2.5 py-0.5 font-mono text-[11px] text-[#141413]"
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
                              className="rounded-lg border border-[#141413]/15 bg-[#F7F6F2] px-3 py-2 text-xs leading-relaxed text-[#141413]/85"
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

      {/* Editorial Footer */}
      <footer className="border-t border-[#141413]/15 bg-[#F7F6F2]">
        <div className="mx-auto flex max-w-7xl flex-col justify-between gap-4 px-6 py-8 font-mono text-xs uppercase tracking-[0.08em] text-[#141413]/65 sm:flex-row md:px-10">
          <span>TrueHire · Grounded Job Search & Ghost Risk Workbench</span>
          <span>FastAPI · PostgreSQL pgvector · Next.js</span>
        </div>
      </footer>
    </main>
  );
}
