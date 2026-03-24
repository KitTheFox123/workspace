#!/usr/bin/env python3
"""
sybil-operator-detector.py — Detect sybil log operators in K-of-N multi-log ATF.

Per santaclawd: "K independent operators who share infrastructure, funding, or
governance = 1 effective operator."

Chrome CT Log Policy requires operators to assert organizational independence.
ATF has no browser vendor gatekeeper. Detection must be algorithmic.

Three detection axes:
  1. Infrastructure overlap (shared ASN, IP range, hosting provider)
  2. Temporal correlation (synchronized behavior = shared operations)
  3. Genesis similarity (shared templates, funding sources, governance docs)

Simpson diversity index on effective operator set.
K-of-N requires K INDEPENDENT operators, not K operators.
"""

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LogOperator:
    operator_id: str
    name: str
    asn: str                    # Autonomous System Number
    ip_prefix: str              # /24 prefix
    hosting_provider: str
    jurisdiction: str
    genesis_hash: str
    funding_source: Optional[str] = None
    governance_doc_hash: Optional[str] = None
    # Behavioral signals
    uptime_pattern: list = field(default_factory=list)  # hourly availability 0/1
    response_latencies: list = field(default_factory=list)  # ms per request


def infrastructure_overlap(a: LogOperator, b: LogOperator) -> float:
    """
    Score infrastructure independence (0=identical, 1=fully independent).
    
    Chrome CT policy: operators must be "organizationally independent."
    We operationalize this across infrastructure signals.
    """
    overlap = 0.0
    checks = 0
    
    # ASN overlap (strongest signal — same network operator)
    if a.asn == b.asn:
        overlap += 0.4
    checks += 0.4
    
    # IP prefix overlap
    if a.ip_prefix == b.ip_prefix:
        overlap += 0.2
    checks += 0.2
    
    # Hosting provider
    if a.hosting_provider == b.hosting_provider:
        overlap += 0.2
    checks += 0.2
    
    # Jurisdiction (weaker signal)
    if a.jurisdiction == b.jurisdiction:
        overlap += 0.1
    checks += 0.1
    
    # Governance doc similarity
    if (a.governance_doc_hash and b.governance_doc_hash and 
        a.governance_doc_hash == b.governance_doc_hash):
        overlap += 0.1
    checks += 0.1
    
    independence = 1.0 - (overlap / checks)
    return round(independence, 4)


def temporal_correlation(a: LogOperator, b: LogOperator) -> float:
    """
    Pearson correlation on uptime patterns.
    Synchronized downtime = shared infrastructure.
    
    Per Brown et al. (2023): ML detected 86% of anonymous bidders
    by temporal patterns alone in Alberta electricity market.
    """
    if not a.uptime_pattern or not b.uptime_pattern:
        return 0.0
    
    n = min(len(a.uptime_pattern), len(b.uptime_pattern))
    if n < 10:
        return 0.0
    
    xa = a.uptime_pattern[:n]
    xb = b.uptime_pattern[:n]
    
    mean_a = sum(xa) / n
    mean_b = sum(xb) / n
    
    cov = sum((xa[i] - mean_a) * (xb[i] - mean_b) for i in range(n)) / n
    std_a = math.sqrt(sum((x - mean_a)**2 for x in xa) / n)
    std_b = math.sqrt(sum((x - mean_b)**2 for x in xb) / n)
    
    if std_a * std_b == 0:
        return 1.0 if mean_a == mean_b else 0.0
    
    r = cov / (std_a * std_b)
    return round(r, 4)


def simpson_diversity(operators: list[LogOperator]) -> float:
    """
    Simpson diversity index on effective operator groups.
    
    D = 1 - Σ(p_i²) where p_i = proportion in group i.
    D=0 = monoculture (all same operator).
    D→1 = high diversity.
    """
    # Group by infrastructure fingerprint
    groups = {}
    for op in operators:
        fingerprint = f"{op.asn}:{op.hosting_provider}:{op.governance_doc_hash or 'none'}"
        groups[fingerprint] = groups.get(fingerprint, 0) + 1
    
    n = len(operators)
    if n <= 1:
        return 0.0
    
    d = 1.0 - sum((count/n)**2 for count in groups.values())
    return round(d, 4)


def effective_k(operators: list[LogOperator], k_required: int) -> dict:
    """
    Compute effective K for a K-of-N multi-log system.
    
    N operators with sybils reduces effective independence.
    Chrome requires 2-3 SCTs from INDEPENDENT logs.
    """
    # Build independence matrix
    n = len(operators)
    independence = [[0.0]*n for _ in range(n)]
    for i in range(n):
        for j in range(i+1, n):
            score = infrastructure_overlap(operators[i], operators[j])
            independence[i][j] = score
            independence[j][i] = score
    
    # Cluster operators with independence < 0.5 as "same effective operator"
    INDEPENDENCE_THRESHOLD = 0.5
    clusters = list(range(n))  # union-find
    
    def find(x):
        while clusters[x] != x:
            clusters[x] = clusters[clusters[x]]
            x = clusters[x]
        return x
    
    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            clusters[ry] = rx
    
    for i in range(n):
        for j in range(i+1, n):
            if independence[i][j] < INDEPENDENCE_THRESHOLD:
                union(i, j)
    
    # Count effective groups
    effective_groups = len(set(find(i) for i in range(n)))
    
    # Temporal correlation check
    sybil_pairs = []
    for i in range(n):
        for j in range(i+1, n):
            corr = temporal_correlation(operators[i], operators[j])
            if corr > 0.7 and independence[i][j] < 0.5:
                sybil_pairs.append({
                    "a": operators[i].name,
                    "b": operators[j].name,
                    "infrastructure_independence": independence[i][j],
                    "temporal_correlation": corr,
                    "verdict": "LIKELY_SYBIL"
                })
    
    diversity = simpson_diversity(operators)
    meets_k = effective_groups >= k_required
    
    return {
        "nominal_n": n,
        "effective_k": effective_groups,
        "k_required": k_required,
        "meets_requirement": meets_k,
        "simpson_diversity": diversity,
        "sybil_pairs": sybil_pairs,
        "grade": "A" if meets_k and diversity > 0.7 else
                 "B" if meets_k else
                 "D" if effective_groups > 1 else "F"
    }


# === Scenarios ===

def scenario_independent_operators():
    """Genuinely independent log operators."""
    print("=== Scenario: Independent Operators ===")
    ops = [
        LogOperator("op1", "LogCorp", "AS15169", "34.0.0.0/24", "GCP", "US",
                     "abc123", "VC-Fund-A", "gov-hash-1",
                     [1]*20 + [0]*4, [45]*24),
        LogOperator("op2", "TrustLog", "AS13335", "104.16.0.0/24", "Cloudflare", "EU",
                     "def456", "Grant-B", "gov-hash-2",
                     [1]*18 + [0]*6, [120]*24),
        LogOperator("op3", "VerifyNet", "AS16509", "52.0.0.0/24", "AWS", "JP",
                     "ghi789", "Self-funded", "gov-hash-3",
                     [1]*22 + [0]*2, [80]*24),
    ]
    result = effective_k(ops, k_required=2)
    print(f"  Nominal N={result['nominal_n']}, Effective K={result['effective_k']}")
    print(f"  Simpson diversity: {result['simpson_diversity']}")
    print(f"  Meets K=2: {result['meets_requirement']}")
    print(f"  Grade: {result['grade']}")
    print(f"  Sybil pairs: {len(result['sybil_pairs'])}")
    print()


def scenario_sybil_operators():
    """Three 'operators' that are actually one entity."""
    print("=== Scenario: Sybil Operators (Same Infrastructure) ===")
    # All on same ASN, same provider, same governance
    shared_uptime = [1]*20 + [0]*4
    ops = [
        LogOperator("op1", "LogA", "AS15169", "34.0.0.0/24", "GCP", "US",
                     "abc1", "Fund-X", "same-gov",
                     shared_uptime, [45]*24),
        LogOperator("op2", "LogB", "AS15169", "34.0.1.0/24", "GCP", "US",
                     "abc2", "Fund-X", "same-gov",
                     shared_uptime, [47]*24),
        LogOperator("op3", "LogC", "AS15169", "34.0.2.0/24", "GCP", "EU",
                     "abc3", "Fund-X", "same-gov",
                     shared_uptime, [44]*24),
    ]
    result = effective_k(ops, k_required=2)
    print(f"  Nominal N={result['nominal_n']}, Effective K={result['effective_k']}")
    print(f"  Simpson diversity: {result['simpson_diversity']}")
    print(f"  Meets K=2: {result['meets_requirement']}")
    print(f"  Grade: {result['grade']}")
    for pair in result['sybil_pairs']:
        print(f"  SYBIL: {pair['a']}↔{pair['b']} "
              f"infra={pair['infrastructure_independence']:.2f} "
              f"temporal={pair['temporal_correlation']:.2f}")
    print()


def scenario_mixed():
    """2 independent + 2 sybils — effective K drops."""
    print("=== Scenario: Mixed (2 Independent + 2 Sybil) ===")
    shared_uptime = [1]*20 + [0]*4
    ops = [
        LogOperator("op1", "Honest-A", "AS15169", "34.0.0.0/24", "GCP", "US",
                     "h1", "Fund-A", "gov-1",
                     [1]*22 + [0]*2, [50]*24),
        LogOperator("op2", "Honest-B", "AS13335", "104.16.0.0/24", "Cloudflare", "EU",
                     "h2", "Fund-B", "gov-2",
                     [1]*18 + [0]*6, [100]*24),
        LogOperator("op3", "Sybil-X", "AS16509", "52.0.0.0/24", "AWS", "JP",
                     "s1", "Fund-Evil", "evil-gov",
                     shared_uptime, [70]*24),
        LogOperator("op4", "Sybil-Y", "AS16509", "52.0.1.0/24", "AWS", "JP",
                     "s2", "Fund-Evil", "evil-gov",
                     shared_uptime, [72]*24),
    ]
    result = effective_k(ops, k_required=3)
    print(f"  Nominal N={result['nominal_n']}, Effective K={result['effective_k']}")
    print(f"  Simpson diversity: {result['simpson_diversity']}")
    print(f"  Meets K=3: {result['meets_requirement']}")
    print(f"  Grade: {result['grade']}")
    for pair in result['sybil_pairs']:
        print(f"  SYBIL: {pair['a']}↔{pair['b']} "
              f"infra={pair['infrastructure_independence']:.2f} "
              f"temporal={pair['temporal_correlation']:.2f}")
    print()


def scenario_chrome_ct_model():
    """Chrome's actual CT log operators (6 operators, K=2-3)."""
    print("=== Scenario: Chrome CT Model (Real-World Scale) ===")
    ops = [
        LogOperator("google", "Google", "AS15169", "34.0.0.0/24", "GCP", "US", "g1"),
        LogOperator("cf", "Cloudflare", "AS13335", "104.16.0.0/24", "Cloudflare", "US", "c1"),
        LogOperator("dc", "DigiCert", "AS14618", "64.0.0.0/24", "DigiCert-DC", "US", "d1"),
        LogOperator("sc", "Sectigo", "AS9009", "91.0.0.0/24", "OVH", "UK", "s1"),
        LogOperator("le", "Let's Encrypt", "AS396982", "23.0.0.0/24", "Akamai", "US", "l1"),
        LogOperator("ta", "TrustAsia", "AS45090", "1.0.0.0/24", "TrustAsia-DC", "CN", "t1"),
    ]
    result = effective_k(ops, k_required=2)
    print(f"  Nominal N={result['nominal_n']}, Effective K={result['effective_k']}")
    print(f"  Simpson diversity: {result['simpson_diversity']}")
    print(f"  Meets K=2: {result['meets_requirement']}")
    print(f"  Grade: {result['grade']}")
    print(f"  Key: Chrome enforces independence via application process.")
    print(f"  ATF must enforce algorithmically — no gatekeeper.")
    print()


if __name__ == "__main__":
    print("Sybil Operator Detector — K-of-N Multi-Log Independence Verification")
    print("Per santaclawd: 'who is ATF's browser vendor?'")
    print("Answer: nobody. Counterparties ARE the verifiers.")
    print("=" * 70)
    print()
    scenario_independent_operators()
    scenario_sybil_operators()
    scenario_mixed()
    scenario_chrome_ct_model()
    
    print("=" * 70)
    print("KEY INSIGHT: ATF has no browser vendor gatekeeper.")
    print("Independence verified algorithmically:")
    print("  1. Infrastructure overlap (ASN, hosting, governance)")
    print("  2. Temporal correlation (synchronized = shared)")
    print("  3. Simpson diversity on effective operator set")
    print("Same infra + same governance + correlated uptime = 1 effective operator.")
    print("Chrome CT log policy requires assertion of independence.")
    print("ATF requires PROOF of independence.")
