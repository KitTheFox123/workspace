#!/usr/bin/env python3
"""
decision-fatigue-auditor.py — Audit agent decision sequences for fatigue patterns.

Based on Andersson et al. (2025, Nature Comms Psych, s44271-025-00207-8):
Registered Report with n=231,076 medical judgments found NO EVIDENCE for decision
fatigue (BF0+ > 22 for all main tests). The "hungry judge" effect (Danziger 2011)
likely reflects scheduling confounds, not depletion.

Key insight: Decision fatigue as a domain-general effect may not exist. What DOES
exist: opportunity cost of effort (Kurzban 2013), rational inattention (Matějka &
McKay 2015), and scheduling confounds mistaken for fatigue.

Audits agent heartbeat/attestation sequences for:
1. Default convergence — are later decisions more like personal defaults?
2. Urgency drift — do risk ratings shift with sequence position?
3. Call duration shift — do processing times change?
4. Break recovery — does a break actually change behavior?

If patterns emerge, they may reflect rational effort allocation, not "depletion."

References:
- Andersson et al. (2025, Comms Psych, Registered Report, n=231,076): No evidence
  for decision fatigue in healthcare. BF0+ > 22 for ALL main tests. Quasi-experimental.
- Danziger, Levav & Avnaim-Pesso (2011, PNAS): "Hungry judge" effect. Criticized by
  Glöckner (2016), Daljord et al. (2017) — magnitude overestimated, scheduling confounds.
- Kurzban et al. (2013, BBS 36:661-679): Opportunity cost model. Mental effort = signal
  of better alternatives, not resource depletion.
- Matějka & McKay (2015, AER 105:272-298): Rational inattention — choices converge to
  priors when info cost rises. Not fatigue, just economics.
"""

import hashlib
import json
import random
import statistics
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Decision:
    """A single decision in a sequence."""
    seq_position: int
    choice: str  # The decision made
    urgency: float  # 0-4 scale
    processing_time_s: float  # How long the decision took
    post_break: bool = False  # Was this right after a break?
    timestamp_h: float = 0.0  # Hours into shift


@dataclass 
class AgentShift:
    """A sequence of decisions (one heartbeat cycle or work session)."""
    agent_id: str
    decisions: list[Decision] = field(default_factory=list)
    break_positions: list[int] = field(default_factory=list)  # Indices where breaks occurred


def compute_personal_default(choices: list[str]) -> str:
    """Modal choice = personal default."""
    from collections import Counter
    if not choices:
        return ""
    counts = Counter(choices)
    return counts.most_common(1)[0][0]


def default_convergence_score(shift: AgentShift) -> dict:
    """
    Test H1: Do later decisions converge toward personal defaults?
    
    Andersson et al. found BF0+ > 22 AGAINST this — no convergence with fatigue.
    If we find convergence, it may reflect rational inattention, not depletion.
    """
    if len(shift.decisions) < 6:
        return {"error": "insufficient_decisions", "min_required": 6}
    
    all_choices = [d.choice for d in shift.decisions]
    default = compute_personal_default(all_choices)
    
    # Split into first half and second half
    mid = len(shift.decisions) // 2
    first_half = shift.decisions[:mid]
    second_half = shift.decisions[mid:]
    
    first_default_rate = sum(1 for d in first_half if d.choice == default) / len(first_half)
    second_default_rate = sum(1 for d in second_half if d.choice == default) / len(second_half)
    
    convergence = second_default_rate - first_default_rate
    
    return {
        "personal_default": default,
        "first_half_default_rate": round(first_default_rate, 3),
        "second_half_default_rate": round(second_default_rate, 3),
        "convergence": round(convergence, 3),
        "interpretation": (
            "CONVERGING — but Andersson (2025) says this isn't fatigue, "
            "it's rational inattention (Matějka & McKay 2015)"
            if convergence > 0.1
            else "NO_CONVERGENCE — consistent with Andersson null finding"
            if abs(convergence) <= 0.1
            else "DIVERGING — opposite of fatigue prediction"
        )
    }


def urgency_drift_score(shift: AgentShift) -> dict:
    """
    Test H2: Do urgency ratings drift upward with sequence position?
    
    Andersson: BF0+ > 45 against drift in pilot, > 22 in confirmatory.
    """
    if len(shift.decisions) < 6:
        return {"error": "insufficient_decisions"}
    
    mid = len(shift.decisions) // 2
    first_urgency = [d.urgency for d in shift.decisions[:mid]]
    second_urgency = [d.urgency for d in shift.decisions[mid:]]
    
    first_mean = statistics.mean(first_urgency)
    second_mean = statistics.mean(second_urgency)
    drift = second_mean - first_mean
    
    # Cohen's d approximation
    pooled = first_urgency + second_urgency
    if statistics.stdev(pooled) > 0:
        cohens_d = drift / statistics.stdev(pooled)
    else:
        cohens_d = 0.0
    
    return {
        "first_half_mean_urgency": round(first_mean, 3),
        "second_half_mean_urgency": round(second_mean, 3),
        "drift": round(drift, 3),
        "cohens_d": round(cohens_d, 3),
        "interpretation": (
            f"d={cohens_d:.2f} — Andersson targeted d=0.20 and found nothing. "
            f"{'DRIFT_DETECTED' if abs(cohens_d) > 0.20 else 'NO_MEANINGFUL_DRIFT'}"
        )
    }


def processing_time_analysis(shift: AgentShift) -> dict:
    """
    Exploratory: Does processing time change with position?
    
    Andersson noted this is ambiguous — could go either way.
    Shorter = less info gathered (fatigue). Longer = slower processing (tiredness).
    """
    if len(shift.decisions) < 6:
        return {"error": "insufficient_decisions"}
    
    mid = len(shift.decisions) // 2
    first_times = [d.processing_time_s for d in shift.decisions[:mid]]
    second_times = [d.processing_time_s for d in shift.decisions[mid:]]
    
    first_mean = statistics.mean(first_times)
    second_mean = statistics.mean(second_times)
    change_pct = ((second_mean - first_mean) / first_mean * 100) if first_mean > 0 else 0
    
    return {
        "first_half_mean_time_s": round(first_mean, 1),
        "second_half_mean_time_s": round(second_mean, 1),
        "change_pct": round(change_pct, 1),
        "interpretation": (
            "SHORTER — less info gathered (rational inattention) or more efficient"
            if change_pct < -10
            else "LONGER — slower processing but NOT necessarily worse"
            if change_pct > 10
            else "STABLE — no processing time drift"
        )
    }


def break_recovery_analysis(shift: AgentShift) -> dict:
    """
    Test break effect: Does behavior change after breaks?
    
    Andersson: BF0+ > 22 against break effects in confirmatory data.
    The "hungry judge" pattern may be scheduling, not recovery.
    """
    pre_break = []
    post_break = []
    
    for i, d in enumerate(shift.decisions):
        if d.post_break:
            post_break.append(d)
            # Get the decision before the break
            if i > 0 and not shift.decisions[i-1].post_break:
                pre_break.append(shift.decisions[i-1])
    
    if len(pre_break) < 2 or len(post_break) < 2:
        return {"error": "insufficient_break_data"}
    
    pre_urgency = statistics.mean([d.urgency for d in pre_break])
    post_urgency = statistics.mean([d.urgency for d in post_break])
    
    pre_time = statistics.mean([d.processing_time_s for d in pre_break])
    post_time = statistics.mean([d.processing_time_s for d in post_break])
    
    return {
        "pre_break_urgency": round(pre_urgency, 3),
        "post_break_urgency": round(post_urgency, 3),
        "urgency_change": round(post_urgency - pre_urgency, 3),
        "pre_break_time_s": round(pre_time, 1),
        "post_break_time_s": round(post_time, 1),
        "time_change_pct": round((post_time - pre_time) / pre_time * 100, 1) if pre_time > 0 else 0,
        "interpretation": (
            "Andersson (2025): breaks DON'T reset decision quality. "
            "If you see a pattern, check for scheduling confounds first."
        )
    }


def audit_shift(shift: AgentShift) -> dict:
    """Full decision fatigue audit for one shift."""
    results = {
        "agent": shift.agent_id,
        "n_decisions": len(shift.decisions),
        "n_breaks": len(shift.break_positions),
        "default_convergence": default_convergence_score(shift),
        "urgency_drift": urgency_drift_score(shift),
        "processing_time": processing_time_analysis(shift),
        "break_recovery": break_recovery_analysis(shift),
    }
    
    # Overall assessment
    signals = []
    dc = results["default_convergence"]
    if isinstance(dc.get("convergence"), (int, float)) and dc["convergence"] > 0.1:
        signals.append("default_convergence")
    ud = results["urgency_drift"]
    if isinstance(ud.get("cohens_d"), (int, float)) and abs(ud["cohens_d"]) > 0.20:
        signals.append("urgency_drift")
    pt = results["processing_time"]
    if isinstance(pt.get("change_pct"), (int, float)) and abs(pt["change_pct"]) > 10:
        signals.append("processing_time_shift")
    
    results["fatigue_signals"] = len(signals)
    results["triggered_signals"] = signals
    results["overall"] = (
        "NO_FATIGUE_DETECTED — consistent with Andersson (2025) null finding"
        if len(signals) == 0
        else f"POSSIBLE_PATTERN ({len(signals)} signals) — but remember: Andersson found "
        f"BF0+ > 22 against fatigue with n=231,076. Check for confounds before concluding fatigue."
    )
    
    return results


def simulate_demo():
    """Demo with simulated heartbeat decisions."""
    random.seed(42)
    
    print("=" * 70)
    print("DECISION FATIGUE AUDITOR")
    print("Based on Andersson et al. (2025, Nature Comms Psych)")
    print("Registered Report, n=231,076: NO evidence for decision fatigue")
    print("=" * 70)
    
    # Scenario 1: Kit's heartbeat cycle (honest agent, no fatigue)
    kit_decisions = []
    choices = ["engage", "research", "build", "skip", "engage"]
    for i in range(20):
        kit_decisions.append(Decision(
            seq_position=i,
            choice=random.choice(choices),
            urgency=random.gauss(2.0, 0.8),  # Stable urgency
            processing_time_s=random.gauss(45, 15),
            post_break=(i in [5, 10, 15]),
            timestamp_h=i * 0.5
        ))
    
    kit_shift = AgentShift(agent_id="Kit", decisions=kit_decisions, break_positions=[5, 10, 15])
    kit_result = audit_shift(kit_shift)
    
    print(f"\n{'─' * 50}")
    print(f"Agent: {kit_result['agent']} (20 heartbeat decisions)")
    print(f"Fatigue signals: {kit_result['fatigue_signals']}")
    print(f"Overall: {kit_result['overall']}")
    print(f"\nDefault convergence: {kit_result['default_convergence']['convergence']}")
    print(f"  → {kit_result['default_convergence']['interpretation']}")
    print(f"Urgency drift d: {kit_result['urgency_drift']['cohens_d']}")
    print(f"  → {kit_result['urgency_drift']['interpretation']}")
    print(f"Processing time change: {kit_result['processing_time']['change_pct']}%")
    print(f"  → {kit_result['processing_time']['interpretation']}")
    
    # Scenario 2: Agent showing "fatigue" pattern (but is it really?)
    fatigued_decisions = []
    default_choice = "approve"
    for i in range(20):
        # Gradually converge to default
        if random.random() < 0.3 + (i / 20) * 0.5:
            choice = default_choice
        else:
            choice = random.choice(["reject", "defer", "escalate"])
        
        fatigued_decisions.append(Decision(
            seq_position=i,
            choice=choice,
            urgency=2.0 + i * 0.05 + random.gauss(0, 0.3),  # Drift up
            processing_time_s=max(10, 60 - i * 1.5 + random.gauss(0, 5)),  # Get faster
            post_break=(i in [10]),
            timestamp_h=i * 0.5
        ))
    
    fatigued_shift = AgentShift(agent_id="FatigueBot", decisions=fatigued_decisions, break_positions=[10])
    fatigued_result = audit_shift(fatigued_shift)
    
    print(f"\n{'─' * 50}")
    print(f"Agent: {fatigued_result['agent']} (20 sequential attestations)")
    print(f"Fatigue signals: {fatigued_result['fatigue_signals']}")
    print(f"Triggered: {fatigued_result['triggered_signals']}")
    print(f"Overall: {fatigued_result['overall']}")
    print(f"\nDefault convergence: {fatigued_result['default_convergence']['convergence']}")
    print(f"  → {fatigued_result['default_convergence']['interpretation']}")
    print(f"Urgency drift d: {fatigued_result['urgency_drift']['cohens_d']}")
    print(f"  → {fatigued_result['urgency_drift']['interpretation']}")
    print(f"Processing time change: {fatigued_result['processing_time']['change_pct']}%")
    print(f"  → {fatigued_result['processing_time']['interpretation']}")
    
    # The lesson
    print(f"\n{'=' * 70}")
    print("KEY FINDING: Andersson et al. (2025)")
    print("─" * 70)
    print("• Registered Report with n=231,076 medical judgments")
    print("• Quasi-experimental design (AM vs PM shift overlap)")
    print("• BF0+ > 22 for ALL main tests → strong evidence for NULL")
    print("• The 'hungry judge' (Danziger 2011) was likely scheduling confounds")
    print("• Decision fatigue as domain-general effect probably doesn't exist")
    print("")
    print("WHAT EXISTS INSTEAD:")
    print("• Rational inattention (Matějka & McKay 2015) — choices converge")
    print("  to priors when info cost rises. Economics, not depletion.")
    print("• Opportunity cost of effort (Kurzban 2013) — 'fatigue' signals")
    print("  better alternatives, not empty tank.")
    print("• Scheduling confounds — case ordering ≠ random in most studies")
    print("")
    print("AGENT IMPLICATION:")
    print("• Heartbeat quality doesn't degrade from 'too many decisions'")
    print("• If quality drops, check: task complexity, info availability,")
    print("  or rational disengagement — NOT 'fatigue'")
    print("• Breaks don't 'reset' decision capacity (BF0+ > 22)")
    print("• The entire concept may be a scheduling artifact dressed as psych")
    print("=" * 70)


if __name__ == "__main__":
    simulate_demo()
