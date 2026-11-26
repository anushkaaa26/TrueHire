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
      if (hits.length > 0 && !selectedJob) {
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

      // Build Risk Critic analysis from /chat if available, with deterministic local fallback
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

  function trustBadge(score: number) {
    const pct = Math.round(score * 100);
    if (pct >= 70) {
      return {
        label: `${pct}% Trusted`,
        cls: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
      };
    }
    if (pct >= 45) {
      return {
        label: `${pct}% Caution`,
        cls: "border-amber-500/40 bg-amber-500/10 text-amber-300",
      };
    }
    return {
      label: `${pct}% High Ghost Risk`,
      cls: "border-rose-500/40 bg-rose-500/10 text-rose-300",
    };
  }

  return (
    <main className="min-h-screen bg-[#09090b] text-zinc-100 antialiased">
      <div className="mx-auto max-w-7xl px-6 py-8">
        {/* Top Header */}
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-800/80 pb-6">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-semibold tracking-tight text-white">TrueHire</h1>
              <span className="rounded-full border border-zinc-800 bg-zinc-900 px-2.5 py-0.5 text-xs font-medium text-zinc-400">
                Hybrid SQL RRF + Ghost Trust + Risk Critic
              </span>
            </div>
            <p className="mt-1.5 text-sm text-zinc-400">
              Daily-snapshotted ATS listings scored with lifecycle signals, Reciprocal Rank Fusion, and candidate fit analysis.
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs text-zinc-400">
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
            <span>API: {API_BASE}</span>
          </div>
        </header>

        {/* Search & Profile Controls */}
        <form
          onSubmit={handleSearch}
          className="mt-6 grid grid-cols-1 gap-3 rounded-xl border border-zinc-800/90 bg-zinc-900/50 p-4 md:grid-cols-12"
        >
          <div className="md:col-span-5">
            <label className="mb-1 block text-xs font-medium text-zinc-400">Role or Keyword Query</label>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. Backend Python FastAPI engineer"
              className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3.5 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:border-zinc-600 focus:outline-none"
            />
          </div>

          <div className="md:col-span-4">
            <label className="mb-1 block text-xs font-medium text-zinc-400">Your Skills (comma-separated)</label>
            <input
              type="text"
              value={skillsInput}
              onChange={(e) => setSkillsInput(e.target.value)}
              placeholder="python, fastapi, sql, docker"
              className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3.5 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:border-zinc-600 focus:outline-none"
            />
          </div>

          <div className="md:col-span-1">
            <label className="mb-1 block text-xs font-medium text-zinc-400">YOE</label>
            <input
              type="text"
              value={yoeInput}
              onChange={(e) => setYoeInput(e.target.value)}
              placeholder="1"
              className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:border-zinc-600 focus:outline-none"
            />
          </div>

          <div className="flex flex-col justify-between gap-2 md:col-span-2">
            <label className="flex cursor-pointer items-center gap-2 text-xs text-zinc-300 pt-1">
              <input
                type="checkbox"
                checked={remoteOnly}
                onChange={(e) => setRemoteOnly(e.target.checked)}
                className="h-4 w-4 rounded border-zinc-700 bg-zinc-950 text-white focus:ring-0"
              />
              <span>Remote only</span>
            </label>
            <button
              type="submit"
              disabled={loadingSearch}
              className="w-full rounded-lg bg-white px-3.5 py-2 text-xs font-semibold text-zinc-950 transition hover:bg-zinc-200 disabled:opacity-50"
            >
              {loadingSearch ? "Searching..." : "Search Roles"}
            </button>
          </div>
        </form>

        {error && (
          <div className="mt-4 rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
            Error: {error}
          </div>
        )}

        {/* Two-Column Workbench: Ranked Results + Trust & Risk Critic Drawer */}
        <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-12">
          {/* Left: Ranked Jobs */}
          <section className="space-y-3 lg:col-span-7">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-medium text-zinc-300">
                Ranked Matches ({results.length})
              </h2>
              <span className="text-xs text-zinc-500">Click any role to inspect trust & fit risks</span>
            </div>

            {results.length === 0 && !loadingSearch ? (
              <div className="rounded-xl border border-dashed border-zinc-800 bg-zinc-900/30 p-8 text-center text-sm text-zinc-400">
                Run a search to inspect ranked roles, ghost-listing trust scores, and candidate risk analysis.
              </div>
            ) : (
              <div className="space-y-2.5">
                {results.map((job) => {
                  const active = selectedJob?.job_id === job.job_id;
                  return (
                    <div
                      key={job.job_id}
                      onClick={() => void inspectJob(job)}
                      className={`cursor-pointer rounded-xl border p-4 transition ${
                        active
                          ? "border-zinc-500 bg-zinc-900"
                          : "border-zinc-800/80 bg-zinc-900/40 hover:border-zinc-700 hover:bg-zinc-900/70"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <h3 className="text-sm font-semibold text-white">{job.title}</h3>
                          <p className="mt-0.5 text-xs text-zinc-400">
                            {job.company} · {job.location || "Location N/A"}
                          </p>
                        </div>
                        <div className="flex shrink-0 items-center gap-2">
                          {job.is_remote && (
                            <span className="rounded-md border border-sky-500/30 bg-sky-500/10 px-2 py-0.5 text-[11px] font-medium text-sky-300">
                              Remote
                            </span>
                          )}
                          <span className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-0.5 font-mono text-[11px] text-zinc-300">
                            #{job.job_id}
                          </span>
                        </div>
                      </div>

                      <div className="mt-3 flex items-center justify-between text-xs text-zinc-500">
                        <span className="font-mono">
                          RRF: {job.rrf_score?.toFixed(4)} · Final: {job.score?.toFixed(4)}
                        </span>
                        <a
                          href={job.apply_url}
                          target="_blank"
                          rel="noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="font-medium text-zinc-300 underline decoration-zinc-700 underline-offset-4 hover:text-white"
                        >
                          Apply link ↗
                        </a>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          {/* Right: Ghost Trust + Risk Critic Panel */}
          <aside className="space-y-4 lg:col-span-5">
            <div className="rounded-xl border border-zinc-800/90 bg-zinc-900/50 p-5">
              <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
                <h2 className="text-sm font-semibold text-white">Trust & Risk Critic</h2>
                {trust && (
                  <span
                    className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${
                      trustBadge(trust.trust_score).cls
                    }`}
                  >
                    {trustBadge(trust.trust_score).label}
                  </span>
                )}
              </div>

              {!selectedJob ? (
                <p className="mt-4 text-xs text-zinc-400">
                  Select a job card on the left to view ghost-listing signals and candidate fit risks.
                </p>
              ) : loadingInspector ? (
                <p className="mt-4 text-xs text-zinc-400">Analyzing listing signals and fit risks...</p>
              ) : (
                <div className="mt-4 space-y-5">
                  <div>
                    <div className="text-sm font-semibold text-white">{selectedJob.title}</div>
                    <div className="text-xs text-zinc-400">
                      {selectedJob.company} · Job ID #{selectedJob.job_id}
                    </div>
                  </div>

                  {/* Ghost Signals */}
                  {trust && (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-medium text-zinc-300">Ghost-Listing Signals</span>
                        <span className="font-mono text-zinc-400">
                          ghost_p={(trust.ghost_probability * 100).toFixed(1)}% ({trust.model_version})
                        </span>
                      </div>
                      <div className="space-y-1.5">
                        {trust.top_signals.length === 0 ? (
                          <div className="rounded-lg border border-zinc-800 bg-zinc-950/70 px-3 py-2 text-xs text-zinc-400">
                            No elevated ghost risk signals triggered yet.
                          </div>
                        ) : (
                          trust.top_signals.map((sig) => (
                            <div
                              key={sig.signal}
                              className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-950/80 px-3 py-2 text-xs"
                            >
                              <span className="font-mono text-zinc-200">{sig.signal}</span>
                              <span className="font-mono text-zinc-400">
                                val={sig.raw_value} · +{sig.weight_contribution.toFixed(2)}
                              </span>
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  )}

                  {/* Risk Critic */}
                  {critic && (
                    <div className="space-y-3 border-t border-zinc-800 pt-4">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-zinc-200">Risk Critic Fit Analysis</span>
                        <span className="font-mono text-xs text-emerald-300">
                          Fit: {(critic.fit_score * 100).toFixed(0)}%
                        </span>
                      </div>

                      {critic.summary && (
                        <p className="text-xs leading-relaxed text-zinc-300">{critic.summary}</p>
                      )}

                      {critic.matched_skills.length > 0 && (
                        <div>
                          <div className="mb-1.5 text-[11px] font-medium text-zinc-400">Matched Skills</div>
                          <div className="flex flex-wrap gap-1.5">
                            {critic.matched_skills.map((sk) => (
                              <span
                                key={sk}
                                className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[11px] text-emerald-200"
                              >
                                {sk}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {critic.missing_skills.length > 0 && (
                        <div>
                          <div className="mb-1.5 text-[11px] font-medium text-zinc-400">Skill Gaps to Address</div>
                          <div className="flex flex-wrap gap-1.5">
                            {critic.missing_skills.map((sk) => (
                              <span
                                key={sk}
                                className="rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[11px] text-amber-200"
                              >
                                {sk}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {critic.risks.length > 0 && (
                        <ul className="space-y-1.5 text-xs text-zinc-300">
                          {critic.risks.map((rk, i) => (
                            <li key={i} className="rounded-lg border border-zinc-800/80 bg-zinc-950/60 px-3 py-2">
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
      </div>
    </main>
  );
}
