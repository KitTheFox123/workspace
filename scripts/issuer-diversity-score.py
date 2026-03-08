#!/usr/bin/env python3
"""issuer-diversity-score.py — Issuer concentration risk analyzer.

Measures issuer diversity across attestations using HHI (Herfindahl-Hirschman Index)
and Simpson's diversity index. Flags monoculture risk.

Inspired by CA failure timeline (SSLMate) + santaclawd's issuer monoculture thread.

Usage:
    python3 issuer-diversity-score.py [--demo]
"""

import argparse
import json
import math
from collections import Counter
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass
class DiversityReport:
    """Issuer diversity analysis."""
    total_attestations: int
    unique_issuers: int
    hhi: float  # 0-10000, >2500 = concentrated
    simpson_d: float  # 0-1, higher = more diverse
    effective_issuers: float  # 1/HHI * 10000
    dominant_issuer: str
    dominant_share: float
    grade: str
    risk_level: str
    recommendation: str


def calculate_diversity(attestations: list[dict]) -> DiversityReport:
    """Calculate issuer diversity metrics."""
    issuers = [a["issuer"] for a in attestations]
    counts = Counter(issuers)
    total = len(issuers)
    
    if total == 0:
        return DiversityReport(0, 0, 10000, 0, 1, "none", 1.0, "F", "CRITICAL", "No attestations")
    
    # HHI: sum of squared market shares (0-10000)
    shares = [c / total for c in counts.values()]
    hhi = sum(s * s for s in shares) * 10000
    
    # Simpson's diversity: 1 - sum(p^2)
    simpson = 1 - sum(s * s for s in shares)
    
    # Effective number of issuers (inverse HHI)
    effective = 10000 / hhi if hhi > 0 else 0
    
    dominant = counts.most_common(1)[0]
    dominant_share = dominant[1] / total
    
    # Grade
    if hhi < 3000 and len(counts) >= 3:
        grade, risk = "A", "LOW"
        rec = "Healthy issuer diversity"
    elif hhi < 5000 and len(counts) >= 2:
        grade, risk = "B", "MODERATE"
        rec = "Acceptable but add more issuers"
    elif hhi < 7000:
        grade, risk = "C", "HIGH"
        rec = f"Concentrated: {dominant[0]} has {dominant_share:.0%}. Add independent issuers."
    else:
        grade, risk = "F", "CRITICAL"
        rec = f"Monoculture: {dominant[0]} controls {dominant_share:.0%}. DigiNotar-level risk."
    
    return DiversityReport(
        total_attestations=total,
        unique_issuers=len(counts),
        hhi=round(hhi, 1),
        simpson_d=round(simpson, 4),
        effective_issuers=round(effective, 2),
        dominant_issuer=dominant[0],
        dominant_share=round(dominant_share, 4),
        grade=grade,
        risk_level=risk,
        recommendation=rec
    )


def demo():
    """Demo with synthetic attestation data."""
    scenarios = {
        "healthy": [
            {"issuer": "operator_a", "agent": "kit"} for _ in range(5)
        ] + [
            {"issuer": "operator_b", "agent": "kit"} for _ in range(4)
        ] + [
            {"issuer": "operator_c", "agent": "kit"} for _ in range(3)
        ] + [
            {"issuer": "operator_d", "agent": "kit"} for _ in range(2)
        ],
        "concentrated": [
            {"issuer": "big_ca", "agent": "kit"} for _ in range(12)
        ] + [
            {"issuer": "small_ca", "agent": "kit"} for _ in range(2)
        ],
        "monoculture": [
            {"issuer": "only_ca", "agent": "kit"} for _ in range(15)
        ],
        "diginotar_scenario": [
            {"issuer": "diginotar", "agent": f"agent_{i}"} for i in range(10)
        ] + [
            {"issuer": "comodo", "agent": f"agent_{i}"} for i in range(2)
        ],
    }
    
    print("=" * 60)
    print("ISSUER DIVERSITY ANALYSIS")
    print("(HHI: <1500=competitive, 1500-2500=moderate, >2500=concentrated)")
    print("=" * 60)
    
    for name, attestations in scenarios.items():
        report = calculate_diversity(attestations)
        print(f"\n[{report.grade}] {name}")
        print(f"    Issuers: {report.unique_issuers} (effective: {report.effective_issuers:.1f})")
        print(f"    HHI: {report.hhi:.0f} | Simpson: {report.simpson_d:.3f}")
        print(f"    Dominant: {report.dominant_issuer} ({report.dominant_share:.0%})")
        print(f"    Risk: {report.risk_level} — {report.recommendation}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Issuer diversity analyzer")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        # Demo data in JSON
        attestations = [{"issuer": "op_a"}]*5 + [{"issuer": "op_b"}]*4 + [{"issuer": "op_c"}]*3
        print(json.dumps(asdict(calculate_diversity(attestations)), indent=2))
    else:
        demo()
