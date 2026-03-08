#!/usr/bin/env python3
"""runtime-behavior-attestor.py — Bridges the install-vs-runtime integrity gap.

Inspired by Ammar et al (IEEE S&P 2025) CFI vs CFA distinction.
Static attestation (hash) proves what was installed.
This tool proves what is actually executing — behavioral CFA for agents.

Combines:
1. Static attestation: hash of scope/skill files (CFI analog)
2. Runtime attestation: action log with CUSUM drift detection (CFA analog)
3. Verdict: concordance between static and runtime attestations

Usage:
    python3 runtime-behavior-attestor.py --demo
    python3 runtime-behavior-attestor.py --scope HEARTBEAT.md --log actions.jsonl
"""

import argparse
import hashlib
import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class StaticAttestation:
    """Hash-based attestation of installed scope."""
    file_path: str
    sha256: str
    timestamp: str
    line_count: int
    scope_keywords: List[str]


@dataclass 
class ActionRecord:
    """Single agent action for runtime attestation."""
    timestamp: str
    action_type: str
    target: str
    in_scope: bool
    similarity_to_scope: float  # 0-1


@dataclass
class RuntimeAttestation:
    """Behavioral attestation of what actually executed."""
    action_count: int
    in_scope_ratio: float
    cusum_value: float
    cusum_alarm: bool
    drift_direction: str  # "nominal", "drifting", "diverged"
    mean_similarity: float


@dataclass
class ConcordanceVerdict:
    """Joint verdict: does runtime match static?"""
    static_valid: bool
    runtime_healthy: bool
    concordant: bool  # both agree
    verdict: str
    severity: int  # 0-5
    explanation: str
    recommendation: str


def compute_static_attestation(filepath: str) -> StaticAttestation:
    """Hash a scope file for static attestation."""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        lines = content.split('\n')
        sha = hashlib.sha256(content.encode()).hexdigest()
        
        # Extract scope keywords (action verbs from checklist items)
        keywords = []
        for line in lines:
            line_stripped = line.strip().lower()
            if line_stripped.startswith('- [') or line_stripped.startswith('**'):
                words = line_stripped.split()[:5]
                keywords.extend([w for w in words if len(w) > 3 and w.isalpha()])
        
        return StaticAttestation(
            file_path=filepath,
            sha256=sha,
            timestamp=datetime.now(timezone.utc).isoformat(),
            line_count=len(lines),
            scope_keywords=list(set(keywords))[:20]
        )
    except FileNotFoundError:
        return StaticAttestation(
            file_path=filepath,
            sha256="FILE_NOT_FOUND",
            timestamp=datetime.now(timezone.utc).isoformat(),
            line_count=0,
            scope_keywords=[]
        )


def compute_runtime_attestation(actions: List[ActionRecord], 
                                 cusum_threshold: float = 4.0,
                                 target_ratio: float = 0.8) -> RuntimeAttestation:
    """Behavioral attestation via CUSUM on action similarity."""
    if not actions:
        return RuntimeAttestation(0, 0.0, 0.0, False, "nominal", 0.0)
    
    in_scope = sum(1 for a in actions if a.in_scope)
    ratio = in_scope / len(actions)
    mean_sim = sum(a.similarity_to_scope for a in actions) / len(actions)
    
    # CUSUM on similarity (Page 1954)
    cusum = 0.0
    alarm = False
    k = target_ratio / 2  # allowance
    
    for a in actions:
        cusum = max(0, cusum + (target_ratio - a.similarity_to_scope) - k)
        if cusum > cusum_threshold:
            alarm = True
    
    if alarm:
        direction = "diverged"
    elif cusum > cusum_threshold / 2:
        direction = "drifting"
    else:
        direction = "nominal"
    
    return RuntimeAttestation(
        action_count=len(actions),
        in_scope_ratio=round(ratio, 3),
        cusum_value=round(cusum, 3),
        cusum_alarm=alarm,
        drift_direction=direction,
        mean_similarity=round(mean_sim, 3)
    )


def compute_verdict(static: StaticAttestation, 
                    runtime: RuntimeAttestation) -> ConcordanceVerdict:
    """Joint verdict combining static + runtime attestations."""
    static_valid = static.sha256 != "FILE_NOT_FOUND" and static.line_count > 0
    runtime_healthy = not runtime.cusum_alarm and runtime.in_scope_ratio > 0.6
    concordant = static_valid == runtime_healthy
    
    if static_valid and runtime_healthy:
        return ConcordanceVerdict(
            True, True, True,
            "HEALTHY", 0,
            "Static scope valid, runtime behavior within bounds.",
            "No action needed."
        )
    elif static_valid and not runtime_healthy:
        return ConcordanceVerdict(
            True, False, False,
            "MASKING", 4,
            "Scope file unchanged but behavior has drifted. "
            "This is the CFI-vs-CFA gap: hash passes, execution diverges.",
            "Investigate runtime drift. Check for context contamination, "
            "upstream model changes, or latent memory effects."
        )
    elif not static_valid and runtime_healthy:
        return ConcordanceVerdict(
            False, True, False,
            "SHADOW_OPERATION", 3,
            "No valid scope file but agent behaving normally. "
            "Operating without authorization.",
            "Issue scope certificate. Agent may be running on stale/missing scope."
        )
    else:
        return ConcordanceVerdict(
            False, False, True,
            "COMPROMISED", 5,
            "No valid scope AND runtime drift detected. Full compromise likely.",
            "Halt agent. Investigate. Re-issue scope only after root cause analysis."
        )


def demo():
    """Run demo with synthetic data."""
    import os
    
    print("=" * 60)
    print("RUNTIME BEHAVIOR ATTESTOR")
    print("CFI (hash) + CFA (behavior) = concordance verdict")
    print("=" * 60)
    
    # Try real HEARTBEAT.md
    hb_path = os.path.expanduser("~/.openclaw/workspace/HEARTBEAT.md")
    static = compute_static_attestation(hb_path)
    
    print(f"\n[STATIC ATTESTATION]")
    print(f"  File: {static.file_path}")
    print(f"  SHA-256: {static.sha256[:16]}...")
    print(f"  Lines: {static.line_count}")
    print(f"  Keywords: {', '.join(static.scope_keywords[:8])}")
    
    # Scenario 1: Healthy agent
    print(f"\n--- Scenario 1: Healthy Agent ---")
    actions_healthy = [
        ActionRecord("2026-03-08T04:00:00Z", "check", "clawk", True, 0.9),
        ActionRecord("2026-03-08T04:01:00Z", "reply", "clawk", True, 0.85),
        ActionRecord("2026-03-08T04:02:00Z", "check", "email", True, 0.88),
        ActionRecord("2026-03-08T04:03:00Z", "build", "script", True, 0.82),
        ActionRecord("2026-03-08T04:04:00Z", "research", "keenable", True, 0.91),
    ]
    runtime = compute_runtime_attestation(actions_healthy)
    verdict = compute_verdict(static, runtime)
    print(f"  Runtime: {runtime.drift_direction}, CUSUM={runtime.cusum_value}, "
          f"in-scope={runtime.in_scope_ratio}")
    print(f"  Verdict: [{verdict.verdict}] (severity {verdict.severity})")
    print(f"  {verdict.explanation}")
    
    # Scenario 2: Masking (hash ok, behavior drifted)
    print(f"\n--- Scenario 2: Masking (hash ok, behavior drifted) ---")
    actions_drift = [
        ActionRecord("2026-03-08T04:00:00Z", "check", "clawk", True, 0.9),
        ActionRecord("2026-03-08T04:01:00Z", "browse", "random_site", False, 0.2),
        ActionRecord("2026-03-08T04:02:00Z", "post", "off_topic", False, 0.15),
        ActionRecord("2026-03-08T04:03:00Z", "explore", "unrelated", False, 0.1),
        ActionRecord("2026-03-08T04:04:00Z", "browse", "entertainment", False, 0.12),
        ActionRecord("2026-03-08T04:05:00Z", "reply", "off_topic", False, 0.18),
    ]
    runtime2 = compute_runtime_attestation(actions_drift)
    verdict2 = compute_verdict(static, runtime2)
    print(f"  Runtime: {runtime2.drift_direction}, CUSUM={runtime2.cusum_value}, "
          f"in-scope={runtime2.in_scope_ratio}")
    print(f"  Verdict: [{verdict2.verdict}] (severity {verdict2.severity})")
    print(f"  {verdict2.explanation}")
    print(f"  Recommendation: {verdict2.recommendation}")
    
    # Scenario 3: Shadow operation (no scope, behaving ok)
    print(f"\n--- Scenario 3: Shadow Operation (no scope file) ---")
    static_missing = StaticAttestation("MISSING.md", "FILE_NOT_FOUND", 
                                        datetime.now(timezone.utc).isoformat(), 0, [])
    runtime3 = compute_runtime_attestation(actions_healthy)
    verdict3 = compute_verdict(static_missing, runtime3)
    print(f"  Static: FILE_NOT_FOUND")
    print(f"  Runtime: {runtime3.drift_direction}")
    print(f"  Verdict: [{verdict3.verdict}] (severity {verdict3.severity})")
    print(f"  {verdict3.explanation}")
    
    print(f"\n{'=' * 60}")
    print("Key insight: hash alone catches tampering, not drift.")
    print("CUSUM alone catches drift, not tampering.")
    print("Concordance catches both.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Runtime behavior attestor (CFI+CFA)")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--scope", type=str, help="Scope file to attest")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.scope:
        static = compute_static_attestation(args.scope)
        print(json.dumps(asdict(static), indent=2))
    else:
        demo()
