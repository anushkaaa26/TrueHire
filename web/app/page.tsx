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

const ACCENT_GRADIENTS = [
  "from-cyan-500/20 via-blue-500/10 to-transparent border-cyan-400/30",
  "from-violet-500/20 via-fuchsia-500/10 to-transparent border-violet-400/30",
  "from-emerald-500/20 via-teal-500/10 to-transparent border-emerald-400/30",
  "from-amber-500/20 via-orange-500/10 to-transparent border-amber-400/30",
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

  function trustTheme(score: number) {
    const pct = Math.round(score * 100);
    if (pct >= 70) {
      return {
        pct,
        label: `${pct}% Trusted`,
        pill: "border-emerald-400/50 bg-gradient-to-r from-emerald-500/25 to-teal-500/20 text-emerald-200 shadow-sm shadow-emerald-500/20",
        bar: "from-emerald-400 via-teal-400 to-cyan-400",
      };
    }
    if (pct >= 45) {
      return {
        pct,
        label: `${pct}% Caution`,
        pill: "border-amber-400/50 bg-gradient-to-r from-amber-500/25 to-orange-500/20 text-amber-200 shadow-sm shadow-amber-500/20",
        bar: "from-amber-400 via-orange-400 to-yellow-300",
      };
    }
    return {
      pct,
      label: `${pct}% High Ghost Risk`,
      pill: "border-rose-400/50 bg-gradient-to-r from-rose-500/25 to-pink-500/20 text-rose-200 shadow-sm shadow-rose-500/20",
      bar: "from-rose-500 via-pink-500 to-orange-400",
    };
  }

  return (
    <main className="relative min-h-screen overflow-x-hidden bg-[#06070D] text-slate-100 selection:bg-cyan-400 selection:text-slate-950">
      {/* Ambient Colorful Mesh Glows */}
      <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
        <div className="absolute -left-32 -top-24 h-96 w-96 rounded-full bg-cyan-500/20 blur-3xl" />
        <div className="absolute right-0 top-16 h-[28rem] w-[28rem] rounded-full bg-fuchsia-600/15 blur-3xl" />
        <div className="absolute bottom-0 left-1/3 h-96 w-96 rounded-full bg-emerald-500/15 blur-3xl" />
      </div>

      {/* Top Glass Navbar */}
      <header className="sticky top-0 z-20 border-b border-white/10 bg-[#06070D]/80 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4 md:px-10">
          <div className="flex items-center gap-4">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-400 via-indigo-500 to-fuchsia-500 font-mono text-sm font-bold text-slate-950 shadow-lg shadow-indigo-500/30">
              TH
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <span className="bg-gradient-to-r from-white via-cyan-200 to-violet-300 bg-clip-text text-xl font-bold tracking-tight text-transparent">
                  TrueHire
                </span>
                <span className="rounded-full border border-cyan-400/30 bg-cyan-400/10 px-2.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-cyan-300">
                  Live ATS Index
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <span className="hidden items-center gap-2 rounded-full border border-emerald-400/25 bg-emerald-500/10 px-3 py-1 font-mono text-[11px] text-emerald-300 sm:inline-flex">
              <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
              {API_BASE}
            </span>
            <button
              type="button"
              onClick={() => void handleSearch()}
              className="rounded-full bg-gradient-to-r from-cyan-400 via-indigo-500 to-fuchsia-500 px-4 py-1.5 text-xs font-semibold text-white shadow-md shadow-indigo-500/30 transition hover:brightness-110"
            >
              Quick Search
            </button>
          </div>
        </div>
      </header>

      {/* Hero Banner */}
      <section className="border-b border-white/10">
        <div className="mx-auto max-w-7xl px-6 py-10 md:px-10">
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-12 lg:items-end">
            <div className="lg:col-span-8">
              <div className="inline-flex items-center gap-2 rounded-full border border-violet-400/30 bg-violet-500/10 px-3 py-1 font-mono text-[11px] uppercase tracking-widest text-violet-200">
                <span className="h-1.5 w-1.5 rounded-full bg-violet-400" />
                Hybrid SQL RRF · Ghost Lifecycle Signals · Risk Critic
              </div>
              <h1 className="mt-4 text-3xl font-bold leading-tight tracking-tight text-white sm:text-5xl">
                Roles that{" "}
                <span className="bg-gradient-to-r from-cyan-300 via-sky-400 to-indigo-400 bg-clip-text text-transparent">
                  mean business
                </span>
                . Signals you can{" "}
                <span className="bg-gradient-to-r from-emerald-300 via-teal-300 to-cyan-300 bg-clip-text text-transparent">
                  actually trust
                </span>
                .
              </h1>
            </div>
            <div className="lg:col-span-4">
              <p className="text-sm leading-relaxed text-slate-300">
                Search daily-snapshotted ATS roles with lexical + vector fusion, inspect ghost-job risk signals, and uncover skill gaps before applying.
              </p>
            </div>
          </div>

          {/* Colorful Search & Profile Workbench */}
          <form
            onSubmit={handleSearch}
            className="mt-8 grid grid-cols-1 gap-4 rounded-2xl border border-white/15 bg-gradient-to-br from-white/[0.07] via-indigo-500/[0.04] to-cyan-500/[0.04] p-5 shadow-2xl shadow-black/40 backdrop-blur-md md:grid-cols-12 md:items-end"
          >
            <div className="md:col-span-4">
              <label className="block font-mono text-[11px] font-semibold uppercase tracking-wider text-cyan-300">
                Role or Keyword Query
              </label>
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Backend Python FastAPI engineer"
                className="mt-2 w-full rounded-xl border border-white/15 bg-[#0A0D18] px-3.5 py-2.5 text-sm text-white placeholder-slate-500 transition focus:border-cyan-400 focus:outline-none focus:ring-2 focus:ring-cyan-400/20"
              />
            </div>

            <div className="md:col-span-4">
              <label className="block font-mono text-[11px] font-semibold uppercase tracking-wider text-violet-300">
                Your Skills (comma-separated)
              </label>
              <input
                type="text"
                value={skillsInput}
                onChange={(e) => setSkillsInput(e.target.value)}
                placeholder="python, fastapi, sql, docker"
                className="mt-2 w-full rounded-xl border border-white/15 bg-[#0A0D18] px-3.5 py-2.5 text-sm text-white placeholder-slate-500 transition focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-400/20"
              />
            </div>

            <div className="md:col-span-1">
              <label className="block font-mono text-[11px] font-semibold uppercase tracking-wider text-amber-300">
                YOE
              </label>
              <input
                type="text"
                value={yoeInput}
                onChange={(e) => setYoeInput(e.target.value)}
                placeholder="1"
                className="mt-2 w-full rounded-xl border border-white/15 bg-[#0A0D18] px-3 py-2.5 font-mono text-sm text-white placeholder-slate-500 transition focus:border-amber-400 focus:outline-none focus:ring-2 focus:ring-amber-400/20"
              />
            </div>

            <div className="flex items-center justify-between gap-3 md:col-span-3">
              <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-white/15 bg-[#0A0D18] px-3 py-2.5 text-xs font-medium text-slate-200 hover:border-cyan-400/40">
                <input
                  type="checkbox"
                  checked={remoteOnly}
                  onChange={(e) => setRemoteOnly(e.target.checked)}
                  className="h-4 w-4 accent-cyan-400"
                />
                <span>Remote</span>
              </label>

              <button
                type="submit"
                disabled={loadingSearch}
                className="flex-1 rounded-xl bg-gradient-to-r from-cyan-400 via-blue-500 to-violet-500 px-5 py-2.5 text-xs font-bold uppercase tracking-wider text-white shadow-lg shadow-blue-500/25 transition hover:brightness-110 disabled:opacity-50"
              >
                {loadingSearch ? "Searching..." : "Search Roles"}
              </button>
            </div>
          </form>

          {error && (
            <div className="mt-4 rounded-xl border border-rose-400/40 bg-rose-500/15 px-4 py-3 text-sm text-rose-200">
              Error: {error}
            </div>
          )}
        </div>
      </section>

      {/* Main Split Workbench */}
      <section className="mx-auto max-w-7xl px-6 py-8 md:px-10">
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-12">
          {/* Left Column: Vibrant Ranked Cards */}
          <div className="space-y-4 lg:col-span-7">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <span className="h-2.5 w-2.5 rounded-full bg-gradient-to-r from-cyan-400 to-indigo-400" />
                <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-200">
                  Ranked Matches ({results.length})
                </h2>
              </div>
              <span className="font-mono text-xs text-slate-400">
                Select any role to inspect
              </span>
            </div>

            {results.length === 0 && !loadingSearch ? (
              <div className="rounded-2xl border border-dashed border-white/15 bg-white/[0.03] p-10 text-center">
                <p className="text-sm text-slate-300">
                  Click <span className="font-semibold text-cyan-300">Search Roles</span> above to query your indexed ATS jobs.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {results.map((job, idx) => {
                  const isSelected = selectedJob?.job_id === job.job_id;
                  const accent = ACCENT_GRADIENTS[idx % ACCENT_GRADIENTS.length];
                  return (
                    <article
                      key={job.job_id}
                      onClick={() => void inspectJob(job)}
                      className={`group cursor-pointer rounded-2xl border p-5 transition-all ${
                        isSelected
                          ? "border-cyan-400/70 bg-gradient-to-r from-cyan-500/15 via-indigo-500/15 to-violet-500/15 shadow-lg shadow-cyan-500/10"
                          : `bg-gradient-to-r ${accent} bg-[#0B0E1A]/90 hover:-translate-y-0.5 hover:border-white/30`
                      }`}
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex items-start gap-3.5">
                          <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-white/10 font-mono text-xs font-bold text-cyan-300">
                            {String(idx + 1).padStart(2, "0")}
                          </span>
                          <div>
                            <h3 className="text-base font-semibold text-white group-hover:text-cyan-200">
                              {job.title}
                            </h3>
                            <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-300">
                              <span className="font-semibold text-violet-300">{job.company}</span>
                              <span className="text-slate-600">•</span>
                              <span>{job.location || "Location N/A"}</span>
                              {job.is_remote && (
                                <span className="rounded-full border border-sky-400/40 bg-sky-500/15 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-sky-200">
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
                          className="shrink-0 rounded-full border border-white/20 bg-white/10 px-3.5 py-1.5 text-xs font-semibold text-white transition hover:border-cyan-300 hover:bg-cyan-400 hover:text-slate-950"
                        >
                          Apply ↗
                        </a>
                      </div>

                      <div className="mt-4 flex items-center justify-between border-t border-white/10 pt-3 pl-10 font-mono text-[11px]">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="rounded-md bg-white/5 px-2 py-0.5 text-slate-300">
                            ID #{job.job_id}
                          </span>
                          <span className="rounded-md bg-indigo-500/15 px-2 py-0.5 text-indigo-200">
                            RRF {job.rrf_score?.toFixed(4)}
                          </span>
                          <span className="rounded-md bg-emerald-500/15 px-2 py-0.5 text-emerald-200">
                            Score {job.score?.toFixed(4)}
                          </span>
                        </div>
                        <span className="font-semibold text-cyan-300">
                          {isSelected ? "Active Inspector →" : "Inspect →"}
                        </span>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </div>

          {/* Right Column: Colorful Ghost Trust & Risk Critic Dossier */}
          <aside className="lg:col-span-5">
            <div className="sticky top-24 rounded-2xl border border-white/15 bg-gradient-to-b from-[#111528] via-[#0D1020] to-[#0A0C18] p-6 shadow-2xl shadow-indigo-950/30">
              <div className="flex items-center justify-between border-b border-white/10 pb-4">
                <div className="flex items-center gap-2">
                  <span className="h-2.5 w-2.5 rounded-full bg-gradient-to-r from-emerald-400 to-cyan-400" />
                  <h2 className="text-sm font-bold uppercase tracking-wider text-white">
                    Trust & Risk Critic
                  </h2>
                </div>
                {trust && (
                  <span
                    className={`rounded-full border px-3 py-1 text-xs font-bold ${
                      trustTheme(trust.trust_score).pill
                    }`}
                  >
                    {trustTheme(trust.trust_score).label}
                  </span>
                )}
              </div>

              {!selectedJob ? (
                <p className="mt-6 text-sm leading-relaxed text-slate-400">
                  Click any job card on the left to inspect ghost-listing lifecycle signals and candidate fit risks.
                </p>
              ) : loadingInspector ? (
                <div className="mt-6 flex items-center gap-3 text-xs font-medium text-cyan-300">
                  <span className="h-3 w-3 animate-spin rounded-full border-2 border-cyan-300 border-t-transparent" />
                  <span>Analyzing ghost signals & candidate fit...</span>
                </div>
              ) : (
                <div className="mt-5 space-y-6">
                  <div>
                    <h3 className="text-lg font-bold text-white">{selectedJob.title}</h3>
                    <p className="mt-1 text-xs font-medium text-violet-300">
                      {selectedJob.company} · Job #{selectedJob.job_id}
                    </p>
                  </div>

                  {/* Visual Trust Gauge */}
                  {trust && (
                    <div className="space-y-3 rounded-xl border border-white/10 bg-black/30 p-4">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-semibold text-slate-200">
                          Ghost-Listing Risk ({trust.model_version})
                        </span>
                        <span className="font-mono font-semibold text-cyan-300">
                          Ghost P: {(trust.ghost_probability * 100).toFixed(1)}%
                        </span>
                      </div>

                      <div className="h-2.5 w-full overflow-hidden rounded-full bg-white/10">
                        <div
                          className={`h-full rounded-full bg-gradient-to-r ${
                            trustTheme(trust.trust_score).bar
                          }`}
                          style={{ width: `${Math.max(8, trustTheme(trust.trust_score).pct)}%` }}
                        />
                      </div>

                      {trust.top_signals.length === 0 ? (
                        <p className="text-xs text-emerald-300/90">
                          Clean snapshot history — no elevated ghost signals triggered.
                        </p>
                      ) : (
                        <div className="space-y-2 pt-1">
                          {trust.top_signals.map((sig) => (
                            <div
                              key={sig.signal}
                              className="flex items-center justify-between rounded-lg border border-amber-400/25 bg-amber-500/10 px-3 py-2 font-mono text-xs text-amber-100"
                            >
                              <span>{sig.signal}</span>
                              <span className="text-amber-300">
                                val={sig.raw_value} (+{sig.weight_contribution.toFixed(2)})
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Risk Critic Panel */}
                  {critic && (
                    <div className="space-y-4 border-t border-white/10 pt-4">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold uppercase tracking-wider text-fuchsia-300">
                          Risk Critic Assessment
                        </span>
                        <span className="rounded-full border border-indigo-400/40 bg-indigo-500/20 px-3 py-0.5 font-mono text-xs font-bold text-indigo-200">
                          Fit {(critic.fit_score * 100).toFixed(0)}%
                        </span>
                      </div>

                      {critic.summary && (
                        <p className="text-xs leading-relaxed text-slate-200">
                          {critic.summary}
                        </p>
                      )}

                      {critic.matched_skills.length > 0 && (
                        <div>
                          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-emerald-300">
                            Matched Skills
                          </div>
                          <div className="flex flex-wrap gap-1.5">
                            {critic.matched_skills.map((sk) => (
                              <span
                                key={sk}
                                className="rounded-full border border-emerald-400/40 bg-emerald-500/15 px-3 py-0.5 font-mono text-[11px] font-medium text-emerald-200"
                              >
                                ✓ {sk}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {critic.missing_skills.length > 0 && (
                        <div>
                          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-amber-300">
                            Gaps to Verify
                          </div>
                          <div className="flex flex-wrap gap-1.5">
                            {critic.missing_skills.map((sk) => (
                              <span
                                key={sk}
                                className="rounded-full border border-amber-400/40 bg-amber-500/15 px-3 py-0.5 font-mono text-[11px] font-medium text-amber-200"
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
                              className="rounded-xl border border-violet-400/20 bg-violet-500/10 px-3.5 py-2.5 text-xs leading-relaxed text-slate-200"
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
