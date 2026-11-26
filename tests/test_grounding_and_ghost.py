from app.agent.grounding import enforce_grounded_ids
from app.agent.risk_critic import extract_required_skills
from app.ghost.scorer import score_features
from app.ingestion.schemas import NormalizedJob
from app.retrieval.queries import COMPANY_MEDIAN_DAYS_OPEN_SQL, REPOSTS_90D_SQL, RRF_HYBRID_SEARCH_SQL


def test_grounding_rejects_unseen_job_ids() -> None:
    grounded, rejected = enforce_grounded_ids([101, 999, 102, 101], {101, 102, 103})
    assert grounded == [101, 102]
    assert rejected == [999]


def test_ghost_scorer_outputs_signals_and_bounds() -> None:
    high_risk = score_features(
        {
            "reposts_90d": 4.0,
            "days_vs_median_ratio": 3.2,
            "stale_no_edits": 1.0,
            "specificity_count": 1.0,
            "high_boilerplate_peers": 3.0,
            "cross_board_duplicates": 2.0,
        }
    )
    low_risk = score_features(
        {
            "reposts_90d": 0.0,
            "days_vs_median_ratio": 0.5,
            "stale_no_edits": 0.0,
            "specificity_count": 14.0,
            "high_boilerplate_peers": 0.0,
            "cross_board_duplicates": 0.0,
        }
    )
    assert 0.0 <= high_risk.probability <= 1.0
    assert 0.0 <= low_risk.probability <= 1.0
    assert high_risk.probability > low_risk.probability
    assert len(high_risk.signals) >= 1


def test_content_hash_and_skill_extraction() -> None:
    j1 = NormalizedJob(
        external_id="1",
        source="greenhouse",
        title="Backend Engineer",
        location="Bengaluru, India",
        is_remote=False,
        description="<p>Build Python, FastAPI, and PostgreSQL services.</p>",
        apply_url="https://example.com/1",
    )
    j2 = NormalizedJob(
        external_id="1",
        source="greenhouse",
        title="Backend Engineer",
        location="Bengaluru, India",
        is_remote=False,
        description="Build Python, FastAPI, and PostgreSQL services.",
        apply_url="https://example.com/1",
    )
    assert j1.content_hash == j2.content_hash
    skills = extract_required_skills(j1.description)
    assert {"python", "fastapi", "postgresql"}.issubset(set(skills))


def test_sql_showcase_queries_present() -> None:
    assert "percentile_cont" in COMPANY_MEDIAN_DAYS_OPEN_SQL
    assert "reappeared" in REPOSTS_90D_SQL
    assert "rrf_score" in RRF_HYBRID_SEARCH_SQL
