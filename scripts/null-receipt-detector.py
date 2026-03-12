#!/usr/bin/env python3
"""Null Receipt Detector — find the dog that didn't bark.

Detects EXPECTED receipts/attestations that are MISSING from an agent's
behavioral stream. Absence against expectation is diagnostic (Holmes/Wald).

"The receipt you SHOULD have sent but didn't is more informative
than the one you did." — Kit, 2026-02-26

Based on:
- Wald (1947): Sequential probability ratio test
- Altman & Bland (BMJ 1995): Absence of evidence ≠ evidence of absence
  BUT: Absence against EXPECTATION IS evidence (Bayesian flip)
- santaclawd: "null nodes = git diff for governance"

Usage:
  python null-receipt-detector.py --demo
  echo '{"expected": [...], "received": [...]}' | python null-receipt-detector.py --json
"""

import json
import sys
import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExpectedReceipt:
    """A receipt we expect to see based on protocol/pattern."""
    id: str
    type: str           # heartbeat, attestation, delegation_ack, quality_report
    agent: str
    interval_hours: float   # Expected interval between receipts
    tolerance: float = 1.5  # Multiplier before flagging (1.5x = 50% late)
    last_seen: Optional[float] = None  # Epoch timestamp
    miss_count: int = 0
    total_expected: int = 0


@dataclass
class NullNode:
    """A detected absence — the dog that didn't bark."""
    receipt_type: str
    agent: str
    expected_at: float
    silence_duration_hours: float
    p_honest_given_silent: float  # P(honest | silent) — lower = more suspicious
    severity: str
    explanation: str


def bayesian_silence(
    p_silent_given_honest: float,    # Base rate of legitimate silence
    p_silent_given_dishonest: float,  # Rate of silence when compromised
    p_honest_prior: float,            # Prior trust
) -> float:
    """P(honest | silent) via Bayes theorem.
    
    When receipts are expected, silence is informative:
    - High p_silent_given_honest (0.3) = unreliable agent, silence is normal
    - Low p_silent_given_honest (0.01) = reliable agent, silence is alarming
    """
    p_silent = (
        p_silent_given_honest * p_honest_prior +
        p_silent_given_dishonest * (1 - p_honest_prior)
    )
    if p_silent == 0:
        return p_honest_prior
    return (p_silent_given_honest * p_honest_prior) / p_silent


def detect_null_receipts(
    expected: list[dict],
    received: list[dict],
    current_time: float,
    trust_prior: float = 0.9,
) -> dict:
    """Detect missing receipts and score their significance."""
    
    # Build expected receipt registry
    expectations = {}
    for e in expected:
        exp = ExpectedReceipt(
            id=e["id"],
            type=e["type"],
            agent=e["agent"],
            interval_hours=e["interval_hours"],
            tolerance=e.get("tolerance", 1.5),
        )
        expectations[f"{exp.agent}:{exp.type}"] = exp
    
    # Process received receipts
    for r in received:
        key = f"{r['agent']}:{r['type']}"
        if key in expectations:
            ts = r.get("timestamp", current_time)
            exp = expectations[key]
            exp.last_seen = max(exp.last_seen or 0, ts)
            exp.total_expected += 1
    
    # Detect nulls
    null_nodes = []
    for key, exp in expectations.items():
        if exp.last_seen is None:
            # Never seen — complete absence
            silence_hours = float('inf')
            p_silent_honest = 0.01  # Very unlikely if honest
        else:
            silence_hours = (current_time - exp.last_seen) / 3600
            expected_silence = exp.interval_hours * exp.tolerance
            
            if silence_hours <= expected_silence:
                continue  # Within tolerance
            
            # P(silent|honest) decreases exponentially with overdue time
            overdue_ratio = silence_hours / exp.interval_hours
            p_silent_honest = math.exp(-overdue_ratio + 1) * 0.3
            p_silent_honest = max(0.001, min(0.3, p_silent_honest))
        
        # Bayesian update
        p_honest = bayesian_silence(
            p_silent_given_honest=p_silent_honest,
            p_silent_given_dishonest=0.7,  # Compromised agents often go silent
            p_honest_prior=trust_prior,
        )
        
        # Severity
        if p_honest < 0.2:
            severity = "CRITICAL"
        elif p_honest < 0.5:
            severity = "HIGH"
        elif p_honest < 0.7:
            severity = "MEDIUM"
        else:
            severity = "LOW"
        
        null_nodes.append(NullNode(
            receipt_type=exp.type,
            agent=exp.agent,
            expected_at=exp.last_seen + exp.interval_hours * 3600 if exp.last_seen else current_time,
            silence_duration_hours=round(silence_hours, 1) if silence_hours != float('inf') else -1,
            p_honest_given_silent=round(p_honest, 4),
            severity=severity,
            explanation=_explain(exp, silence_hours, p_honest),
        ))
    
    # Sort by severity
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    null_nodes.sort(key=lambda n: severity_order.get(n.severity, 4))
    
    # Git diff analogy: what changed vs what was expected
    total_expected = len(expectations)
    total_received = len(set(f"{r['agent']}:{r['type']}" for r in received))
    total_null = len(null_nodes)
    
    return {
        "total_expected": total_expected,
        "total_received": total_received,
        "null_count": total_null,
        "coverage": round(total_received / total_expected, 3) if total_expected > 0 else 1.0,
        "governance_grade": _grade(null_nodes),
        "null_nodes": [vars(n) for n in null_nodes],
        "summary": _summarize(null_nodes),
    }


def _explain(exp, silence_hours, p_honest):
    if silence_hours == float('inf'):
        return f"{exp.agent} has NEVER sent a {exp.type} receipt. Expected every {exp.interval_hours}h."
    overdue = silence_hours - exp.interval_hours
    return f"{exp.agent} is {overdue:.1f}h overdue on {exp.type}. P(honest|silent)={p_honest:.3f}."


def _grade(null_nodes):
    if not null_nodes:
        return "A"
    critical = sum(1 for n in null_nodes if n.severity == "CRITICAL")
    high = sum(1 for n in null_nodes if n.severity == "HIGH")
    if critical > 0:
        return "F"
    if high > 1:
        return "D"
    if high == 1:
        return "C"
    return "B"


def _summarize(null_nodes):
    if not null_nodes:
        return "All expected receipts received. No dogs silent."
    agents = set(n.agent for n in null_nodes)
    critical = [n for n in null_nodes if n.severity in ("CRITICAL", "HIGH")]
    if critical:
        return f"{len(critical)} critical/high null receipts from {', '.join(set(n.agent for n in critical))}. Investigate immediately."
    return f"{len(null_nodes)} overdue receipts from {', '.join(agents)}. Monitor."


def demo():
    import time
    now = time.time()
    
    print("=" * 60)
    print("Null Receipt Detector — The Dog That Didn't Bark")
    print("Wald (1947) + Holmes + Altman & Bland (1995)")
    print("=" * 60)
    
    # Scenario 1: All receipts present
    print("\n--- Scenario 1: Healthy Agent Network ---")
    expected = [
        {"id": "hb1", "type": "heartbeat", "agent": "alpha", "interval_hours": 3},
        {"id": "att1", "type": "attestation", "agent": "alpha", "interval_hours": 24},
        {"id": "hb2", "type": "heartbeat", "agent": "beta", "interval_hours": 3},
    ]
    received = [
        {"agent": "alpha", "type": "heartbeat", "timestamp": now - 7200},
        {"agent": "alpha", "type": "attestation", "timestamp": now - 3600},
        {"agent": "beta", "type": "heartbeat", "timestamp": now - 5400},
    ]
    result = detect_null_receipts(expected, received, now)
    print(f"Grade: {result['governance_grade']} | Coverage: {result['coverage']}")
    print(f"Summary: {result['summary']}")
    
    # Scenario 2: One agent goes silent
    print("\n--- Scenario 2: Beta Goes Silent (12h overdue) ---")
    received_partial = [
        {"agent": "alpha", "type": "heartbeat", "timestamp": now - 7200},
        {"agent": "alpha", "type": "attestation", "timestamp": now - 3600},
        {"agent": "beta", "type": "heartbeat", "timestamp": now - 43200},  # 12h ago
    ]
    result = detect_null_receipts(expected, received_partial, now)
    print(f"Grade: {result['governance_grade']} | Nulls: {result['null_count']}")
    for n in result['null_nodes']:
        print(f"  🐕 [{n['severity']}] {n['explanation']}")
    
    # Scenario 3: Complete absence — never seen
    print("\n--- Scenario 3: Ghost Agent (Never Sent Receipts) ---")
    expected_with_ghost = expected + [
        {"id": "hb3", "type": "heartbeat", "agent": "gamma", "interval_hours": 3},
        {"id": "att3", "type": "attestation", "agent": "gamma", "interval_hours": 24},
    ]
    result = detect_null_receipts(expected_with_ghost, received, now)
    print(f"Grade: {result['governance_grade']} | Nulls: {result['null_count']}")
    for n in result['null_nodes']:
        print(f"  🐕 [{n['severity']}] {n['explanation']}")
    print(f"Summary: {result['summary']}")
    
    # Scenario 4: Cascading silence (multiple agents)
    print("\n--- Scenario 4: Cascading Silence (Possible Compromise) ---")
    expected_large = [
        {"id": f"hb_{a}", "type": "heartbeat", "agent": a, "interval_hours": 3}
        for a in ["alpha", "beta", "gamma", "delta", "epsilon"]
    ]
    received_sparse = [
        {"agent": "alpha", "type": "heartbeat", "timestamp": now - 7200},
        {"agent": "beta", "type": "heartbeat", "timestamp": now - 36000},  # 10h ago
        # gamma, delta, epsilon: never seen
    ]
    result = detect_null_receipts(expected_large, received_sparse, now, trust_prior=0.85)
    print(f"Grade: {result['governance_grade']} | Nulls: {result['null_count']}")
    for n in result['null_nodes']:
        print(f"  🐕 [{n['severity']}] P(honest|silent)={n['p_honest_given_silent']}")
    print(f"Summary: {result['summary']}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        import time
        data = json.load(sys.stdin)
        result = detect_null_receipts(
            data.get("expected", []),
            data.get("received", []),
            data.get("current_time", time.time()),
            data.get("trust_prior", 0.9),
        )
        print(json.dumps(result, indent=2))
    else:
        demo()
