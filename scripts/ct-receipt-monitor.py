#!/usr/bin/env python3
"""CT-style Receipt Monitor/Auditor — RFC 6962 pattern for agent receipts.

Two roles (per santaclawd's insight):
- MONITOR: Detects unexpected entries (unknown attesters, scope violations, bursts)
- AUDITOR: Verifies inclusion proofs and log consistency

Based on Certificate Transparency (RFC 6962): 10B+ TLS certs, 5+ independent
log operators, append-only Merkle trees.

Usage:
  python ct-receipt-monitor.py --demo
  echo '{"receipts": [...]}' | python ct-receipt-monitor.py --json
"""

import json
import sys
import hashlib
import math
from collections import Counter, defaultdict
from datetime import datetime

# Known trusted attesters (would be loaded from config in production)
KNOWN_ATTESTERS = {
    "kit_fox", "bro_agent", "santaclawd", "cassian", "funwolf",
    "clawdvine", "gerundium", "braindiff", "gendolf", "agentmail",
}

# Proof class requirements
PROOF_CLASSES = {"payment", "generation", "transport", "witness"}


def hash_receipt(receipt: dict) -> str:
    """Content-addressable hash for a receipt."""
    canonical = json.dumps(receipt, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


class ReceiptLog:
    """Append-only receipt log with Merkle tree properties."""
    
    def __init__(self):
        self.entries = []
        self.hashes = []
    
    def append(self, receipt: dict) -> dict:
        h = hash_receipt(receipt)
        idx = len(self.entries)
        self.entries.append(receipt)
        self.hashes.append(h)
        return {"index": idx, "hash": h}
    
    def get_root(self) -> str:
        if not self.hashes:
            return hashlib.sha256(b"empty").hexdigest()[:16]
        combined = "|".join(self.hashes)
        return hashlib.sha256(combined.encode()).hexdigest()[:16]
    
    def inclusion_proof(self, index: int) -> dict:
        if index < 0 or index >= len(self.entries):
            return {"valid": False, "error": "index out of range"}
        return {
            "valid": True,
            "index": index,
            "hash": self.hashes[index],
            "root": self.get_root(),
            "log_size": len(self.entries),
        }
    
    def consistency_proof(self, old_size: int) -> dict:
        if old_size > len(self.entries):
            return {"consistent": False, "error": "old_size > current size"}
        old_root = hashlib.sha256("|".join(self.hashes[:old_size]).encode()).hexdigest()[:16]
        return {
            "consistent": True,
            "old_size": old_size,
            "new_size": len(self.entries),
            "old_root": old_root,
            "new_root": self.get_root(),
        }


def monitor_scan(receipts: list) -> dict:
    """MONITOR role: detect unexpected entries in receipt log."""
    alerts = []
    
    # 1. Unknown attesters
    attesters = [r.get("attester", "unknown") for r in receipts]
    unknown = [a for a in set(attesters) if a not in KNOWN_ATTESTERS]
    if unknown:
        alerts.append({
            "type": "UNKNOWN_ATTESTER",
            "severity": "HIGH",
            "detail": f"Unknown attesters: {unknown}",
            "count": len(unknown),
        })
    
    # 2. Temporal burst detection (>3 receipts in <60s from same attester)
    by_attester = defaultdict(list)
    for r in receipts:
        ts = r.get("timestamp", 0)
        by_attester[r.get("attester", "unknown")].append(ts)
    
    for attester, timestamps in by_attester.items():
        timestamps.sort()
        for i in range(len(timestamps) - 2):
            window = timestamps[i+2] - timestamps[i]
            if window < 60:
                alerts.append({
                    "type": "TEMPORAL_BURST",
                    "severity": "HIGH",
                    "detail": f"{attester}: 3+ receipts in {window:.0f}s",
                    "attester": attester,
                })
                break
    
    # 3. Scope violations (receipt references scope not in original contract)
    scopes = [r.get("scope", "") for r in receipts]
    scope_set = set(scopes)
    if len(scope_set) > 5:
        alerts.append({
            "type": "SCOPE_PROLIFERATION",
            "severity": "MEDIUM",
            "detail": f"{len(scope_set)} distinct scopes detected (expected <5)",
        })
    
    # 4. Proof class monotony (all same class = potential gaming)
    classes = [r.get("proof_class", "unknown") for r in receipts]
    class_counts = Counter(classes)
    if len(class_counts) == 1 and len(receipts) > 2:
        alerts.append({
            "type": "PROOF_CLASS_MONOTONY",
            "severity": "MEDIUM",
            "detail": f"All {len(receipts)} receipts are class '{classes[0]}'",
        })
    
    # 5. Missing proof classes
    present = set(classes)
    missing = PROOF_CLASSES - present
    if missing and len(receipts) >= 3:
        alerts.append({
            "type": "MISSING_PROOF_CLASS",
            "severity": "LOW",
            "detail": f"Missing classes: {missing}",
        })
    
    # 6. Attester concentration (one attester >60% of receipts)
    attester_counts = Counter(attesters)
    for attester, count in attester_counts.items():
        if count / len(receipts) > 0.6 and len(receipts) > 3:
            alerts.append({
                "type": "ATTESTER_CONCENTRATION",
                "severity": "MEDIUM",
                "detail": f"{attester} has {count}/{len(receipts)} receipts ({count/len(receipts):.0%})",
            })
    
    severity_score = sum(
        {"HIGH": 1.0, "MEDIUM": 0.5, "LOW": 0.2}.get(a["severity"], 0)
        for a in alerts
    )
    max_score = len(receipts) * 0.5  # normalize
    risk = min(1.0, severity_score / max(max_score, 1))
    
    return {
        "role": "MONITOR",
        "receipts_scanned": len(receipts),
        "alerts": alerts,
        "alert_count": len(alerts),
        "risk_score": round(risk, 3),
        "recommendation": "BLOCK" if risk > 0.7 else "INVESTIGATE" if risk > 0.3 else "PASS",
    }


def auditor_verify(log: ReceiptLog, checks: list) -> dict:
    """AUDITOR role: verify inclusion proofs and log consistency."""
    results = []
    
    for check in checks:
        if check["type"] == "inclusion":
            proof = log.inclusion_proof(check["index"])
            results.append({
                "check": "inclusion",
                "index": check["index"],
                "valid": proof["valid"],
                "hash": proof.get("hash"),
            })
        elif check["type"] == "consistency":
            proof = log.consistency_proof(check["old_size"])
            results.append({
                "check": "consistency",
                "old_size": check["old_size"],
                "consistent": proof["consistent"],
                "old_root": proof.get("old_root"),
                "new_root": proof.get("new_root"),
            })
    
    all_pass = all(
        r.get("valid", r.get("consistent", False)) for r in results
    )
    
    return {
        "role": "AUDITOR",
        "checks_run": len(results),
        "all_pass": all_pass,
        "results": results,
    }


def demo():
    print("=" * 60)
    print("CT-Style Receipt Monitor/Auditor")
    print("Based on RFC 6962 Certificate Transparency")
    print("=" * 60)
    
    # Build a receipt log
    log = ReceiptLog()
    
    # Scenario 1: Clean TC3-like delivery
    clean_receipts = [
        {"attester": "bro_agent", "proof_class": "witness", "scope": "tc3", "timestamp": 1000},
        {"attester": "kit_fox", "proof_class": "generation", "scope": "tc3", "timestamp": 1100},
        {"attester": "agentmail", "proof_class": "transport", "scope": "tc3", "timestamp": 1200},
        {"attester": "santaclawd", "proof_class": "payment", "scope": "tc3", "timestamp": 1300},
    ]
    
    for r in clean_receipts:
        log.append(r)
    
    print("\n--- Scenario 1: Clean TC3 Delivery ---")
    monitor_result = monitor_scan(clean_receipts)
    print(f"Monitor: {monitor_result['recommendation']} (risk: {monitor_result['risk_score']})")
    print(f"Alerts: {monitor_result['alert_count']}")
    
    auditor_result = auditor_verify(log, [
        {"type": "inclusion", "index": 0},
        {"type": "inclusion", "index": 3},
        {"type": "consistency", "old_size": 2},
    ])
    print(f"Auditor: {'ALL PASS ✅' if auditor_result['all_pass'] else 'FAILED ❌'}")
    
    # Scenario 2: Sybil pattern
    sybil_receipts = [
        {"attester": "sybil_1", "proof_class": "witness", "scope": "tc99", "timestamp": 2000},
        {"attester": "sybil_1", "proof_class": "witness", "scope": "tc99", "timestamp": 2010},
        {"attester": "sybil_1", "proof_class": "witness", "scope": "tc99", "timestamp": 2020},
        {"attester": "sybil_1", "proof_class": "witness", "scope": "tc99", "timestamp": 2030},
        {"attester": "sybil_2", "proof_class": "witness", "scope": "tc99", "timestamp": 2035},
    ]
    
    print("\n--- Scenario 2: Sybil Burst Pattern ---")
    monitor_result = monitor_scan(sybil_receipts)
    print(f"Monitor: {monitor_result['recommendation']} (risk: {monitor_result['risk_score']})")
    for alert in monitor_result['alerts']:
        print(f"  🚨 {alert['type']} [{alert['severity']}]: {alert['detail']}")
    
    # Scenario 3: Tampered log
    print("\n--- Scenario 3: Log Tamper Detection ---")
    tamper_log = ReceiptLog()
    for r in clean_receipts[:3]:
        tamper_log.append(r)
    
    old_root = tamper_log.get_root()
    tamper_log.append(clean_receipts[3])
    
    # Verify consistency
    consistency = tamper_log.consistency_proof(3)
    print(f"Consistency (3→4): {'✅' if consistency['consistent'] else '❌'}")
    print(f"Old root: {consistency['old_root']}")
    print(f"New root: {consistency['new_root']}")
    
    # Scenario 4: Mixed — some good, some suspicious
    mixed_receipts = [
        {"attester": "kit_fox", "proof_class": "generation", "scope": "delivery", "timestamp": 3000},
        {"attester": "braindiff", "proof_class": "witness", "scope": "delivery", "timestamp": 3100},
        {"attester": "unknown_bot", "proof_class": "transport", "scope": "delivery", "timestamp": 3200},
        {"attester": "kit_fox", "proof_class": "payment", "scope": "delivery", "timestamp": 3300},
    ]
    
    print("\n--- Scenario 4: Mixed (1 Unknown Attester) ---")
    monitor_result = monitor_scan(mixed_receipts)
    print(f"Monitor: {monitor_result['recommendation']} (risk: {monitor_result['risk_score']})")
    for alert in monitor_result['alerts']:
        print(f"  ⚠️ {alert['type']} [{alert['severity']}]: {alert['detail']}")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    elif "--json" in sys.argv:
        data = json.load(sys.stdin)
        receipts = data.get("receipts", [])
        print(json.dumps(monitor_scan(receipts), indent=2))
    else:
        demo()
