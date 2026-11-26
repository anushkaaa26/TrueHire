"use client";

import { useState } from "react";

interface JobResult {
  job_id: number;
  title: string;
  company: string;
  location: string | null;
  is_remote: boolean;
  apply_url: string;
  rrf_score: number;
  score: number;
}

interface TrustPayload {
  job_id: number;
  ghost_probability: number;
  trust_score: number;
  top_signals: { signal: string; weight_contribution: number; raw_value: number }[];
}

export default function Home() {
  const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const [query, setQuery] = useState("Backend Python FastAPI engineer");
  const [skills, setSkills] = useState("python, fastapi, postgresql, docker");
  const [jobs, setJobs] = useState<JobResult[]>([]);
  const [trustMap, setTrustMap] = useState<Record<number, TrustPayload>>({});
  const [status, setStatus] = useState<string>("Ready");
  const [loading, setLoading] = useState(false);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setStatus("Running hybrid BM25 + pgvector search...");
    try {
      const res = await fetch(`${apiBase}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: query,
          skills: skills.split(",").map((s) => s.trim()).filter(Boolean),
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setJobs(data.jobs || []);
      setStatus(data.reply || "Done");
    } catch (err) {
      setStatus(`Error: ${err instanceof Error ? err.message : "Failed to reach API"}`);
    } finally {
      setLoading(false);
    }
  }

  async function inspectTrust(jobId: number) {
    try {
      const res = await fetch(`${apiBase}/jobs/${jobId}/trust`);
      if (!res.ok) return;
      const data: TrustPayload = await res.json();
      setTrustMap((prev) => ({ ...prev, [jobId]: data }));
    } catch {
      // ignore transient network errors
    }
  }

  function badgeStyle(trustScore: number) {
    if (trustScore >= 0.75) return "border-emerald-500/40 bg-emerald-500/10 text-emerald-300";
    if (trustScore >= 0.5) return "border-amber-500/40 bg-amber-500/10 text-amber-300";
    return "border-rose-500/40 bg-rose-500/10 text-rose-300";
  }

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100 px-6 py-10">
      <div className="max-w-4xl mx-auto space-y-8">
        <header className="border-b border-zinc-800 pb-6 flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <h1 className="text-2xl font-semibold tracking-tight text-white">TrueHire</h1>
            <span className="text-xs font-mono px-2.5 py-1 rounded border border-zinc-800 bg-zinc-900 text-zinc-400">
              Grounded Hybrid Search + Ghost-Job Trust
            </span>
          </div>
          <p className="text-sm text-zinc-400">
            Daily-snapshotted ATS listings scored with lifecycle signals and SQL Reciprocal Rank Fusion.
          </p>
        </header>

        <form onSubmit={handleSearch} className="space-y-3 bg-zinc-900/60 border border-zinc-800 rounded-xl p-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Role, stack, or location..."
              className="md:col-span-2 bg-zinc-950 border border-zinc-800 rounded-lg px-3.5 py-2 text-sm text-zinc-100 focus:outline-none focus:border-zinc-600"
            />
            <input
              value={skills}
              onChange={(e) => setSkills(e.target.value)}
              placeholder="Skills (comma-separated)"
              className="bg-zinc-950 border border-zinc-800 rounded-lg px-3.5 py-2 text-sm text-zinc-100 focus:outline-none focus:border-zinc-600"
            />
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-zinc-400">{status}</span>
            <button
              type="submit"
              disabled={loading}
              className="px-4 py-2 rounded-lg bg-white text-zinc-950 text-sm font-medium hover:bg-zinc-200 disabled:opacity-50 transition"
            >
              {loading ? "Searching..." : "Search Grounded Roles"}
            </button>
          </div>
        </form>

        <section className="space-y-3">
          {jobs.map((job) => {
            const trust = trustMap[job.job_id];
            return (
              <article
                key={job.job_id}
                className="border border-zinc-800 bg-zinc-900/40 rounded-xl p-5 flex flex-col gap-3"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <h2 className="text-base font-medium text-white">{job.title}</h2>
                      <span className="text-xs font-mono text-zinc-500">#{job.job_id}</span>
                    </div>
                    <p className="text-sm text-zinc-400 mt-0.5">
                      {job.company} · {job.location || "Unspecified"} {job.is_remote ? "· Remote" : ""}
                    </p>
                  </div>

                  <div className="flex items-center gap-2">
                    {trust ? (
                      <span className={`text-xs font-mono px-2.5 py-1 rounded border ${badgeStyle(trust.trust_score)}`}>
                        Trust {(trust.trust_score * 100).toFixed(0)}%
                      </span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => inspectTrust(job.job_id)}
                        className="text-xs font-mono px-2.5 py-1 rounded border border-zinc-700 bg-zinc-900 text-zinc-300 hover:border-zinc-500"
                      >
                        Check Trust Score
                      </button>
                    )}
                    {job.apply_url && (
                      <a
                        href={job.apply_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-xs font-medium px-3 py-1 rounded bg-zinc-800 text-zinc-100 hover:bg-zinc-700"
                      >
                        Apply ↗
                      </a>
                    )}
                  </div>
                </div>

                {trust && trust.top_signals.length > 0 && (
                  <div className="text-xs font-mono text-zinc-400 border-t border-zinc-800/80 pt-2.5 flex flex-wrap gap-2">
                    <span className="text-zinc-500">Top risk signals:</span>
                    {trust.top_signals.map((s) => (
                      <span key={s.signal} className="px-2 py-0.5 rounded bg-zinc-950 border border-zinc-800">
                        {s.signal}: {s.raw_value}
                      </span>
                    ))}
                  </div>
                )}
              </article>
            );
          })}
        </section>
      </div>
    </main>
  );
}
