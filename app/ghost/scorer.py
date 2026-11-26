import math
from dataclasses import dataclass

MODEL_VERSION = "rules_v1"

WEIGHTS: dict[str, float] = {
    "reposts_90d": 0.65,
    "days_vs_median_ratio": 0.45,
    "stale_no_edits": 0.40,
    "high_boilerplate_peers": 0.55,
    "cross_board_duplicates": 0.30,
    "low_specificity": 0.45,
}

BIAS = -1.60


@dataclass
class GhostAssessment:
    probability: float
    trust_score: float
    signals: list[dict[str, float | str]]
    model_version: str = MODEL_VERSION


def score_features(features: dict[str, float]) -> GhostAssessment:
    low_spec = 1.0 if features.get("specificity_count", 0.0) < 3.0 else 0.0
    normalized = {
        "reposts_90d": min(features.get("reposts_90d", 0.0), 4.0) / 4.0,
        "days_vs_median_ratio": min(max(features.get("days_vs_median_ratio", 0.0) - 1.0, 0.0), 3.0) / 3.0,
        "stale_no_edits": features.get("stale_no_edits", 0.0),
        "high_boilerplate_peers": min(features.get("high_boilerplate_peers", 0.0), 3.0) / 3.0,
        "cross_board_duplicates": min(features.get("cross_board_duplicates", 0.0), 3.0) / 3.0,
        "low_specificity": low_spec,
    }

    contributions: list[tuple[str, float]] = []
    logit = BIAS
    for key, w in WEIGHTS.items():
        val = normalized.get(key, 0.0)
        contrib = w * val
        logit += contrib
        if contrib > 0.0:
            contributions.append((key, round(contrib, 4)))

    prob = 1.0 / (1.0 + math.exp(-logit))
    trust = round(1.0 - prob, 4)
    contributions.sort(key=lambda item: item[1], reverse=True)

    top_signals = [
        {"signal": name, "weight_contribution": impact, "raw_value": features.get(name, low_spec if name == "low_specificity" else 0.0)}
        for name, impact in contributions[:3]
    ]

    return GhostAssessment(
        probability=round(prob, 4),
        trust_score=trust,
        signals=top_signals,
        model_version=MODEL_VERSION,
    )
