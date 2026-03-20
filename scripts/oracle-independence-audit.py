#!/usr/bin/env python3
"""
oracle-independence-audit.py — Detect correlated oracle failure in trust systems.

Problem (santaclawd 2026-03-20): "oracles are independent" is a hidden assumption.
If A, B, C share an operator/model/trust anchor, pairwise agreement = shared blindness.
Nature 2025: wisdom of crowds fails with correlated voters.

Checks:
1. Operator independence: different operators
2. Model independence: different base models  
3. Temporal correlation: synchronized attestation patterns
4. Trust anchor independence: different root of trust
5. Structural correlation: shared infrastructure

Output: independence_score (0-1) + correlation matrix + warnings
"""

import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class OracleProfile:
    """Profile of an attestation oracle."""
    oracle_id: str
    operator_id: Optional[str] = None
    model_family: Optional[str] = None
    trust_anchor: Optional[str] = None  # root CA, chain, etc.
    hosting_provider: Optional[str] = None
    attestation_timestamps: list[float] = field(default_factory=list)
    decisions: list[bool] = field(default_factory=list)  # True=approve, False=reject


@dataclass 
class CorrelationResult:
    """Pairwise correlation between two oracles."""
    oracle_a: str
    oracle_b: str
    decision_correlation: float  # -1 to 1
    temporal_correlation: float  # 0 to 1 (sync score)
    structural_overlap: int  # count of shared properties
    shared_properties: list[str]
    independence_score: float  # 0 = fully correlated, 1 = independent


@dataclass
class AuditResult:
    """Full independence audit result."""
    oracle_count: int
    pairwise_results: list[CorrelationResult]
    effective_oracle_count: float  # adjusted for correlation
    system_independence: float  # 0-1
    warnings: list[str]
    recommendation: str


def decision_correlation(a: list[bool], b: list[bool]) -> float:
    """Pearson correlation of binary decision vectors."""
    n = min(len(a), len(b))
    if n < 2:
        return 0.0
    a, b = a[:n], b[:n]
    mean_a = sum(a) / n
    mean_b = sum(b) / n
    
    cov = sum((ai - mean_a) * (bi - mean_b) for ai, bi in zip(a, b)) / n
    std_a = math.sqrt(sum((ai - mean_a)**2 for ai in a) / n)
    std_b = math.sqrt(sum((bi - mean_b)**2 for bi in b) / n)
    
    if std_a == 0 or std_b == 0:
        return 1.0 if mean_a == mean_b else 0.0
    return cov / (std_a * std_b)


def temporal_sync_score(ts_a: list[float], ts_b: list[float], window_sec: float = 60.0) -> float:
    """Fraction of attestations that are temporally synchronized within window."""
    if not ts_a or not ts_b:
        return 0.0
    
    synced = 0
    total = min(len(ts_a), len(ts_b))
    for ta in ts_a[:total]:
        if any(abs(ta - tb) < window_sec for tb in ts_b):
            synced += 1
    
    return synced / total if total > 0 else 0.0


def structural_overlap(a: OracleProfile, b: OracleProfile) -> tuple[int, list[str]]:
    """Count shared structural properties between oracles."""
    shared = []
    if a.operator_id and a.operator_id == b.operator_id:
        shared.append(f"OPERATOR:{a.operator_id}")
    if a.model_family and a.model_family == b.model_family:
        shared.append(f"MODEL:{a.model_family}")
    if a.trust_anchor and a.trust_anchor == b.trust_anchor:
        shared.append(f"TRUST_ANCHOR:{a.trust_anchor}")
    if a.hosting_provider and a.hosting_provider == b.hosting_provider:
        shared.append(f"HOSTING:{a.hosting_provider}")
    return len(shared), shared


def pairwise_independence(a: OracleProfile, b: OracleProfile) -> CorrelationResult:
    """Compute pairwise independence score."""
    dec_corr = decision_correlation(a.decisions, b.decisions)
    temp_corr = temporal_sync_score(a.attestation_timestamps, b.attestation_timestamps)
    struct_count, struct_shared = structural_overlap(a, b)
    
    # Independence = 1 - max(correlations)
    # Structural overlap is heavily weighted — shared operator is near-fatal
    struct_penalty = min(1.0, struct_count * 0.4)  # each shared property = 0.4 penalty
    decision_penalty = max(0, dec_corr) * 0.3  # positive correlation = penalty
    temporal_penalty = temp_corr * 0.2
    
    independence = max(0.0, 1.0 - struct_penalty - decision_penalty - temporal_penalty)
    
    return CorrelationResult(
        oracle_a=a.oracle_id,
        oracle_b=b.oracle_id,
        decision_correlation=dec_corr,
        temporal_correlation=temp_corr,
        structural_overlap=struct_count,
        shared_properties=struct_shared,
        independence_score=independence
    )


def audit_independence(oracles: list[OracleProfile]) -> AuditResult:
    """Full independence audit of oracle set."""
    n = len(oracles)
    warnings = []
    
    if n < 2:
        return AuditResult(
            oracle_count=n, pairwise_results=[], effective_oracle_count=float(n),
            system_independence=0.0, warnings=["INSUFFICIENT: need at least 2 oracles"],
            recommendation="Cannot assess independence with fewer than 2 oracles."
        )
    
    # Pairwise analysis
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            pairs.append(pairwise_independence(oracles[i], oracles[j]))
    
    # Warnings
    for p in pairs:
        if p.structural_overlap > 0:
            warnings.append(f"STRUCTURAL: {p.oracle_a}↔{p.oracle_b} share {', '.join(p.shared_properties)}")
        if p.decision_correlation > 0.9:
            warnings.append(f"DECISION: {p.oracle_a}↔{p.oracle_b} correlation={p.decision_correlation:.2f} (near-identical decisions)")
        if p.temporal_correlation > 0.8:
            warnings.append(f"TEMPORAL: {p.oracle_a}↔{p.oracle_b} sync={p.temporal_correlation:.2f} (synchronized timing)")
    
    # Effective oracle count (adjusted for correlation)
    avg_independence = sum(p.independence_score for p in pairs) / len(pairs)
    # Effective count: n oracles with avg independence i ≈ n * i oracles truly independent
    effective = max(1.0, n * avg_independence)
    
    # System independence
    system_score = avg_independence
    
    # Recommendation
    if system_score > 0.7:
        rec = f"INDEPENDENT: {effective:.1f} effective oracles from {n} actual. Safe for quorum decisions."
    elif system_score > 0.4:
        rec = f"PARTIALLY_CORRELATED: {effective:.1f} effective from {n}. Add structurally diverse oracles."
    else:
        rec = f"CORRELATED: {effective:.1f} effective from {n}. Consensus is illusory — shared blindness likely."
    
    return AuditResult(
        oracle_count=n, pairwise_results=pairs, effective_oracle_count=effective,
        system_independence=system_score, warnings=warnings, recommendation=rec
    )


def demo():
    """Demo: independent vs correlated oracle sets."""
    import time
    now = time.time()
    
    # Scenario 1: Truly independent oracles
    independent = [
        OracleProfile("kit_fox", "ilya", "opus-4.6", "agentmail", "hetzner",
                      [now, now+100, now+200], [True, True, False]),
        OracleProfile("bro_agent", "paylock_team", "gpt-5", "solana", "aws",
                      [now+30, now+130, now+250], [True, True, False]),
        OracleProfile("funwolf", "indie_dev", "gemini-3", "smtp", "digitalocean",
                      [now+60, now+160, now+280], [True, False, False]),
    ]
    
    # Scenario 2: Same-operator correlated oracles
    correlated = [
        OracleProfile("oracle_a", "same_corp", "opus-4.6", "same_ca", "aws",
                      [now, now+100, now+200], [True, True, True]),
        OracleProfile("oracle_b", "same_corp", "opus-4.6", "same_ca", "aws",
                      [now+2, now+102, now+202], [True, True, True]),
        OracleProfile("oracle_c", "same_corp", "opus-4.6", "same_ca", "aws",
                      [now+1, now+101, now+201], [True, True, True]),
    ]
    
    # Scenario 3: Mixed — some correlation
    mixed = [
        OracleProfile("alpha", "team_a", "opus-4.6", "agentmail", "hetzner",
                      [now, now+100, now+200], [True, True, False]),
        OracleProfile("beta", "team_b", "opus-4.6", "smtp", "aws",
                      [now+10, now+110, now+210], [True, True, False]),
        OracleProfile("gamma", "team_c", "gemini-3", "solana", "gcp",
                      [now+50, now+150, now+300], [True, False, True]),
    ]
    
    for label, oracles in [("INDEPENDENT", independent), ("CORRELATED", correlated), ("MIXED", mixed)]:
        result = audit_independence(oracles)
        print(f"\n{'='*60}")
        print(f"  {label} ORACLE SET")
        print(f"{'='*60}")
        print(f"  Oracles:           {result.oracle_count}")
        print(f"  Effective count:   {result.effective_oracle_count:.1f}")
        print(f"  System score:      {result.system_independence:.2f}")
        print(f"  Recommendation:    {result.recommendation}")
        if result.warnings:
            print(f"  Warnings:")
            for w in result.warnings:
                print(f"    ⚠️  {w}")
        print(f"  Pairwise:")
        for p in result.pairwise_results:
            print(f"    {p.oracle_a}↔{p.oracle_b}: independence={p.independence_score:.2f}, "
                  f"decision_corr={p.decision_correlation:.2f}, structural={p.structural_overlap}")


if __name__ == "__main__":
    demo()
