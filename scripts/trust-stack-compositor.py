#!/usr/bin/env python3
"""
trust-stack-compositor.py — Unified trust score from the full tool stack.

Per santaclawd (2026-03-20): "the trust stack is almost complete."
  cold-start-trust.py: bootstrap
  correction-health-scorer.py: drift
  fork-probability-detector.py: contradiction

Composition: MIN() not weighted average.
Each tool catches a different attack vector. Failing ANY axis = failing trust.
Same principle as trust-axis-scorer: min(continuity, stake, reachability).

Additional signals:
- Shannon entropy (action type diversity)
- Pairwise oracle disagree rates (per santaclawd: names relationships not just aggregates)
- Evidence grade distribution
"""

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class ToolScore:
    """Score from one trust tool."""
    tool: str
    score: float  # 0-1
    confidence: float  # 0-1 (based on data quantity)
    flag: Optional[str]  # None = clean, else = warning


@dataclass
class CompositeAssessment:
    """Unified trust assessment from full stack."""
    agent_id: str
    tool_scores: list[ToolScore]
    composite_score: float  # min() of all tool scores
    composite_confidence: float  # min() of all confidences
    weakest_tool: str  # which tool is the bottleneck
    grade: str  # A|B|C|D|F
    flags: list[str]
    recommendation: str


def grade_from_score(score: float, confidence: float) -> str:
    """Letter grade incorporating both score and confidence."""
    if confidence < 0.3:
        return "I"  # Insufficient data
    if score >= 0.85:
        return "A"
    if score >= 0.70:
        return "B"
    if score >= 0.50:
        return "C"
    if score >= 0.30:
        return "D"
    return "F"


def compose_trust(
    agent_id: str,
    cold_start_phase: str,
    cold_start_ci: tuple[float, float],
    correction_health: float,  # 0-1, from correction-health-scorer
    correction_phase: str,  # HEALTHY|DEGRADING|SUSPICIOUS|OVERCORRECTING
    fork_probability: float,  # 0-1, from fork-probability-detector
    entropy_score: float,  # 0-1, normalized Shannon entropy
    evidence_grade_ratio: float,  # fraction chain-grade
    counterparty_diversity: int,  # unique counterparties
    receipt_count: int,
) -> CompositeAssessment:
    """Compose trust from full tool stack."""
    
    scores = []
    flags = []
    
    # Cold start score (CI midpoint, penalized by width)
    ci_width = cold_start_ci[1] - cold_start_ci[0]
    ci_mid = (cold_start_ci[0] + cold_start_ci[1]) / 2
    cold_confidence = max(0, 1 - ci_width)
    
    if cold_start_phase in ("GENESIS", "WARMING", "VELOCITY_SUSPECT"):
        cold_score = 0.0
        cold_confidence = 0.1
        flags.append(f"COLD_START: {cold_start_phase}")
    else:
        cold_score = ci_mid
    
    scores.append(ToolScore("cold-start-trust", cold_score, cold_confidence, 
                            cold_start_phase if cold_start_phase != "SCOREABLE" and cold_start_phase != "ESTABLISHED" else None))
    
    # Correction health
    corr_confidence = min(1.0, receipt_count / 50)  # confidence scales with data
    scores.append(ToolScore("correction-health", correction_health, corr_confidence,
                            correction_phase if correction_phase != "HEALTHY" else None))
    
    # Fork probability (invert: low fork_prob = good)
    fork_score = 1.0 - fork_probability
    fork_confidence = min(1.0, counterparty_diversity / 5)  # need diverse oracles
    if fork_probability > 0.3:
        flags.append(f"HIGH_FORK_PROB: {fork_probability:.2f}")
    scores.append(ToolScore("fork-probability", fork_score, fork_confidence,
                            "HIGH_FORK" if fork_probability > 0.3 else None))
    
    # Entropy (action diversity)
    entropy_confidence = min(1.0, receipt_count / 30)
    if entropy_score < 0.3 and receipt_count > 30:
        flags.append(f"LOW_ENTROPY: {entropy_score:.2f}")
    scores.append(ToolScore("entropy-diversity", entropy_score, entropy_confidence,
                            "LOW_ENTROPY" if entropy_score < 0.3 and receipt_count > 30 else None))
    
    # Evidence grade quality
    grade_confidence = min(1.0, receipt_count / 30)
    scores.append(ToolScore("evidence-grade", evidence_grade_ratio, grade_confidence, None))
    
    # Composite: MIN() — failing any axis = failing trust
    scored_tools = [s for s in scores if s.confidence >= 0.3]
    if len(scored_tools) < 3:  # need majority of stack to be confident
        composite = 0.0
        composite_conf = 0.0
        weakest = "ALL (insufficient data)"
    else:
        composite = min(s.score for s in scored_tools)
        composite_conf = min(s.confidence for s in scored_tools)
        weakest = min(scored_tools, key=lambda s: s.score).tool
    
    grade = grade_from_score(composite, composite_conf)
    
    # Recommendation
    if grade == "I":
        rec = "Insufficient data. Return uncertainty, not suspicion."
    elif grade == "A":
        rec = f"Strong trust. Weakest: {weakest}. Monitor for drift."
    elif grade in ("B", "C"):
        rec = f"Moderate trust. Bottleneck: {weakest}. {len(flags)} flags."
    else:
        rec = f"Low trust. Failing on: {weakest}. {', '.join(flags)}"
    
    return CompositeAssessment(
        agent_id=agent_id,
        tool_scores=scores,
        composite_score=composite,
        composite_confidence=composite_conf,
        weakest_tool=weakest,
        grade=grade,
        flags=flags,
        recommendation=rec,
    )


def demo():
    """Demo unified trust stack."""
    scenarios = [
        # (name, phase, ci, corr_health, corr_phase, fork_prob, entropy, evidence_ratio, counterparties, receipts)
        ("kit_fox", "ESTABLISHED", (0.92, 0.96), 0.88, "HEALTHY", 0.05, 0.76, 0.69, 30, 500),
        ("new_agent", "WARMING", (0.44, 1.0), 0.50, "HEALTHY", 0.10, 0.40, 0.30, 2, 5),
        ("hiding_drift", "SCOREABLE", (0.80, 0.95), 0.20, "SUSPICIOUS", 0.08, 0.65, 0.50, 12, 80),
        ("equivocator", "SCOREABLE", (0.75, 0.92), 0.70, "HEALTHY", 0.55, 0.60, 0.40, 8, 60),
        ("monoculture", "SCOREABLE", (0.78, 0.96), 0.75, "HEALTHY", 0.03, 0.08, 0.60, 10, 50),
        ("sybil_burst", "VELOCITY_SUSPECT", (0.98, 1.0), 1.00, "HEALTHY", 0.00, 0.05, 0.10, 1, 200),
        ("bro_agent", "ESTABLISHED", (0.93, 0.97), 0.90, "HEALTHY", 0.03, 0.82, 0.85, 25, 450),
    ]
    
    print("=" * 75)
    print("UNIFIED TRUST STACK ASSESSMENT")
    print("=" * 75)
    print(f"{'Agent':<16} {'Grade':>5} {'Score':>6} {'Conf':>5} {'Weakest':<22} {'Flags':>5}")
    print("-" * 75)
    
    for name, phase, ci, ch, cp, fp, ent, evr, cps, rc in scenarios:
        result = compose_trust(name, phase, ci, ch, cp, fp, ent, evr, cps, rc)
        print(f"{name:<16} {result.grade:>5} {result.composite_score:>6.2f} {result.composite_confidence:>5.2f} {result.weakest_tool:<22} {len(result.flags):>5}")
    
    print()
    print("DETAILED ASSESSMENTS:")
    print("-" * 75)
    
    for name, phase, ci, ch, cp, fp, ent, evr, cps, rc in scenarios:
        result = compose_trust(name, phase, ci, ch, cp, fp, ent, evr, cps, rc)
        print(f"\n  {name} (Grade {result.grade}):")
        for ts in result.tool_scores:
            flag = f" ⚠️ {ts.flag}" if ts.flag else ""
            conf_bar = "▓" * int(ts.confidence * 10) + "░" * (10 - int(ts.confidence * 10))
            print(f"    {ts.tool:<22} {ts.score:>5.2f} [{conf_bar}]{flag}")
        if result.flags:
            print(f"    FLAGS: {', '.join(result.flags)}")
        print(f"    → {result.recommendation}")
    
    print()
    print("COMPOSITION: min(tool_scores) — failing ANY axis = failing trust.")
    print("Per santaclawd: each tool is a lens, none sufficient alone.")


if __name__ == "__main__":
    demo()
