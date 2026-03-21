#!/usr/bin/env python3
"""
oracle-revocation.py — Evidence-based oracle independence revocation.

The missing primitive in the trust stack (santaclawd 2026-03-21):
- oracle-independence-verifier.py ✓
- oracle-genesis-registry.py ✓  
- oracle-vouch-chain.py ✓
- model-monoculture-detector.py ✓
- oracle-revocation.py ← THIS

Revocation triggers:
1. Gini threshold breach (>0.33 = BFT unsafe)
2. Model family acquisition (same family = correlated failures)
3. Shared incident (same CVE/outage across providers)
4. Behavioral correlation (outputs too similar = not independent)

Key principle: revocation by EVIDENCE not AUTHORITY.
Any party with proof can trigger re-audit.
CT parallel: CRLite bloom filter for mass revocation checks.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class RevocationReason(Enum):
    GINI_BREACH = "gini_threshold_breach"
    MONOCULTURE = "model_family_acquisition"
    SHARED_INCIDENT = "shared_incident_cve"
    BEHAVIORAL_CORRELATION = "output_correlation"
    MANUAL_EVIDENCE = "manual_evidence_submission"


class RevocationStatus(Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"  # temporary, pending review
    REVOKED = "revoked"  # permanent until re-audit
    REINSTATED = "reinstated"  # passed re-audit


@dataclass
class RevocationEvidence:
    """Evidence supporting a revocation claim."""
    reason: RevocationReason
    submitter_id: str
    timestamp: float
    evidence_hash: str  # hash of evidence payload
    details: dict
    
    @property
    def evidence_id(self) -> str:
        data = f"{self.reason.value}:{self.submitter_id}:{self.timestamp}:{self.evidence_hash}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass
class OracleStatus:
    """Current status of an oracle in the independence registry."""
    oracle_id: str
    model_family: str
    status: RevocationStatus = RevocationStatus.ACTIVE
    revocation_history: list[RevocationEvidence] = field(default_factory=list)
    last_audit: Optional[float] = None
    
    @property
    def times_revoked(self) -> int:
        return sum(1 for e in self.revocation_history)


@dataclass
class RevocationVerdict:
    """Result of evaluating revocation evidence."""
    oracle_id: str
    previous_status: RevocationStatus
    new_status: RevocationStatus
    reason: RevocationReason
    evidence_id: str
    affected_quorums: list[str]
    remediation: str


def check_gini_breach(oracle_weights: dict[str, float], threshold: float = 0.33) -> Optional[RevocationEvidence]:
    """Check if any oracle controls >threshold of total weight (BFT unsafe)."""
    total = sum(oracle_weights.values())
    if total == 0:
        return None
    
    for oracle_id, weight in oracle_weights.items():
        fraction = weight / total
        if fraction > threshold:
            return RevocationEvidence(
                reason=RevocationReason.GINI_BREACH,
                submitter_id="system",
                timestamp=time.time(),
                evidence_hash=hashlib.sha256(json.dumps(oracle_weights, sort_keys=True).encode()).hexdigest()[:32],
                details={"oracle_id": oracle_id, "fraction": fraction, "threshold": threshold}
            )
    return None


def check_monoculture(oracles: list[OracleStatus], family_threshold: float = 0.34) -> list[RevocationEvidence]:
    """Check if model family concentration exceeds BFT safety."""
    family_counts: dict[str, list[str]] = {}
    for o in oracles:
        family_counts.setdefault(o.model_family, []).append(o.oracle_id)
    
    evidences = []
    total = len(oracles)
    for family, members in family_counts.items():
        if len(members) / total > family_threshold:
            evidences.append(RevocationEvidence(
                reason=RevocationReason.MONOCULTURE,
                submitter_id="system",
                timestamp=time.time(),
                evidence_hash=hashlib.sha256(f"{family}:{len(members)}:{total}".encode()).hexdigest()[:32],
                details={"family": family, "members": members, "fraction": len(members)/total}
            ))
    return evidences


def check_shared_incident(affected_oracles: list[str], incident_id: str, 
                           total_oracles: int, threshold: float = 0.25) -> Optional[RevocationEvidence]:
    """Check if shared incident affects too many oracles."""
    if len(affected_oracles) / max(total_oracles, 1) > threshold:
        return RevocationEvidence(
            reason=RevocationReason.SHARED_INCIDENT,
            submitter_id="incident_reporter",
            timestamp=time.time(),
            evidence_hash=hashlib.sha256(incident_id.encode()).hexdigest()[:32],
            details={"incident_id": incident_id, "affected": affected_oracles, 
                     "fraction": len(affected_oracles)/total_oracles}
        )
    return None


def evaluate_revocation(oracle: OracleStatus, evidence: RevocationEvidence, 
                         quorum_memberships: list[str]) -> RevocationVerdict:
    """Evaluate revocation evidence and produce verdict."""
    previous = oracle.status
    
    # Determine new status based on evidence severity
    if evidence.reason == RevocationReason.GINI_BREACH:
        new_status = RevocationStatus.SUSPENDED
        remediation = "Re-audit required. Reduce weight below BFT threshold (0.33)."
    elif evidence.reason == RevocationReason.MONOCULTURE:
        new_status = RevocationStatus.SUSPENDED
        remediation = "Suspend until family diversity restored. Replace with different model family."
    elif evidence.reason == RevocationReason.SHARED_INCIDENT:
        new_status = RevocationStatus.SUSPENDED
        remediation = "Suspend pending incident resolution. CVE remediation required."
    elif evidence.reason == RevocationReason.BEHAVIORAL_CORRELATION:
        new_status = RevocationStatus.REVOKED
        remediation = "Revoked. Independence claim falsified by output correlation analysis."
    else:
        new_status = RevocationStatus.SUSPENDED
        remediation = "Suspend pending manual review of submitted evidence."
    
    oracle.status = new_status
    oracle.revocation_history.append(evidence)
    
    return RevocationVerdict(
        oracle_id=oracle.oracle_id,
        previous_status=previous,
        new_status=new_status,
        reason=evidence.reason,
        evidence_id=evidence.evidence_id,
        affected_quorums=quorum_memberships,
        remediation=remediation
    )


def demo():
    """Demo: oracle revocation scenarios."""
    oracles = [
        OracleStatus("oracle_1", "openai"),
        OracleStatus("oracle_2", "openai"),
        OracleStatus("oracle_3", "openai"),
        OracleStatus("oracle_4", "anthropic"),
        OracleStatus("oracle_5", "google"),
        OracleStatus("oracle_6", "openai"),
        OracleStatus("oracle_7", "mistral"),
    ]

    print("=" * 65)
    print("ORACLE REVOCATION — THE MISSING PRIMITIVE")
    print("=" * 65)

    # Scenario 1: Monoculture detection
    print("\n--- Scenario 1: Model Family Monoculture ---")
    mono_evidence = check_monoculture(oracles)
    for ev in mono_evidence:
        print(f"  ⚠️  {ev.reason.value}: {ev.details['family']} = {ev.details['fraction']:.0%} of quorum")
        verdict = evaluate_revocation(
            oracles[0], ev, ["quorum_alpha", "quorum_beta"]
        )
        print(f"  Verdict: {verdict.previous_status.value} → {verdict.new_status.value}")
        print(f"  Remediation: {verdict.remediation}")
        print(f"  Affected quorums: {verdict.affected_quorums}")

    # Scenario 2: Gini concentration
    print("\n--- Scenario 2: Gini Weight Concentration ---")
    weights = {"oracle_1": 0.4, "oracle_2": 0.2, "oracle_3": 0.15, 
               "oracle_4": 0.15, "oracle_5": 0.1}
    gini_ev = check_gini_breach(weights)
    if gini_ev:
        print(f"  ⚠️  {gini_ev.reason.value}: oracle_1 = {gini_ev.details['fraction']:.0%}")
        verdict = evaluate_revocation(
            OracleStatus("oracle_1", "openai"), gini_ev, ["quorum_gamma"]
        )
        print(f"  Verdict: {verdict.previous_status.value} → {verdict.new_status.value}")

    # Scenario 3: Shared CVE
    print("\n--- Scenario 3: Shared Incident (CVE) ---")
    cve_ev = check_shared_incident(
        ["oracle_1", "oracle_2", "oracle_6"],
        "CVE-2026-1234", 
        total_oracles=7
    )
    if cve_ev:
        print(f"  ⚠️  {cve_ev.reason.value}: {len(cve_ev.details['affected'])}/{7} oracles affected")
        print(f"  Incident: {cve_ev.details['incident_id']}")

    # Summary
    print("\n" + "=" * 65)
    print("TRUST STACK STATUS (post-revocation)")
    print("=" * 65)
    print(f"  oracle-independence-verifier.py  ✅")
    print(f"  oracle-genesis-registry.py       ✅")
    print(f"  oracle-vouch-chain.py            ✅")
    print(f"  model-monoculture-detector.py    ✅")
    print(f"  oracle-revocation.py             ✅  ← NEW")
    print()
    print("  Key: revocation by EVIDENCE not AUTHORITY.")
    print("  Any party with proof can trigger re-audit.")
    print("  — santaclawd (2026-03-21)")


if __name__ == "__main__":
    demo()
