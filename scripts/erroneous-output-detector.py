#!/usr/bin/env python3
"""
erroneous-output-detector.py — Detect erroneous output vs fail-silent failures.

NASA NESC 2022 (42 incidents): 88% erroneous output, 12% fail-silent.
Rebooting fixes fail-silent but NOT erroneous output.

Agent monitoring must detect BOTH:
- Fail-silent: watchdog timer, dead man's switch, heartbeat absence
- Erroneous output: behavioral drift, scope mismatch, quality decay

This script classifies agent behavior into failure modes and recommends
appropriate remediation (restart vs behavioral correction).
"""

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class FailureMode(Enum):
    HEALTHY = "healthy"
    FAIL_SILENT = "fail_silent"       # Agent stopped producing output
    ERRONEOUS_OUTPUT = "erroneous"    # Agent producing wrong output
    ERRONEOUS_CODING = "erroneous_coding"      # Logic error
    ERRONEOUS_DATA = "erroneous_data"          # Misconfigured input
    ERRONEOUS_INPUT = "erroneous_input"        # Unanticipated input
    ERRONEOUS_DRIFT = "erroneous_drift"        # Gradual behavioral shift


class Remediation(Enum):
    NONE = "none"
    RESTART = "restart"                     # Fixes fail-silent
    BEHAVIORAL_CORRECTION = "behavioral"    # Fixes erroneous output
    ROLLBACK = "rollback"                   # Restore to known-good state
    MANUAL_INTERVENTION = "manual"          # Human needed
    DISSIMILAR_BACKUP = "dissimilar"        # N-version switch


@dataclass
class AgentObservation:
    """Single observation of agent behavior."""
    agent_id: str
    timestamp: float
    has_output: bool
    output_hash: Optional[str] = None
    scope_hash: Optional[str] = None
    expected_scope_hash: Optional[str] = None
    quality_score: float = 1.0          # 0-1
    channels_active: int = 0
    channels_expected: int = 0
    action_count: int = 0


@dataclass 
class DiagnosticResult:
    failure_mode: FailureMode
    confidence: float
    remediation: Remediation
    reboot_effective: bool
    evidence: list
    grade: str


def classify_failure(observations: list[AgentObservation]) -> DiagnosticResult:
    """Classify agent failure mode from observation sequence."""
    
    if not observations:
        return DiagnosticResult(
            failure_mode=FailureMode.FAIL_SILENT,
            confidence=0.5,
            remediation=Remediation.RESTART,
            reboot_effective=True,
            evidence=["No observations available"],
            grade="F"
        )
    
    recent = observations[-5:]  # Last 5 observations
    evidence = []
    
    # Check 1: Fail-silent (no output)
    silent_count = sum(1 for o in recent if not o.has_output)
    if silent_count >= 3:
        return DiagnosticResult(
            failure_mode=FailureMode.FAIL_SILENT,
            confidence=silent_count / len(recent),
            remediation=Remediation.RESTART,
            reboot_effective=True,
            evidence=[f"{silent_count}/{len(recent)} observations have no output",
                      "Fail-silent: watchdog timer should have caught this",
                      "NASA NESC: 12% of failures are fail-silent, reboot usually fixes"],
            grade="F"
        )
    
    # Check 2: Scope mismatch (erroneous — data misconfigured)
    scope_mismatches = sum(1 for o in recent 
                          if o.scope_hash and o.expected_scope_hash 
                          and o.scope_hash != o.expected_scope_hash)
    if scope_mismatches >= 2:
        evidence.append(f"{scope_mismatches} scope mismatches detected")
        return DiagnosticResult(
            failure_mode=FailureMode.ERRONEOUS_DATA,
            confidence=scope_mismatches / len(recent),
            remediation=Remediation.ROLLBACK,
            reboot_effective=False,  # NASA: reboot doesn't fix erroneous output
            evidence=evidence + ["Scope hash mismatch = data misconfiguration",
                                 "NASA NESC: reboot ineffective for erroneous output",
                                 "Remediation: rollback to last known-good scope"],
            grade="D"
        )
    
    # Check 3: Quality decay (erroneous — behavioral drift)
    quality_scores = [o.quality_score for o in recent if o.has_output]
    if quality_scores and len(quality_scores) >= 3:
        avg_quality = sum(quality_scores) / len(quality_scores)
        trend = quality_scores[-1] - quality_scores[0]
        
        if avg_quality < 0.5 or trend < -0.3:
            evidence.append(f"Quality decay: avg={avg_quality:.2f}, trend={trend:+.2f}")
            return DiagnosticResult(
                failure_mode=FailureMode.ERRONEOUS_DRIFT,
                confidence=1.0 - avg_quality,
                remediation=Remediation.BEHAVIORAL_CORRECTION,
                reboot_effective=False,
                evidence=evidence + ["Behavioral drift detected",
                                     "NASA NESC: erroneous output 7× more common than fail-silent",
                                     "Remediation: behavioral correction, not restart"],
                grade="D"
            )
    
    # Check 4: Channel attrition (erroneous — scope contraction)
    channel_ratios = [o.channels_active / max(o.channels_expected, 1) for o in recent]
    if channel_ratios and sum(channel_ratios) / len(channel_ratios) < 0.5:
        evidence.append(f"Channel coverage declining: {[f'{r:.0%}' for r in channel_ratios]}")
        return DiagnosticResult(
            failure_mode=FailureMode.ERRONEOUS_OUTPUT,
            confidence=0.7,
            remediation=Remediation.BEHAVIORAL_CORRECTION,
            reboot_effective=False,
            evidence=evidence + ["Scope contraction = doing less while appearing active",
                                 "The dangerous kind: agent IS running, output IS wrong"],
            grade="C"
        )
    
    # Check 5: Stale output (same hash repeated)
    if len(recent) >= 3:
        hashes = [o.output_hash for o in recent if o.output_hash]
        if len(hashes) >= 3 and len(set(hashes)) == 1:
            return DiagnosticResult(
                failure_mode=FailureMode.ERRONEOUS_CODING,
                confidence=0.8,
                remediation=Remediation.DISSIMILAR_BACKUP,
                reboot_effective=False,
                evidence=["Same output hash repeated across observations",
                          "Stuck loop: producing output but not adapting",
                          "NASA: dissimilar backup needed for coding/logic errors"],
                grade="F"
            )
    
    # Healthy
    return DiagnosticResult(
        failure_mode=FailureMode.HEALTHY,
        confidence=0.9,
        remediation=Remediation.NONE,
        reboot_effective=False,
        evidence=["All checks passed", "Output present, scope valid, quality stable"],
        grade="A"
    )


def demo():
    print("=" * 60)
    print("ERRONEOUS OUTPUT DETECTOR")
    print("NASA NESC 2022: 88% erroneous, 12% fail-silent")
    print("=" * 60)
    
    scenarios = {
        "healthy_agent": [
            AgentObservation("bot_a", 1000+i*60, True, f"hash_{i}", "scope_1", "scope_1", 0.85+i*0.02, 4, 4, 3+i)
            for i in range(5)
        ],
        "fail_silent": [
            AgentObservation("bot_b", 1000, True, "h1", "s1", "s1", 0.9, 4, 4, 5),
            AgentObservation("bot_b", 1060, True, "h2", "s1", "s1", 0.85, 4, 4, 3),
            AgentObservation("bot_b", 1120, False, None, None, None, 0.0, 0, 4, 0),
            AgentObservation("bot_b", 1180, False, None, None, None, 0.0, 0, 4, 0),
            AgentObservation("bot_b", 1240, False, None, None, None, 0.0, 0, 4, 0),
        ],
        "scope_mismatch": [
            AgentObservation("bot_c", 1000+i*60, True, f"h_{i}", "scope_WRONG", "scope_CORRECT", 0.7, 3, 4, 2)
            for i in range(5)
        ],
        "quality_decay": [
            AgentObservation("bot_d", 1000+i*60, True, f"h_{i}", "s1", "s1", 0.95 - i*0.15, 4, 4, max(1, 5-i))
            for i in range(5)
        ],
        "stuck_loop": [
            AgentObservation("bot_e", 1000+i*60, True, "same_hash", "s1", "s1", 0.5, 2, 4, 1)
            for i in range(5)
        ],
    }
    
    for name, observations in scenarios.items():
        result = classify_failure(observations)
        print(f"\n{'─' * 50}")
        print(f"Scenario: {name}")
        print(f"  Failure mode: {result.failure_mode.value}")
        print(f"  Confidence: {result.confidence:.0%}")
        print(f"  Remediation: {result.remediation.value}")
        print(f"  Reboot effective: {'YES' if result.reboot_effective else 'NO'}")
        print(f"  Grade: {result.grade}")
        for e in result.evidence:
            print(f"  → {e}")
    
    # Summary statistics
    print(f"\n{'=' * 60}")
    print("NASA NESC KEY FINDINGS (42 incidents, 24 open-source):")
    print("  • Erroneous output: 88% of failures")
    print("  • Fail-silent: 12% of failures")
    print("  • Reboot fixes fail-silent: YES (usually)")
    print("  • Reboot fixes erroneous: NO (almost never)")
    print("  • Root causes: coding/logic (most), data misconfig, bad input")
    print("  • Fix: dissimilar backup + behavioral monitoring")
    print("  • Watchdog timers only catch fail-silent (12%)")
    print("  • Behavioral attestation catches erroneous (88%)")
    print("=" * 60)


if __name__ == "__main__":
    demo()
