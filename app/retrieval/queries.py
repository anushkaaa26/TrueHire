REPOSTS_90D_SQL = """
SELECT
    j.id AS job_id,
    c.name AS company,
    j.title,
    COUNT(*) FILTER (
        WHERE e.event_type IN ('reappeared', 'appeared')
          AND e.at >= NOW() - INTERVAL '90 days'
    ) AS events_90d,
    COUNT(*) FILTER (
        WHERE e.event_type = 'reappeared'
          AND e.at >= NOW() - INTERVAL '90 days'
    ) AS reposts_90d,
    SUM(COUNT(*)) OVER (PARTITION BY j.company_id) AS company_events_90d
FROM jobs j
JOIN companies c ON c.id = j.company_id
LEFT JOIN job_events e ON e.job_id = j.id
GROUP BY j.id, c.name, j.title, j.company_id
ORDER BY reposts_90d DESC, events_90d DESC
"""

COMPANY_MEDIAN_DAYS_OPEN_SQL = """
WITH job_durations AS (
    SELECT
        c.id AS company_id,
        c.name AS company,
        GREATEST((j.last_seen - j.first_seen), 1)::numeric AS days_open
    FROM jobs j
    JOIN companies c ON c.id = j.company_id
)
SELECT
    company_id,
    company,
    COUNT(*) AS total_jobs,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY days_open) AS median_days_open,
    percentile_cont(0.9) WITHIN GROUP (ORDER BY days_open) AS p90_days_open
FROM job_durations
GROUP BY company_id, company
ORDER BY median_days_open DESC
"""

RRF_HYBRID_SEARCH_SQL = """
WITH bm25_ranked AS (
    SELECT
        j.id,
        ROW_NUMBER() OVER (ORDER BY ts_rank_cd(j.tsv, websearch_to_tsquery('english', $1)) DESC) AS rank_ix
    FROM jobs j
    WHERE j.is_active = TRUE
      AND j.tsv @@ websearch_to_tsquery('english', $1)
    ORDER BY ts_rank_cd(j.tsv, websearch_to_tsquery('english', $1)) DESC
    LIMIT 50
),
dense_ranked AS (
    SELECT
        j.id,
        ROW_NUMBER() OVER (ORDER BY j.embedding <=> $2::vector ASC) AS rank_ix
    FROM jobs j
    WHERE j.is_active = TRUE
      AND j.embedding IS NOT NULL
    ORDER BY j.embedding <=> $2::vector ASC
    LIMIT 50
),
rrf AS (
    SELECT
        COALESCE(b.id, d.id) AS job_id,
        COALESCE(1.0 / ($3::float + b.rank_ix), 0.0) +
        COALESCE(1.0 / ($3::float + d.rank_ix), 0.0) AS rrf_score
    FROM bm25_ranked b
    FULL OUTER JOIN dense_ranked d ON b.id = d.id
)
SELECT
    j.id,
    j.title,
    c.name AS company,
    j.location,
    j.is_remote,
    j.apply_url,
    rrf.rrf_score
FROM rrf
JOIN jobs j ON j.id = rrf.job_id
JOIN companies c ON c.id = j.company_id
ORDER BY rrf.rrf_score DESC
LIMIT $4
"""
