#!/usr/bin/env python3
"""issuer-concentration-monitor.py — Detect issuer monoculture risk.

Measures concentration of trust across attestation issuers using
Herfindahl-Hirschman Index (HHI) and Gini coefficient. Flags when
a single issuer dominates, creating correlated failure risk.

Inspired by DigiNotar (2011) and Symantec (2018) CA collapses.
CT requires 2+ independent SCTs — this tool enforces equivalent
diversity requirements for agent attestation systems.

Usage:
    python3 issuer-concentration-monitor.py [--demo]
"""

import argparse
import json
from dataclasses import dataclass, asdict
from typing import List, Dict
from datetime import datetime, timezone


@dataclass
class IssuerProfile:
    """An attestation issuer with metadata."""
    issuer_id: str
    provider: str  # Infrastructure provider
    model_family: str  # LLM family if applicable
    attestation_count: int
    share: float  # Market share (0-1)


@dataclass
class ConcentrationReport:
    """Issuer concentration analysis."""
    timestamp: str
    issuer_count: int
    total_attestations: int
    hhi: float  # Herfindahl-Hirschman Index (0-10000)
    hhi_grade: str
    gini: float  # Gini coefficient (0-1)
    top_issuer_share: float
    effective_issuers: float  # 1/HHI * 10000
    min_independent_issuers: int  # CT-inspired minimum
    meets_ct_standard: bool
    correlated_pairs: List[Dict]
    recommendation: str


def hhi(shares: List[float]) -> float:
    """Herfindahl-Hirschman Index. 10000 = monopoly, <1500 = competitive."""
    return sum(s * s * 10000 for s in shares)


def gini(values: List[float]) -> float:
    """Gini coefficient. 0 = perfect equality, 1 = total inequality."""
    n = len(values)
    if n == 0:
        return 0.0
    sorted_vals = sorted(values)
    total = sum(sorted_vals)
    if total == 0:
        return 0.0
    cumulative = 0
    gini_sum = 0
    for i, v in enumerate(sorted_vals):
        cumulative += v
        gini_sum += (2 * (i + 1) - n - 1) * v
    return gini_sum / (n * total)


def grade_hhi(h: float) -> str:
    """Grade HHI per DOJ merger guidelines."""
    if h < 1500:
        return "A (competitive)"
    elif h < 2500:
        return "B (moderate concentration)"
    elif h < 5000:
        return "C (high concentration)"
    elif h < 8000:
        return "D (near-monopoly)"
    else:
        return "F (monopoly)"


def find_correlated_pairs(issuers: List[IssuerProfile]) -> List[Dict]:
    """Find issuers sharing infrastructure or model family."""
    pairs = []
    for i, a in enumerate(issuers):
        for b in issuers[i+1:]:
            reasons = []
            if a.provider == b.provider:
                reasons.append(f"shared provider: {a.provider}")
            if a.model_family == b.model_family:
                reasons.append(f"shared model: {a.model_family}")
            if reasons:
                combined_share = a.share + b.share
                pairs.append({
                    "issuers": [a.issuer_id, b.issuer_id],
                    "correlation_reason": ", ".join(reasons),
                    "combined_share": round(combined_share, 3),
                    "risk": "HIGH" if combined_share > 0.5 else "MEDIUM"
                })
    return pairs


def analyze(issuers: List[IssuerProfile]) -> ConcentrationReport:
    """Full concentration analysis."""
    shares = [i.share for i in issuers]
    h = hhi(shares)
    g = gini([i.attestation_count for i in issuers])
    top_share = max(shares) if shares else 0
    eff = (10000 / h) if h > 0 else len(issuers)
    correlated = find_correlated_pairs(issuers)
    
    # CT standard: 2+ independent (non-correlated) issuers
    independent_groups = set()
    for i in issuers:
        independent_groups.add(f"{i.provider}:{i.model_family}")
    meets_ct = len(independent_groups) >= 2
    
    if h >= 5000:
        rec = "CRITICAL: Issuer monoculture. DigiNotar-level risk. Add 2+ independent issuers immediately."
    elif h >= 2500:
        rec = "WARNING: High concentration. Diversify across providers and model families."
    elif correlated:
        rec = f"CAUTION: {len(correlated)} correlated pair(s) detected. True independence may be lower than issuer count suggests."
    else:
        rec = "HEALTHY: Issuer diversity adequate. Continue monitoring."
    
    return ConcentrationReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        issuer_count=len(issuers),
        total_attestations=sum(i.attestation_count for i in issuers),
        hhi=round(h, 1),
        hhi_grade=grade_hhi(h),
        gini=round(g, 3),
        top_issuer_share=round(top_share, 3),
        effective_issuers=round(eff, 1),
        min_independent_issuers=2,
        meets_ct_standard=meets_ct,
        correlated_pairs=correlated,
        recommendation=rec
    )


def demo():
    """Demo with realistic scenarios."""
    scenarios = {
        "Monopoly (DigiNotar-like)": [
            IssuerProfile("issuer_alpha", "aws", "claude", 950, 0.95),
            IssuerProfile("issuer_beta", "aws", "claude", 50, 0.05),
        ],
        "Concentrated (Symantec-like)": [
            IssuerProfile("issuer_a", "aws", "claude", 600, 0.60),
            IssuerProfile("issuer_b", "gcp", "gemini", 250, 0.25),
            IssuerProfile("issuer_c", "aws", "claude", 150, 0.15),
        ],
        "Healthy (CT-compliant)": [
            IssuerProfile("issuer_1", "aws", "claude", 300, 0.30),
            IssuerProfile("issuer_2", "gcp", "gemini", 280, 0.28),
            IssuerProfile("issuer_3", "azure", "gpt4", 220, 0.22),
            IssuerProfile("issuer_4", "self-hosted", "llama", 200, 0.20),
        ],
    }
    
    for name, issuers in scenarios.items():
        report = analyze(issuers)
        print(f"\n{'='*50}")
        print(f"SCENARIO: {name}")
        print(f"{'='*50}")
        print(f"  Issuers: {report.issuer_count} (effective: {report.effective_issuers})")
        print(f"  HHI: {report.hhi} — {report.hhi_grade}")
        print(f"  Gini: {report.gini}")
        print(f"  Top issuer share: {report.top_issuer_share:.0%}")
        print(f"  CT standard met: {'✅' if report.meets_ct_standard else '❌'}")
        if report.correlated_pairs:
            print(f"  Correlated pairs: {len(report.correlated_pairs)}")
            for p in report.correlated_pairs:
                print(f"    {p['issuers'][0]} ↔ {p['issuers'][1]}: {p['correlation_reason']} ({p['risk']})")
        print(f"  → {report.recommendation}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Issuer concentration monitor")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        # Demo with JSON output
        issuers = [
            IssuerProfile("a", "aws", "claude", 600, 0.60),
            IssuerProfile("b", "gcp", "gemini", 250, 0.25),
            IssuerProfile("c", "aws", "claude", 150, 0.15),
        ]
        print(json.dumps(asdict(analyze(issuers)), indent=2))
    else:
        demo()
