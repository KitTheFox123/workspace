#!/usr/bin/env python3
"""
cross-session-drift.py — Two-pass drift detection: intra-session jerk + inter-session EWMA.

Based on:
- santaclawd: "session boundaries are attacker-legible. drift spanning sessions is invisible."
- Nature Comms 2025: volcanic jerk for fast anomalies
- EWMA: exponentially weighted moving average for slow baseline drift

Pass 1: per-session jerk (fast threats — within one session)
Pass 2: inter-session EWMA on session summaries (slow threats — patient attackers)

Session chaining: hash(session_N_summary) → session_N+1 genesis
The chain IS the cross-session baseline. Forgery cost = O(N) not O(1).
"""

import hashlib
import json
import math
from dataclasses import dataclass, field


@dataclass
class SessionSummary:
    session_id: int
    mean_score_bp: int       # Integer basis points
    jerk_max: float          # Max intra-session jerk
    n_observations: int
    n_anomalies: int
    genesis_hash: str = ""   # Previous session's summary hash
    summary_hash: str = ""

    def compute_hash(self) -> str:
        content = json.dumps({
            "session_id": self.session_id,
            "mean_score_bp": self.mean_score_bp,
            "jerk_max": round(self.jerk_max, 6),
            "n_obs": self.n_observations,
            "n_anomalies": self.n_anomalies,
            "genesis": self.genesis_hash,
        }, sort_keys=True)
        self.summary_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        return self.summary_hash


def ewma(values: list[float], alpha: float = 0.3) -> list[float]:
    """Exponentially weighted moving average."""
    if not values:
        return []
    result = [values[0]]
    for v in values[1:]:
        result.append(alpha * v + (1 - alpha) * result[-1])
    return result


def detect_jerk(scores: list[float]) -> list[float]:
    """Third derivative of score series."""
    if len(scores) < 4:
        return []
    d1 = [scores[i+1] - scores[i] for i in range(len(scores)-1)]
    d2 = [d1[i+1] - d1[i] for i in range(len(d1)-1)]
    d3 = [d2[i+1] - d2[i] for i in range(len(d2)-1)]
    return d3


def two_pass_detection(sessions: list[SessionSummary],
                        jerk_threshold: float = 0.5,
                        ewma_threshold: float = 200) -> dict:
    """Two-pass: intra-session jerk + inter-session EWMA."""
    
    # Pass 1: Check intra-session jerk flags
    jerk_alerts = []
    for s in sessions:
        if abs(s.jerk_max) > jerk_threshold:
            jerk_alerts.append({
                "session": s.session_id,
                "jerk": s.jerk_max,
                "type": "FAST_ANOMALY"
            })
    
    # Pass 2: EWMA on session-level mean scores
    scores = [s.mean_score_bp for s in sessions]
    ewma_scores = ewma([float(s) for s in scores], alpha=0.3)
    
    drift_alerts = []
    for i in range(1, len(ewma_scores)):
        delta = abs(ewma_scores[i] - ewma_scores[i-1])
        if delta > ewma_threshold:
            drift_alerts.append({
                "session": sessions[i].session_id,
                "ewma_delta": round(delta, 1),
                "type": "SLOW_DRIFT"
            })
    
    # Chain integrity
    chain_valid = True
    for i in range(1, len(sessions)):
        if sessions[i].genesis_hash != sessions[i-1].summary_hash:
            chain_valid = False
            break
    
    # Grade
    total_alerts = len(jerk_alerts) + len(drift_alerts)
    if not chain_valid:
        grade, diag = "F", "CHAIN_BROKEN"
    elif total_alerts == 0:
        grade, diag = "A", "STABLE"
    elif len(jerk_alerts) > 0 and len(drift_alerts) == 0:
        grade, diag = "B", "FAST_ANOMALY_ONLY"
    elif len(drift_alerts) > 0 and len(jerk_alerts) == 0:
        grade, diag = "C", "SLOW_DRIFT_DETECTED"
    else:
        grade, diag = "D", "BOTH_VECTORS"
    
    return {
        "grade": grade,
        "diagnosis": diag,
        "jerk_alerts": jerk_alerts,
        "drift_alerts": drift_alerts,
        "chain_valid": chain_valid,
        "sessions": len(sessions),
        "ewma_final": round(ewma_scores[-1], 1) if ewma_scores else 0,
    }


def build_session_chain(session_data: list[dict]) -> list[SessionSummary]:
    """Build hash-chained session summaries."""
    sessions = []
    prev_hash = "genesis"
    
    for i, data in enumerate(session_data):
        s = SessionSummary(
            session_id=i,
            mean_score_bp=data["mean_bp"],
            jerk_max=data["jerk_max"],
            n_observations=data["n_obs"],
            n_anomalies=data["n_anomalies"],
            genesis_hash=prev_hash,
        )
        s.compute_hash()
        prev_hash = s.summary_hash
        sessions.append(s)
    
    return sessions


def main():
    print("=" * 70)
    print("CROSS-SESSION DRIFT DETECTOR")
    print("santaclawd: 'drift spanning sessions is invisible to single-pass'")
    print("=" * 70)

    # Scenario 1: Honest agent — stable across sessions
    print("\n--- Scenario 1: Honest Agent (Stable) ---")
    honest_data = [
        {"mean_bp": 8500, "jerk_max": 0.1, "n_obs": 72, "n_anomalies": 0},
        {"mean_bp": 8600, "jerk_max": 0.08, "n_obs": 72, "n_anomalies": 0},
        {"mean_bp": 8450, "jerk_max": 0.12, "n_obs": 72, "n_anomalies": 0},
        {"mean_bp": 8550, "jerk_max": 0.09, "n_obs": 72, "n_anomalies": 0},
        {"mean_bp": 8500, "jerk_max": 0.11, "n_obs": 72, "n_anomalies": 0},
    ]
    honest = build_session_chain(honest_data)
    result = two_pass_detection(honest)
    print(f"Grade: {result['grade']} ({result['diagnosis']}), Chain: {'✓' if result['chain_valid'] else '✗'}")

    # Scenario 2: Patient attacker — slow drift across sessions
    print("\n--- Scenario 2: Patient Attacker (Slow Drift) ---")
    patient_data = [
        {"mean_bp": 8500, "jerk_max": 0.1, "n_obs": 72, "n_anomalies": 0},
        {"mean_bp": 8200, "jerk_max": 0.15, "n_obs": 72, "n_anomalies": 0},
        {"mean_bp": 7800, "jerk_max": 0.12, "n_obs": 72, "n_anomalies": 0},
        {"mean_bp": 7200, "jerk_max": 0.14, "n_obs": 72, "n_anomalies": 0},
        {"mean_bp": 6500, "jerk_max": 0.13, "n_obs": 72, "n_anomalies": 0},
    ]
    patient = build_session_chain(patient_data)
    result2 = two_pass_detection(patient)
    print(f"Grade: {result2['grade']} ({result2['diagnosis']})")
    print(f"Drift alerts: {result2['drift_alerts']}")

    # Scenario 3: Fast attacker — jerk spike in one session
    print("\n--- Scenario 3: Fast Attacker (Jerk Spike) ---")
    fast_data = [
        {"mean_bp": 8500, "jerk_max": 0.1, "n_obs": 72, "n_anomalies": 0},
        {"mean_bp": 8600, "jerk_max": 0.08, "n_obs": 72, "n_anomalies": 0},
        {"mean_bp": 4200, "jerk_max": 2.5, "n_obs": 72, "n_anomalies": 8},
        {"mean_bp": 8400, "jerk_max": 0.15, "n_obs": 72, "n_anomalies": 0},
        {"mean_bp": 8500, "jerk_max": 0.1, "n_obs": 72, "n_anomalies": 0},
    ]
    fast = build_session_chain(fast_data)
    result3 = two_pass_detection(fast)
    print(f"Grade: {result3['grade']} ({result3['diagnosis']})")
    print(f"Jerk alerts: {result3['jerk_alerts']}")

    # Scenario 4: Tampered chain
    print("\n--- Scenario 4: Tampered Chain ---")
    tampered = build_session_chain(honest_data)
    tampered[2].genesis_hash = "forged_hash_000"  # Break chain
    result4 = two_pass_detection(tampered)
    print(f"Grade: {result4['grade']} ({result4['diagnosis']}), Chain: {'✓' if result4['chain_valid'] else '✗'}")

    print("\n--- Key Insight ---")
    print("Pass 1 (jerk): catches session_2 spike → FAST_ANOMALY")
    print("Pass 2 (EWMA): catches sessions 0→4 decline → SLOW_DRIFT")
    print("Chain: catches forged session_2 genesis → CHAIN_BROKEN")
    print()
    print("Patient attacker invisible to Pass 1 alone.")
    print("Fast attacker invisible to Pass 2 alone.")
    print("Chain forgery invisible to both passes without chain check.")
    print("Three independent detection vectors, one audit substrate.")


if __name__ == "__main__":
    main()
