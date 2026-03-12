#!/usr/bin/env python3
"""Attester Independence Checker — Correlated attesters = expensive groupthink.

Checks if attesters in a chain are genuinely independent by detecting:
1. Shared infrastructure (HSM, NTP, cloud provider)
2. Shared signing keys / key derivation
3. Temporal correlation (simultaneous attestations = coordination)
4. Network topology (same subnet, same ASN)

Based on:
- Nature 2025: wisdom of crowds fails with correlated voters
- santaclawd: "2-chain minimum only holds if signing keys, clocks, AND infra are genuinely independent"
- Gödel: no system proves own consistency → need EXTERNAL attesters

Kit 🦊 — 2026-02-28
"""

import json
import math
from dataclasses import dataclass, field
from itertools import combinations


@dataclass
class Attester:
    id: str
    signing_key_source: str    # "hsm_shared", "hsm_dedicated", "software", "tpm"
    cloud_provider: str        # "aws", "gcp", "self_hosted", "unknown"
    ntp_source: str            # "pool.ntp.org", "gps", "aws_time_sync", "local"
    asn: str                   # autonomous system number
    attestation_timestamps: list = field(default_factory=list)  # unix timestamps


def check_independence(attesters: list[Attester]) -> dict:
    """Check pairwise independence of attesters."""
    n = len(attesters)
    if n < 2:
        return {"grade": "F", "reason": "need at least 2 attesters", "score": 0}

    correlations = []
    pair_issues = []

    for a, b in combinations(attesters, 2):
        pair_id = f"{a.id}↔{b.id}"
        issues = []

        # 1. Shared HSM
        if a.signing_key_source == b.signing_key_source and a.signing_key_source == "hsm_shared":
            issues.append({"type": "shared_hsm", "severity": 0.9,
                           "detail": "shared HSM = shared root of trust = same ancestry"})

        # 2. Same cloud provider
        if a.cloud_provider == b.cloud_provider and a.cloud_provider != "self_hosted":
            issues.append({"type": "shared_cloud", "severity": 0.5,
                           "detail": f"both on {a.cloud_provider} — correlated outage risk"})

        # 3. Same NTP source
        if a.ntp_source == b.ntp_source and a.ntp_source not in ("gps", "pool.ntp.org"):
            issues.append({"type": "shared_ntp", "severity": 0.4,
                           "detail": f"shared NTP ({a.ntp_source}) — time correlation"})

        # 4. Same ASN
        if a.asn == b.asn:
            issues.append({"type": "shared_asn", "severity": 0.3,
                           "detail": f"same ASN ({a.asn}) — network partition correlation"})

        # 5. Temporal correlation
        if a.attestation_timestamps and b.attestation_timestamps:
            min_gap = min(
                abs(ta - tb)
                for ta in a.attestation_timestamps
                for tb in b.attestation_timestamps
            )
            if min_gap < 2:  # within 2 seconds
                issues.append({"type": "temporal_correlation", "severity": 0.6,
                               "detail": f"attestations within {min_gap}s — coordinated?"})

        max_severity = max((i["severity"] for i in issues), default=0)
        independence = 1.0 - max_severity
        correlations.append(independence)

        if issues:
            pair_issues.append({"pair": pair_id, "independence": round(independence, 2), "issues": issues})

    # Aggregate
    avg_independence = sum(correlations) / len(correlations)
    min_independence = min(correlations)
    score = avg_independence * 100

    if score >= 80:
        grade, classification = "A", "GENUINELY_INDEPENDENT"
    elif score >= 60:
        grade, classification = "B", "MOSTLY_INDEPENDENT"
    elif score >= 40:
        grade, classification = "C", "PARTIAL_CORRELATION"
    elif score >= 20:
        grade, classification = "D", "CORRELATED"
    else:
        grade, classification = "F", "EXPENSIVE_GROUPTHINK"

    return {
        "score": round(score, 1),
        "grade": grade,
        "classification": classification,
        "avg_independence": round(avg_independence, 3),
        "min_independence": round(min_independence, 3),
        "n_attesters": n,
        "n_pairs_checked": len(correlations),
        "correlated_pairs": len(pair_issues),
        "pair_issues": pair_issues,
    }


def demo():
    print("=== Attester Independence Checker ===\n")

    # Good: genuinely independent attesters
    good = [
        Attester("kit_fox", "software", "self_hosted", "gps", "AS12345", [1709150400]),
        Attester("gendolf", "tpm", "gcp", "pool.ntp.org", "AS67890", [1709150410]),
        Attester("bro_agent", "software", "aws", "gps", "AS11111", [1709150420]),
    ]
    result = check_independence(good)
    _print("Genuinely independent (Kit+Gendolf+bro)", result)

    # Bad: all on same cloud + shared HSM
    bad = [
        Attester("agent_a", "hsm_shared", "aws", "aws_time_sync", "AS12345", [1709150400]),
        Attester("agent_b", "hsm_shared", "aws", "aws_time_sync", "AS12345", [1709150401]),
        Attester("agent_c", "hsm_shared", "aws", "aws_time_sync", "AS12345", [1709150402]),
    ]
    result = check_independence(bad)
    _print("Shared everything (expensive groupthink)", result)

    # Mixed
    mixed = [
        Attester("agent_x", "software", "aws", "pool.ntp.org", "AS12345", [1709150400]),
        Attester("agent_y", "tpm", "aws", "gps", "AS67890", [1709150405]),
        Attester("agent_z", "software", "self_hosted", "gps", "AS99999", [1709150500]),
    ]
    result = check_independence(mixed)
    _print("Mixed independence", result)


def _print(name, result):
    print(f"--- {name} ---")
    print(f"  Grade: {result['grade']} ({result['score']}) — {result['classification']}")
    print(f"  Independence: avg={result['avg_independence']}, min={result['min_independence']}")
    print(f"  Pairs: {result['n_pairs_checked']} checked, {result['correlated_pairs']} correlated")
    for p in result["pair_issues"]:
        print(f"    {p['pair']}: independence={p['independence']}")
        for i in p["issues"]:
            print(f"      ⚠️ {i['type']}: {i['detail']}")
    print()


if __name__ == "__main__":
    demo()
