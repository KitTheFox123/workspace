#!/usr/bin/env python3
"""Receipt Anomaly Detector — IDS for attestation chains.

Maps OTEL observability patterns to receipt chains:
- Scope exceeded? Flag.
- Unknown attester? Flag.
- Timestamp gap? Flag.
- Burst pattern? Flag (sybil).
- Missing proof class? Flag.

Based on santaclawd's insight: "receipts aren't just forensics — they're intrusion detection."
IBM 2024: avg breach detection = 194 days. This tool aims to compress MTTD to minutes.

Usage:
  python receipt-anomaly-detector.py --demo
  echo '{"receipts": [...]}' | python receipt-anomaly-detector.py --json
"""

import json
import sys
import math
from datetime import datetime, timedelta
from collections import Counter

# Anomaly types with severity weights
ANOMALY_WEIGHTS = {
    "scope_exceeded": 0.9,       # Agent acted outside declared scope
    "unknown_attester": 0.7,     # Attester not in known registry
    "timestamp_gap": 0.6,        # Unexpected gap in receipt chain
    "timestamp_burst": 0.8,      # Too many receipts too fast (sybil)
    "missing_proof_class": 0.5,  # Expected proof class absent
    "attester_concentration": 0.7, # Too few unique attesters
    "temporal_regression": 0.95,  # Receipt timestamp before parent (causality violation)
    "duplicate_nonce": 1.0,       # Replay attack
    "proof_class_monotony": 0.4,  # All proofs same class (low diversity)
}

# Expected inter-receipt intervals by context (seconds)
EXPECTED_INTERVALS = {
    "payment": 86400,      # ~1 per day
    "generation": 600,     # ~every 10 min during active work
    "transport": 60,       # ~per message
    "witness": 3600,       # ~hourly
}


def detect_anomalies(receipts: list, config: dict = None) -> dict:
    """Analyze a receipt chain for anomalies."""
    config = config or {}
    known_attesters = set(config.get("known_attesters", []))
    declared_scope = config.get("declared_scope", [])
    
    anomalies = []
    
    if not receipts:
        return {"anomaly_count": 0, "anomalies": [], "risk_score": 0.0, "grade": "A"}
    
    # Sort by timestamp
    sorted_receipts = sorted(receipts, key=lambda r: r.get("timestamp", ""))
    
    # 1. Temporal analysis
    timestamps = []
    for r in sorted_receipts:
        ts = r.get("timestamp")
        if ts:
            try:
                timestamps.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
            except:
                timestamps.append(None)
        else:
            timestamps.append(None)
    
    # Check for temporal regression (causality violation)
    for i in range(1, len(timestamps)):
        if timestamps[i] and timestamps[i-1] and timestamps[i] < timestamps[i-1]:
            anomalies.append({
                "type": "temporal_regression",
                "severity": ANOMALY_WEIGHTS["temporal_regression"],
                "detail": f"Receipt {i} predates receipt {i-1}",
                "receipt_index": i,
            })
    
    # Check for bursts (sybil pattern)
    if len(timestamps) >= 3:
        valid_ts = [t for t in timestamps if t]
        if len(valid_ts) >= 3:
            intervals = [(valid_ts[i+1] - valid_ts[i]).total_seconds() for i in range(len(valid_ts)-1)]
            burst_threshold = 2.0  # seconds
            burst_count = sum(1 for iv in intervals if 0 <= iv < burst_threshold)
            if burst_count >= 2:
                anomalies.append({
                    "type": "timestamp_burst",
                    "severity": ANOMALY_WEIGHTS["timestamp_burst"],
                    "detail": f"{burst_count} receipts within {burst_threshold}s of each other",
                    "burst_count": burst_count,
                })
    
    # Check for gaps
    if len(timestamps) >= 2:
        valid_ts = [t for t in timestamps if t]
        if len(valid_ts) >= 2:
            intervals = [(valid_ts[i+1] - valid_ts[i]).total_seconds() for i in range(len(valid_ts)-1)]
            if intervals:
                median_interval = sorted(intervals)[len(intervals)//2]
                for i, iv in enumerate(intervals):
                    if iv > median_interval * 10 and iv > 3600:  # 10x median and >1hr
                        anomalies.append({
                            "type": "timestamp_gap",
                            "severity": ANOMALY_WEIGHTS["timestamp_gap"],
                            "detail": f"Gap of {iv/3600:.1f}h between receipts {i} and {i+1} (median: {median_interval/60:.1f}m)",
                            "gap_seconds": iv,
                        })
    
    # 2. Attester analysis
    attesters = [r.get("attester", "unknown") for r in sorted_receipts]
    attester_set = set(attesters)
    
    # Unknown attesters
    if known_attesters:
        unknown = attester_set - known_attesters
        for u in unknown:
            anomalies.append({
                "type": "unknown_attester",
                "severity": ANOMALY_WEIGHTS["unknown_attester"],
                "detail": f"Attester '{u}' not in known registry",
                "attester": u,
            })
    
    # Attester concentration
    attester_counts = Counter(attesters)
    if len(attester_set) == 1 and len(sorted_receipts) > 3:
        anomalies.append({
            "type": "attester_concentration",
            "severity": ANOMALY_WEIGHTS["attester_concentration"],
            "detail": f"All {len(sorted_receipts)} receipts from single attester: {attesters[0]}",
        })
    
    # 3. Scope analysis
    if declared_scope:
        for i, r in enumerate(sorted_receipts):
            action = r.get("action", r.get("proof_type", ""))
            if action and action not in declared_scope:
                anomalies.append({
                    "type": "scope_exceeded",
                    "severity": ANOMALY_WEIGHTS["scope_exceeded"],
                    "detail": f"Action '{action}' not in declared scope {declared_scope}",
                    "receipt_index": i,
                })
    
    # 4. Proof class analysis
    proof_classes = [r.get("proof_class", r.get("proof_type", "unknown")) for r in sorted_receipts]
    unique_classes = set(proof_classes)
    if len(unique_classes) == 1 and len(sorted_receipts) > 3:
        anomalies.append({
            "type": "proof_class_monotony",
            "severity": ANOMALY_WEIGHTS["proof_class_monotony"],
            "detail": f"All {len(sorted_receipts)} receipts are class '{proof_classes[0]}'. Expected diversity.",
        })
    
    # 5. Duplicate nonce detection
    nonces = [r.get("nonce") for r in sorted_receipts if r.get("nonce")]
    nonce_counts = Counter(nonces)
    for nonce, count in nonce_counts.items():
        if count > 1:
            anomalies.append({
                "type": "duplicate_nonce",
                "severity": ANOMALY_WEIGHTS["duplicate_nonce"],
                "detail": f"Nonce '{nonce}' appears {count} times (replay attack?)",
                "nonce": nonce,
            })
    
    # Compute risk score
    if anomalies:
        max_severity = max(a["severity"] for a in anomalies)
        avg_severity = sum(a["severity"] for a in anomalies) / len(anomalies)
        risk_score = 0.7 * max_severity + 0.3 * avg_severity
    else:
        risk_score = 0.0
    
    grade = "A" if risk_score < 0.2 else "B" if risk_score < 0.4 else "C" if risk_score < 0.6 else "D" if risk_score < 0.8 else "F"
    
    return {
        "receipt_count": len(sorted_receipts),
        "unique_attesters": len(attester_set),
        "unique_proof_classes": len(unique_classes),
        "anomaly_count": len(anomalies),
        "risk_score": round(risk_score, 3),
        "grade": grade,
        "anomalies": anomalies,
        "recommendation": "BLOCK" if risk_score > 0.8 else "INVESTIGATE" if risk_score > 0.5 else "MONITOR" if risk_score > 0.2 else "PASS",
    }


def demo():
    """Demo with realistic scenarios."""
    print("=" * 60)
    print("Receipt Anomaly Detector (Agent IDS)")
    print("=" * 60)
    
    base = datetime(2026, 2, 26, 4, 0, 0)
    
    # Scenario 1: Clean receipt chain
    clean = [
        {"attester": "kit_fox", "proof_class": "generation", "timestamp": (base).isoformat() + "Z", "nonce": "n1"},
        {"attester": "bro_agent", "proof_class": "witness", "timestamp": (base + timedelta(hours=1)).isoformat() + "Z", "nonce": "n2"},
        {"attester": "agentmail", "proof_class": "transport", "timestamp": (base + timedelta(hours=2)).isoformat() + "Z", "nonce": "n3"},
        {"attester": "paylock", "proof_class": "payment", "timestamp": (base + timedelta(hours=3)).isoformat() + "Z", "nonce": "n4"},
    ]
    
    print("\n--- Scenario 1: Clean Chain (TC3-like) ---")
    r = detect_anomalies(clean, {"known_attesters": ["kit_fox", "bro_agent", "agentmail", "paylock"]})
    print(f"Grade: {r['grade']} | Risk: {r['risk_score']} | Anomalies: {r['anomaly_count']} | → {r['recommendation']}")
    
    # Scenario 2: Sybil burst
    sybil = [
        {"attester": "sybil_1", "proof_class": "witness", "timestamp": (base).isoformat() + "Z", "nonce": "s1"},
        {"attester": "sybil_2", "proof_class": "witness", "timestamp": (base + timedelta(seconds=0.5)).isoformat() + "Z", "nonce": "s2"},
        {"attester": "sybil_3", "proof_class": "witness", "timestamp": (base + timedelta(seconds=1.0)).isoformat() + "Z", "nonce": "s3"},
        {"attester": "sybil_4", "proof_class": "witness", "timestamp": (base + timedelta(seconds=1.5)).isoformat() + "Z", "nonce": "s4"},
    ]
    
    print("\n--- Scenario 2: Sybil Burst ---")
    r = detect_anomalies(sybil, {"known_attesters": ["kit_fox", "bro_agent"]})
    print(f"Grade: {r['grade']} | Risk: {r['risk_score']} | Anomalies: {r['anomaly_count']} | → {r['recommendation']}")
    for a in r['anomalies']:
        print(f"  🚨 {a['type']}: {a['detail']}")
    
    # Scenario 3: Scope violation + temporal regression
    violation = [
        {"attester": "kit_fox", "proof_class": "generation", "action": "research", "timestamp": (base).isoformat() + "Z", "nonce": "v1"},
        {"attester": "kit_fox", "proof_class": "generation", "action": "fund_transfer", "timestamp": (base + timedelta(hours=1)).isoformat() + "Z", "nonce": "v2"},
        {"attester": "bro_agent", "proof_class": "witness", "action": "research", "timestamp": (base + timedelta(minutes=30)).isoformat() + "Z", "nonce": "v3"},
    ]
    
    print("\n--- Scenario 3: Scope Violation + Temporal Regression ---")
    r = detect_anomalies(violation, {"declared_scope": ["research", "delivery", "witness"]})
    print(f"Grade: {r['grade']} | Risk: {r['risk_score']} | Anomalies: {r['anomaly_count']} | → {r['recommendation']}")
    for a in r['anomalies']:
        print(f"  ⚠️ {a['type']}: {a['detail']}")
    
    # Scenario 4: Replay attack
    replay = [
        {"attester": "kit_fox", "proof_class": "payment", "timestamp": (base).isoformat() + "Z", "nonce": "SAME_NONCE"},
        {"attester": "bro_agent", "proof_class": "witness", "timestamp": (base + timedelta(hours=1)).isoformat() + "Z", "nonce": "SAME_NONCE"},
    ]
    
    print("\n--- Scenario 4: Replay Attack (Duplicate Nonce) ---")
    r = detect_anomalies(replay)
    print(f"Grade: {r['grade']} | Risk: {r['risk_score']} | Anomalies: {r['anomaly_count']} | → {r['recommendation']}")
    for a in r['anomalies']:
        print(f"  🚨 {a['type']}: {a['detail']}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = detect_anomalies(data.get("receipts", []), data.get("config", {}))
        print(json.dumps(result, indent=2))
    else:
        demo()
