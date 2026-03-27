#!/usr/bin/env python3
"""
grader-fatigue-detector.py — Detect decision fatigue patterns in ATF grader pools.

Maps decision fatigue research to agent attestation:
- Choudhury & Saravanan (Frontiers Cognition, Jan 2026): 10 causes of decision fatigue,
  classified as organizational/individual/external. 4 primary effects: ineffective,
  conservative, erroneous, perceived complexity.
- Key finding: decisions degrade with TIME (shift progression), FREQUENCY (successive
  decisions), and COMPLEXITY. Breaks restore performance.
- Linder et al (2014): antibiotic prescribing increased 26% by 4th hour of shift.
- Allan et al (2019): nurses become more conservative after each decision since last break.
- Hirshleifer et al (2019): analyst forecast accuracy declines with daily forecast count.

ATF parallel: Agent graders making successive attestations exhibit the SAME patterns.
- Attestation quality degrades over session length
- Graders default to "safe" scores (conservatism bias)
- Score variance drops late in session (mode collapse from fatigue, not agreement)
- Breaks between attestation batches restore quality

Detection: Monitor per-grader temporal patterns to distinguish genuine agreement
from fatigue-induced convergence.
"""

import json
import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from typing import Optional


@dataclass
class Attestation:
    """A single grader attestation with temporal metadata."""
    grader_id: str
    claim_id: str
    score: float           # 0.0 to 1.0
    reasoning_length: int  # chars in reasoning text
    confidence: float      # self-reported
    timestamp: datetime
    session_order: int     # nth attestation in this grader's session
    minutes_since_break: float  # time since last break/session start


@dataclass 
class FatigueSignal:
    """A detected fatigue signal with evidence."""
    signal_type: str
    grader_id: str
    severity: str          # "low", "medium", "high"
    evidence: str
    recommendation: str


class GraderFatigueDetector:
    """
    Detect decision fatigue in ATF grader attestation patterns.
    
    Three fatigue indicators (from Choudhury & Saravanan 2026 framework):
    
    1. TEMPORAL_DECAY: Score quality degrades over time
       - Reasoning length shortens (cognitive shortcutting)
       - Score variance drops (defaulting to "safe" middle scores)
       - Source: Duration of decisions, Linder et al 2014
       
    2. SEQUENTIAL_DRIFT: Successive attestations converge
       - nth attestation more conservative than 1st
       - Confidence remains high even as reasoning thins
       - Source: Frequency of decisions, Ma et al 2021
       
    3. COMPLEXITY_AVOIDANCE: Hard claims get lower engagement
       - Complex claims get shorter reasoning when fatigued
       - Simple claims maintain quality (low cognitive load)
       - Source: Complexity of decision-making, Mullette-Gillman et al 2015
    """
    
    # Thresholds calibrated to literature
    REASONING_DECAY_THRESHOLD = 0.30     # 30% shorter reasoning = fatigue signal
    VARIANCE_COLLAPSE_THRESHOLD = 0.50   # 50% variance drop = convergence signal
    CONSERVATISM_THRESHOLD = 0.15        # Score shifts >15% toward 0.5 = conservatism
    CONFIDENCE_REASONING_RATIO = 2.0     # High confidence / thin reasoning = overconfidence
    BREAK_BENEFIT_WINDOW_MINS = 30       # Breaks <30 min ago restore performance
    
    def __init__(self):
        self.signals: list[FatigueSignal] = []
    
    def analyze_grader(self, attestations: list[Attestation]) -> dict:
        """Analyze a single grader's attestation sequence for fatigue signals."""
        self.signals = []
        
        if len(attestations) < 3:
            return {"status": "INSUFFICIENT", "attestation_count": len(attestations)}
        
        # Sort by session order
        sorted_atts = sorted(attestations, key=lambda a: a.session_order)
        
        # 1. Temporal decay: reasoning length over session
        self._check_reasoning_decay(sorted_atts)
        
        # 2. Sequential drift: score variance early vs late
        self._check_sequential_drift(sorted_atts)
        
        # 3. Conservatism bias: scores drift toward 0.5
        self._check_conservatism_drift(sorted_atts)
        
        # 4. Confidence-reasoning disconnect
        self._check_confidence_disconnect(sorted_atts)
        
        # 5. Break effect
        self._check_break_effect(sorted_atts)
        
        # Overall assessment
        high_count = sum(1 for s in self.signals if s.severity == "high")
        med_count = sum(1 for s in self.signals if s.severity == "medium")
        
        if high_count >= 2:
            status = "FATIGUED"
        elif high_count >= 1 or med_count >= 2:
            status = "DEGRADING"
        elif med_count >= 1:
            status = "MILD"
        else:
            status = "FRESH"
        
        return {
            "grader_id": sorted_atts[0].grader_id,
            "status": status,
            "attestation_count": len(attestations),
            "session_duration_mins": (sorted_atts[-1].timestamp - sorted_atts[0].timestamp).total_seconds() / 60,
            "signals": [
                {
                    "type": s.signal_type,
                    "severity": s.severity,
                    "evidence": s.evidence,
                    "recommendation": s.recommendation,
                }
                for s in self.signals
            ],
        }
    
    def _check_reasoning_decay(self, atts: list[Attestation]):
        """Check if reasoning length decays over session (Linder et al pattern)."""
        n = len(atts)
        first_half = atts[:n//2]
        second_half = atts[n//2:]
        
        avg_early = statistics.mean(a.reasoning_length for a in first_half)
        avg_late = statistics.mean(a.reasoning_length for a in second_half)
        
        if avg_early == 0:
            return
        
        decay = (avg_early - avg_late) / avg_early
        
        if decay > self.REASONING_DECAY_THRESHOLD:
            severity = "high" if decay > 0.5 else "medium"
            self.signals.append(FatigueSignal(
                signal_type="REASONING_DECAY",
                grader_id=atts[0].grader_id,
                severity=severity,
                evidence=f"Reasoning length dropped {decay:.0%}: {avg_early:.0f} → {avg_late:.0f} chars. "
                         f"Linder et al 2014: cognitive shortcuts increase 26% by hour 4.",
                recommendation="Insert mandatory break or cap session at "
                              f"{n//2} attestations.",
            ))
    
    def _check_sequential_drift(self, atts: list[Attestation]):
        """Check if score variance collapses (Allan et al pattern)."""
        n = len(atts)
        early_scores = [a.score for a in atts[:n//2]]
        late_scores = [a.score for a in atts[n//2:]]
        
        if len(early_scores) < 2 or len(late_scores) < 2:
            return
        
        early_var = statistics.variance(early_scores)
        late_var = statistics.variance(late_scores)
        
        if early_var == 0:
            return
        
        collapse = (early_var - late_var) / early_var
        
        if collapse > self.VARIANCE_COLLAPSE_THRESHOLD:
            self.signals.append(FatigueSignal(
                signal_type="VARIANCE_COLLAPSE",
                grader_id=atts[0].grader_id,
                severity="high" if collapse > 0.7 else "medium",
                evidence=f"Score variance dropped {collapse:.0%}: {early_var:.4f} → {late_var:.4f}. "
                         f"Allan et al 2019: nurses become more conservative per decision since break.",
                recommendation="Shuffle attestation order or inject calibration claims.",
            ))
    
    def _check_conservatism_drift(self, atts: list[Attestation]):
        """Check if scores drift toward 0.5 (safe middle)."""
        n = len(atts)
        early_distance = statistics.mean(abs(a.score - 0.5) for a in atts[:n//2])
        late_distance = statistics.mean(abs(a.score - 0.5) for a in atts[n//2:])
        
        drift = early_distance - late_distance
        
        if drift > self.CONSERVATISM_THRESHOLD:
            self.signals.append(FatigueSignal(
                signal_type="CONSERVATISM_DRIFT",
                grader_id=atts[0].grader_id,
                severity="medium",
                evidence=f"Scores drifted {drift:.2f} toward 0.5 midpoint over session. "
                         f"Fatigued graders default to 'safe' middle scores.",
                recommendation="Weight late-session scores lower or require justification "
                              "for scores near 0.5.",
            ))
    
    def _check_confidence_disconnect(self, atts: list[Attestation]):
        """Check if confidence stays high while reasoning thins."""
        late = atts[len(atts)//2:]
        
        for a in late:
            if a.reasoning_length > 0:
                ratio = a.confidence / (a.reasoning_length / 100)  # Normalize to ~1.0
                if ratio > self.CONFIDENCE_REASONING_RATIO and a.confidence > 0.8:
                    self.signals.append(FatigueSignal(
                        signal_type="CONFIDENCE_DISCONNECT",
                        grader_id=a.grader_id,
                        severity="medium",
                        evidence=f"Attestation #{a.session_order}: confidence={a.confidence:.2f} "
                                f"but reasoning only {a.reasoning_length} chars. "
                                f"Hirshleifer et al 2019: fatigued analysts rely on heuristics "
                                f"while maintaining confidence.",
                        recommendation="Flag high-confidence thin-reasoning attestations for review.",
                    ))
                    break  # One signal is enough
    
    def _check_break_effect(self, atts: list[Attestation]):
        """Check if breaks restore quality (Baer & Schnall 2021 pattern)."""
        # Look for quality improvement after breaks
        for i in range(1, len(atts)):
            if (atts[i].minutes_since_break < self.BREAK_BENEFIT_WINDOW_MINS and 
                atts[i-1].minutes_since_break >= self.BREAK_BENEFIT_WINDOW_MINS):
                # Post-break attestation
                if atts[i].reasoning_length > atts[i-1].reasoning_length * 1.3:
                    self.signals.append(FatigueSignal(
                        signal_type="BREAK_RECOVERY",
                        grader_id=atts[i].grader_id,
                        severity="low",
                        evidence=f"Post-break reasoning jumped {atts[i].reasoning_length} vs "
                                f"pre-break {atts[i-1].reasoning_length} chars. "
                                f"Baer & Schnall 2021: credit approvals recovered post-lunch.",
                        recommendation="Enforce break policy: max 6 attestations per session "
                                      "before mandatory 15-min break.",
                    ))
                    break


def analyze_pool(attestations: list[Attestation]) -> dict:
    """Analyze entire grader pool, detecting per-grader fatigue and pool-level patterns."""
    detector = GraderFatigueDetector()
    
    # Group by grader
    by_grader = defaultdict(list)
    for a in attestations:
        by_grader[a.grader_id].append(a)
    
    grader_results = {}
    for gid, atts in by_grader.items():
        grader_results[gid] = detector.analyze_grader(atts)
    
    # Pool-level stats
    fatigued = sum(1 for r in grader_results.values() if r["status"] == "FATIGUED")
    degrading = sum(1 for r in grader_results.values() if r["status"] == "DEGRADING")
    fresh = sum(1 for r in grader_results.values() if r["status"] == "FRESH")
    
    pool_status = "HEALTHY"
    if fatigued / max(len(grader_results), 1) > 0.5:
        pool_status = "POOL_FATIGUED"
    elif (fatigued + degrading) / max(len(grader_results), 1) > 0.5:
        pool_status = "POOL_DEGRADING"
    
    return {
        "pool_status": pool_status,
        "total_graders": len(grader_results),
        "fresh": fresh,
        "degrading": degrading,
        "fatigued": fatigued,
        "graders": grader_results,
    }


def run_demo():
    """Demonstrate fatigue detection with synthetic data."""
    print("=" * 70)
    print("GRADER FATIGUE DETECTOR — ATF ATTESTATION QUALITY MONITOR")
    print("Based on Choudhury & Saravanan (Frontiers Cognition, Jan 2026)")
    print("=" * 70)
    
    now = datetime.now(timezone.utc)
    
    # Grader A: Fatigued — reasoning decays, scores converge, confidence stays high
    grader_a = []
    for i in range(8):
        reasoning_len = max(50, 300 - i * 35)  # Decays from 300 to ~50
        score = 0.9 - i * 0.02 if i < 3 else 0.75 + (i % 2) * 0.02  # Converges to ~0.75
        grader_a.append(Attestation(
            grader_id="grader_alpha",
            claim_id=f"claim_{i}",
            score=score,
            reasoning_length=reasoning_len,
            confidence=0.90 - i * 0.01,  # Barely drops
            timestamp=now + timedelta(minutes=i * 12),
            session_order=i,
            minutes_since_break=i * 12,
        ))
    
    # Grader B: Fresh — consistent quality throughout
    grader_b = []
    for i in range(8):
        reasoning_len = 250 + (i % 3) * 30  # Stable with natural variation
        score = [0.85, 0.60, 0.90, 0.70, 0.95, 0.55, 0.80, 0.65][i]  # Varied
        grader_b.append(Attestation(
            grader_id="grader_beta",
            claim_id=f"claim_{i}",
            score=score,
            reasoning_length=reasoning_len,
            confidence=0.75 + (i % 3) * 0.05,
            timestamp=now + timedelta(minutes=i * 15),
            session_order=i,
            minutes_since_break=i * 15 if i < 4 else (i - 4) * 15,  # Break at claim 4
        ))
    
    # Grader C: Break recovery pattern
    grader_c = []
    for i in range(6):
        if i < 3:
            reasoning_len = 280 - i * 60  # Decays
            mins_break = i * 20
        else:
            reasoning_len = 300 - (i - 3) * 40  # Recovers post-break
            mins_break = (i - 3) * 20  # Reset after break
        
        grader_c.append(Attestation(
            grader_id="grader_gamma",
            claim_id=f"claim_{i}",
            score=[0.9, 0.8, 0.75, 0.85, 0.7, 0.65][i],
            reasoning_length=reasoning_len,
            confidence=0.85,
            timestamp=now + timedelta(minutes=i * 15),
            session_order=i,
            minutes_since_break=mins_break,
        ))
    
    all_attestations = grader_a + grader_b + grader_c
    result = analyze_pool(all_attestations)
    
    print(f"\nPool Status: {result['pool_status']}")
    print(f"Graders: {result['total_graders']} "
          f"(Fresh: {result['fresh']}, Degrading: {result['degrading']}, "
          f"Fatigued: {result['fatigued']})")
    
    for gid, gresult in result["graders"].items():
        print(f"\n--- {gid}: {gresult['status']} ---")
        print(f"  Attestations: {gresult['attestation_count']}, "
              f"Session: {gresult.get('session_duration_mins', 0):.0f} min")
        for signal in gresult.get("signals", []):
            print(f"  ⚠ [{signal['severity'].upper()}] {signal['type']}")
            print(f"    {signal['evidence']}")
            print(f"    → {signal['recommendation']}")
    
    print(f"\n{'=' * 70}")
    print("ATF implications:")
    print("- Monitor per-grader temporal patterns to distinguish agreement from fatigue")
    print("- Cap session length: max 6 attestations before mandatory break")
    print("- Weight late-session scores lower unless post-break")
    print("- Shuffle attestation order to prevent sequential bias")
    print("- Flag high-confidence + thin-reasoning combinations")
    print(f"\nSources: Choudhury & Saravanan 2026, Linder 2014, Allan 2019,")
    print(f"  Hirshleifer 2019, Baer & Schnall 2021, Mullette-Gillman 2015")


if __name__ == "__main__":
    run_demo()
