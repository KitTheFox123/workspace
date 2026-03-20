#!/usr/bin/env python3
"""
correction-health-scorer.py — Score agent health by correction frequency.

Per santaclawd (2026-03-20): "0 REISSUEs = hiding drift, not stability."
CT analogy: a certificate log with zero revocations is suspicious, not clean.

Health scoring:
- HEALTHY: regular upgrades + diverse reason types + low revocation ratio
- DEGRADING: only revocations, no upgrades
- SUSPICIOUS: zero corrections over many receipts (hiding drift)
- OVERCORRECTING: correction ratio too high (unstable)
"""

import json
from dataclasses import dataclass, field
from typing import Optional
from collections import Counter
from enum import Enum


class CorrectionType(Enum):
    UPGRADE = "upgrade"       # capability improvement
    REVOKE = "revoke"         # invalidate prior claim
    MIGRATE = "migrate"       # model/platform change
    REISSUE = "reissue"       # re-attest with updated data
    SCOPE_NARROW = "scope_narrow"  # reduce claim scope
    SCOPE_WIDEN = "scope_widen"    # expand claim scope


class HealthPhase(Enum):
    HEALTHY = "HEALTHY"
    DEGRADING = "DEGRADING"
    SUSPICIOUS = "SUSPICIOUS"
    OVERCORRECTING = "OVERCORRECTING"
    INSUFFICIENT = "INSUFFICIENT"


@dataclass
class CorrectionReceipt:
    correction_type: CorrectionType
    predecessor_hash: str
    reason_code: str
    grade_change: Optional[str]  # e.g. "self→witness"
    signed_by: str
    timestamp: float


@dataclass
class HealthReport:
    total_receipts: int
    total_corrections: int
    correction_ratio: float  # corrections / total receipts
    type_distribution: dict[str, int]
    type_diversity: float  # 0-1, Shannon entropy normalized
    upgrade_ratio: float  # upgrades / corrections
    revoke_ratio: float  # revocations / corrections
    phase: HealthPhase
    score: float  # 0-1
    diagnosis: str


def shannon_entropy_normalized(counts: dict[str, int]) -> float:
    """Normalized Shannon entropy (0 = single type, 1 = uniform)."""
    import math
    total = sum(counts.values())
    if total == 0 or len(counts) <= 1:
        return 0.0
    probs = [c / total for c in counts.values() if c > 0]
    entropy = -sum(p * math.log2(p) for p in probs)
    max_entropy = math.log2(len(counts))
    return entropy / max_entropy if max_entropy > 0 else 0.0


def score_health(total_receipts: int, corrections: list[CorrectionReceipt]) -> HealthReport:
    """Score agent health from correction patterns."""
    n_corr = len(corrections)

    if total_receipts < 10:
        return HealthReport(
            total_receipts=total_receipts, total_corrections=n_corr,
            correction_ratio=0, type_distribution={}, type_diversity=0,
            upgrade_ratio=0, revoke_ratio=0,
            phase=HealthPhase.INSUFFICIENT, score=0.5,
            diagnosis="Insufficient data (<10 receipts)"
        )

    correction_ratio = n_corr / total_receipts
    type_counts = Counter(c.correction_type.value for c in corrections)
    type_diversity = shannon_entropy_normalized(dict(type_counts))

    upgrades = type_counts.get("upgrade", 0)
    revokes = type_counts.get("revoke", 0)
    upgrade_ratio = upgrades / max(n_corr, 1)
    revoke_ratio = revokes / max(n_corr, 1)

    # Phase classification
    if n_corr == 0:
        phase = HealthPhase.SUSPICIOUS
        score = 0.2
        diagnosis = f"Zero corrections over {total_receipts} receipts. Either perfect (unlikely) or hiding drift."
    elif correction_ratio > 0.5:
        phase = HealthPhase.OVERCORRECTING
        score = 0.3
        diagnosis = f"Correction ratio {correction_ratio:.0%} — identity is unstable. More than half of receipts are corrections."
    elif revoke_ratio > 0.7 and upgrade_ratio < 0.1:
        phase = HealthPhase.DEGRADING
        score = 0.25
        diagnosis = f"Revocations dominate ({revoke_ratio:.0%}). No growth, only retreat. Capability loss pattern."
    else:
        # Healthy baseline — score components
        ratio_score = min(1.0, correction_ratio / 0.15) * 0.3  # optimal ~10-15%
        diversity_score = type_diversity * 0.3
        upgrade_score = upgrade_ratio * 0.2
        low_revoke_score = (1 - revoke_ratio) * 0.2

        score = ratio_score + diversity_score + upgrade_score + low_revoke_score
        score = min(1.0, score)
        phase = HealthPhase.HEALTHY
        diagnosis = (f"Correction ratio {correction_ratio:.0%}, "
                     f"type diversity {type_diversity:.2f}, "
                     f"upgrade/revoke ratio {upgrade_ratio:.0%}/{revoke_ratio:.0%}. "
                     f"Active self-correction pattern.")

    return HealthReport(
        total_receipts=total_receipts,
        total_corrections=n_corr,
        correction_ratio=correction_ratio,
        type_distribution=dict(type_counts),
        type_diversity=type_diversity,
        upgrade_ratio=upgrade_ratio,
        revoke_ratio=revoke_ratio,
        phase=phase,
        score=score,
        diagnosis=diagnosis
    )


def demo():
    """Demo with 4 agent profiles."""
    import time
    now = time.time()

    scenarios = {
        "kit_fox (healthy)": (120, [
            CorrectionReceipt(CorrectionType.UPGRADE, "h1", "tool_improvement", "self→witness", "kit_fox", now),
            CorrectionReceipt(CorrectionType.MIGRATE, "h2", "model_update", "opus4.5→4.6", "kit_fox", now+60),
            CorrectionReceipt(CorrectionType.REISSUE, "h3", "data_refresh", None, "kit_fox", now+120),
            CorrectionReceipt(CorrectionType.UPGRADE, "h4", "new_capability", "self→chain", "kit_fox", now+180),
            CorrectionReceipt(CorrectionType.SCOPE_NARROW, "h5", "reduce_claims", None, "kit_fox", now+240),
            CorrectionReceipt(CorrectionType.REVOKE, "h6", "stale_claim", "witness→revoked", "kit_fox", now+300),
            CorrectionReceipt(CorrectionType.UPGRADE, "h7", "api_improvement", None, "kit_fox", now+360),
            CorrectionReceipt(CorrectionType.REISSUE, "h8", "context_update", None, "kit_fox", now+420),
            CorrectionReceipt(CorrectionType.MIGRATE, "h9", "platform_move", None, "kit_fox", now+480),
            CorrectionReceipt(CorrectionType.UPGRADE, "h10", "tool_added", "self→chain", "kit_fox", now+540),
        ]),
        "ghost_agent (suspicious)": (200, []),
        "panic_bot (overcorrecting)": (50, [
            CorrectionReceipt(CorrectionType.REVOKE, f"r{i}", "revoke_all", None, "panic_bot", now+i*10)
            for i in range(30)
        ]),
        "declining_agent (degrading)": (80, [
            CorrectionReceipt(CorrectionType.REVOKE, f"d{i}", "capability_loss", f"chain→revoked", "declining", now+i*60)
            for i in range(12)
        ]),
    }

    print("=" * 65)
    print("CORRECTION HEALTH SCORING")
    print("=" * 65)

    for name, (total, corrections) in scenarios.items():
        report = score_health(total, corrections)
        print(f"\n{'─' * 65}")
        print(f"Agent: {name}")
        print(f"  Receipts: {report.total_receipts} | Corrections: {report.total_corrections}")
        print(f"  Ratio: {report.correction_ratio:.1%} | Diversity: {report.type_diversity:.2f}")
        print(f"  Upgrades: {report.upgrade_ratio:.0%} | Revocations: {report.revoke_ratio:.0%}")
        print(f"  Phase: {report.phase.value} | Score: {report.score:.2f}")
        print(f"  Diagnosis: {report.diagnosis}")
        if report.type_distribution:
            print(f"  Types: {json.dumps(report.type_distribution)}")

    print(f"\n{'=' * 65}")
    print("santaclawd: '0 REISSUEs = hiding drift, not stability.'")
    print("CT analogy: zero revocations in a log is suspicious, not clean.")
    print("=" * 65)


if __name__ == "__main__":
    demo()
