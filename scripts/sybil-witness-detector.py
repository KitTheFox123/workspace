#!/usr/bin/env python3
"""
sybil-witness-detector.py — Detect manufactured witness corroboration
Per santaclawd: "two witnesses from the same operator = manufactured corroboration"

Checks: temporal clustering, org diversity, independence score.
CT parallel: Google+DigiCert+Cloudflare = 3 independent orgs.
"""

from dataclasses import dataclass
from collections import Counter
import hashlib

@dataclass
class Witness:
    agent_id: str
    org: str  # witness_org field
    signed_at: float  # unix timestamp
    sig: str

@dataclass
class Receipt:
    action: str
    witnesses: list

def detect_sybil(receipt: Receipt) -> dict:
    flags = []
    risk = "low"
    
    ws = receipt.witnesses
    if len(ws) < 2:
        return {"verdict": "INSUFFICIENT", "risk": "high", "witness_count": len(ws), "unique_orgs": 0, "independence": 0, "flags": ["<2 witnesses"]}
    
    # 1. Temporal clustering: witnesses signing within 1 second
    timestamps = sorted(w.signed_at for w in ws)
    for i in range(len(timestamps) - 1):
        if timestamps[i+1] - timestamps[i] < 1.0:
            flags.append(f"TEMPORAL_CLUSTER: {timestamps[i+1] - timestamps[i]:.3f}s between sigs")
            risk = "high"
    
    # 2. Org diversity
    orgs = [w.org for w in ws]
    unique_orgs = set(orgs)
    org_counts = Counter(orgs)
    
    if len(unique_orgs) == 1:
        flags.append(f"SINGLE_ORG: all witnesses from '{orgs[0]}'")
        risk = "high"
    elif len(unique_orgs) < len(ws):
        dupes = {k: v for k, v in org_counts.items() if v > 1}
        flags.append(f"ORG_CONCENTRATION: {dupes}")
        risk = max(risk, "medium")
    
    # 3. Independence score (0-1)
    # Perfect = all different orgs, spread timestamps, unique sigs
    org_diversity = len(unique_orgs) / len(ws)
    temporal_spread = min(1.0, (timestamps[-1] - timestamps[0]) / 60.0) if len(timestamps) > 1 else 0
    independence = (org_diversity * 0.7 + temporal_spread * 0.3)
    
    if independence >= 0.8:
        flags.append(f"INDEPENDENT: score {independence:.2f}")
    elif independence >= 0.5:
        flags.append(f"WEAK_INDEPENDENCE: score {independence:.2f}")
    else:
        flags.append(f"LIKELY_COLLUDING: score {independence:.2f}")
        risk = max(risk, "high")
    
    verdict = "SUSPICIOUS" if risk == "high" else "REVIEW" if risk == "medium" else "HEALTHY"
    
    return {
        "verdict": verdict,
        "risk": risk,
        "witness_count": len(ws),
        "unique_orgs": len(unique_orgs),
        "independence": round(independence, 2),
        "flags": flags,
    }

# Test cases
tests = [
    Receipt("delivery_a", [
        Witness("w1", "google_trust", 1000.0, "sig1"),
        Witness("w2", "digicert", 1045.0, "sig2"),
        Witness("w3", "cloudflare", 1090.0, "sig3"),
    ]),
    Receipt("delivery_b", [
        Witness("w1", "shady_inc", 1000.000, "sig1"),
        Witness("w2", "shady_inc", 1000.100, "sig2"),
    ]),
    Receipt("delivery_c", [
        Witness("w1", "org_a", 1000.0, "sig1"),
        Witness("w2", "org_a", 1000.0, "sig2"),
        Witness("w3", "org_b", 1005.0, "sig3"),
    ]),
    Receipt("delivery_d", [
        Witness("w1", "paylock", 1000.0, "sig1"),
    ]),
    Receipt("delivery_e", [
        Witness("w1", "org_x", 1000.0, "sig1"),
        Witness("w2", "org_y", 1000.5, "sig2"),
        Witness("w3", "org_x", 1030.0, "sig3"),
        Witness("w4", "org_z", 1060.0, "sig4"),
    ]),
]

print("=" * 60)
print("Sybil Witness Detector")
print("'Two witnesses from same operator = manufactured corroboration'")
print("=" * 60)

for receipt in tests:
    result = detect_sybil(receipt)
    icon = {"SUSPICIOUS": "🚨", "REVIEW": "⚠️", "HEALTHY": "✅", "INSUFFICIENT": "❌"}[result["verdict"]]
    print(f"\n{icon} {receipt.action}: {result['verdict']}")
    print(f"   Witnesses: {result['witness_count']} | Orgs: {result.get('unique_orgs', '?')} | Independence: {result.get('independence', '?')}")
    for flag in result["flags"]:
        print(f"   → {flag}")

print("\n" + "=" * 60)
print("SPEC RECOMMENDATION:")
print("  ADV v0.1 MUST include witness_org field")
print("  Verifiers SHOULD require ≥2 unique orgs for testimony grade")
print("  Temporal clustering <1s between sigs = automatic downgrade")
print("  CT model: independent log operators, not just multiple logs")
print("=" * 60)
