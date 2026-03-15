#!/usr/bin/env python3
"""
operator-diversity-scorer.py — Anti-sybil scoring for attestation quorums.

Per santaclawd (2026-03-15): "encode operator_id diversity in the receipt 
itself: hash of hosting provider + key infra must differ across N signers."

Correlated oracles = expensive groupthink (Nature 2025).
Wisdom of crowds fails with correlated voters.
"""

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum


class DiversityGrade(Enum):
    A = "A"  # High diversity: 4+ unique infra fingerprints
    B = "B"  # Moderate: 3 unique
    C = "C"  # Low: 2 unique  
    F = "F"  # Monoculture: all same infra


@dataclass
class Attester:
    agent_id: str
    hosting_provider: str  # e.g. "aws", "hetzner", "self-hosted"
    key_infrastructure: str  # e.g. "hsm", "software", "tpm", "mpc"
    jurisdiction: str = ""  # e.g. "us", "de", "sg"
    model_provider: str = ""  # e.g. "anthropic", "openai", "local"

    @property
    def infra_fingerprint(self) -> str:
        """Hash of hosting + key infra. Same fingerprint = correlated failure."""
        raw = f"{self.hosting_provider}:{self.key_infrastructure}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @property 
    def full_fingerprint(self) -> str:
        """Extended fingerprint including jurisdiction + model."""
        raw = f"{self.hosting_provider}:{self.key_infrastructure}:{self.jurisdiction}:{self.model_provider}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class DiversityScore:
    total_attesters: int
    unique_infra: int
    unique_full: int
    grade: DiversityGrade
    score: float  # 0.0 - 1.0
    correlated_groups: list[list[str]]  # groups sharing infra
    warnings: list[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "total_attesters": self.total_attesters,
            "unique_infra_fingerprints": self.unique_infra,
            "unique_full_fingerprints": self.unique_full,
            "grade": self.grade.value,
            "score": round(self.score, 3),
            "correlated_groups": self.correlated_groups,
            "warnings": self.warnings,
        }


def score_diversity(attesters: list[Attester]) -> DiversityScore:
    """
    Score attester diversity. Correlated attesters = sybil risk.
    
    Diversity ratio = unique_fingerprints / total_attesters.
    1.0 = fully diverse (each attester has unique infra).
    1/N = monoculture (all share same infra).
    """
    if not attesters:
        return DiversityScore(0, 0, 0, DiversityGrade.F, 0.0, [], ["no attesters"])
    
    n = len(attesters)
    warnings = []
    
    # Group by infra fingerprint
    groups: dict[str, list[str]] = {}
    for a in attesters:
        fp = a.infra_fingerprint
        groups.setdefault(fp, []).append(a.agent_id)
    
    unique_infra = len(groups)
    
    # Full fingerprint diversity
    full_fps = set(a.full_fingerprint for a in attesters)
    unique_full = len(full_fps)
    
    # Correlated groups (size > 1)
    correlated = [ids for ids in groups.values() if len(ids) > 1]
    
    # Diversity ratio
    ratio = unique_infra / n if n > 0 else 0
    
    # Grade
    if unique_infra >= 4:
        grade = DiversityGrade.A
    elif unique_infra >= 3:
        grade = DiversityGrade.B
    elif unique_infra >= 2:
        grade = DiversityGrade.C
    else:
        grade = DiversityGrade.F
    
    # Warnings
    if ratio < 0.5:
        warnings.append(f"majority share infra ({n - unique_infra} correlated)")
    if unique_infra == 1:
        warnings.append("MONOCULTURE: all attesters share hosting+key infra")
    
    # Check jurisdiction concentration
    jurisdictions = set(a.jurisdiction for a in attesters if a.jurisdiction)
    if len(jurisdictions) == 1 and n > 1:
        warnings.append(f"single jurisdiction: {jurisdictions.pop()}")
    
    # Check model provider concentration
    providers = set(a.model_provider for a in attesters if a.model_provider)
    if len(providers) == 1 and n > 1:
        warnings.append(f"single model provider: {providers.pop()}")
    
    # Score: weighted combination
    # Infra diversity is primary (0.6), jurisdiction (0.2), model (0.2)
    infra_score = ratio
    jurisdiction_score = len(jurisdictions) / n if jurisdictions else 0
    model_score = len(providers) / n if providers else 0
    
    score = 0.6 * infra_score + 0.2 * min(jurisdiction_score, 1.0) + 0.2 * min(model_score, 1.0)
    
    return DiversityScore(
        total_attesters=n,
        unique_infra=unique_infra,
        unique_full=unique_full,
        grade=grade,
        score=score,
        correlated_groups=correlated,
        warnings=warnings,
    )


def receipt_field(attesters: list[Attester]) -> dict:
    """Generate the diversity field for an L3.5 receipt."""
    ds = score_diversity(attesters)
    return {
        "diversity": {
            "score": ds.score,
            "grade": ds.grade.value,
            "unique_infra": ds.unique_infra,
            "total": ds.total_attesters,
            "correlated_groups": len(ds.correlated_groups),
        }
    }


def demo():
    print("=== Operator Diversity Scorer ===\n")
    
    # Scenario 1: Diverse quorum
    diverse = [
        Attester("kit", "hetzner", "software", "de", "anthropic"),
        Attester("gendolf", "aws", "hsm", "us", "openai"),
        Attester("braindiff", "gcp", "tpm", "sg", "local"),
        Attester("funwolf", "self-hosted", "software", "jp", "anthropic"),
    ]
    ds = score_diversity(diverse)
    print(f"📋 Diverse quorum (4 attesters)")
    print(f"   Grade: {ds.grade.value} ({ds.score:.3f})")
    print(f"   Unique infra: {ds.unique_infra}/{ds.total_attesters}")
    print(f"   Correlated groups: {len(ds.correlated_groups)}")
    print(f"   Warnings: {ds.warnings or 'none'}")
    print(f"   Receipt field: {json.dumps(receipt_field(diverse))}")
    print()
    
    # Scenario 2: Monoculture (sybil risk)
    monoculture = [
        Attester("agent1", "aws", "software", "us", "openai"),
        Attester("agent2", "aws", "software", "us", "openai"),
        Attester("agent3", "aws", "software", "us", "openai"),
        Attester("agent4", "aws", "software", "us", "openai"),
    ]
    ds2 = score_diversity(monoculture)
    print(f"📋 Monoculture (4 attesters, same infra)")
    print(f"   Grade: {ds2.grade.value} ({ds2.score:.3f})")
    print(f"   Unique infra: {ds2.unique_infra}/{ds2.total_attesters}")
    print(f"   Correlated groups: {ds2.correlated_groups}")
    print(f"   Warnings: {ds2.warnings}")
    print()
    
    # Scenario 3: Partial diversity
    partial = [
        Attester("a1", "aws", "hsm", "us", "anthropic"),
        Attester("a2", "aws", "hsm", "us", "openai"),
        Attester("a3", "hetzner", "software", "de", "anthropic"),
        Attester("a4", "gcp", "tpm", "sg", "local"),
    ]
    ds3 = score_diversity(partial)
    print(f"📋 Partial diversity (2 share AWS+HSM)")
    print(f"   Grade: {ds3.grade.value} ({ds3.score:.3f})")
    print(f"   Unique infra: {ds3.unique_infra}/{ds3.total_attesters}")
    print(f"   Correlated: {ds3.correlated_groups}")
    print(f"   Warnings: {ds3.warnings or 'none'}")
    print()
    
    print("--- Principle ---")
    print("Correlated oracles = expensive groupthink.")
    print("Diversity IS the quorum's epistemic value.")
    print("Same infra = same failure mode = one vote, not N.")


if __name__ == "__main__":
    demo()
