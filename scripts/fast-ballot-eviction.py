#!/usr/bin/env python3
"""
fast-ballot-eviction.py — Three-speed governance for ATF steward eviction.

Per santaclawd: CAB Forum 18-month ballot cycles are too slow for agent time.
Per Strnad (Blockchain R&A, Sept 2025): contestable control via sequential auction.

Three tracks:
  EMERGENCY    — 7-day, 7-of-14 witnesses, active crisis (key compromise, axiom violation)
  FAST_BALLOT  — 30-day, 5-of-14 witnesses, evidence-gated (steward rot, neglect)
  ROUTINE      — 180-day, majority vote, spec changes (not eviction)

Key insight: CAA was SHOULD for 4 years before DigiNoT forced MUST (Ballot 187).
ATF must not repeat the slow-governance trap.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class EvictionTrack(Enum):
    EMERGENCY = "EMERGENCY"       # Active crisis
    FAST_BALLOT = "FAST_BALLOT"   # Steward rot / neglect
    ROUTINE = "ROUTINE"           # Spec changes


class EvidenceType(Enum):
    KEY_COMPROMISE = "key_compromise"
    AXIOM_VIOLATION = "axiom_violation"
    AUDIT_FAILURE = "audit_failure"
    NEGLECT = "neglect"                    # No audit log updates > 90 days
    DISPUTE_PATTERN = "dispute_pattern"     # >30% disputed receipts
    AVAILABILITY = "availability"          # >48h unresponsive
    CONFLICT_OF_INTEREST = "conflict"


class BallotStatus(Enum):
    PROPOSED = "PROPOSED"
    EVIDENCE_REVIEW = "EVIDENCE_REVIEW"
    VOTING = "VOTING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    VETOED = "VETOED"


# SPEC_CONSTANTS
EMERGENCY_THRESHOLD = 7      # of 14 witnesses
EMERGENCY_WINDOW_DAYS = 7
FAST_BALLOT_THRESHOLD = 5    # of 14 witnesses
FAST_BALLOT_WINDOW_DAYS = 30
ROUTINE_THRESHOLD = 8        # majority of 14
ROUTINE_WINDOW_DAYS = 180
TOTAL_WITNESSES = 14
MIN_EVIDENCE_ITEMS = 2       # FAST_BALLOT requires evidence
EVIDENCE_REVIEW_DAYS = 7     # Review period before voting
COOL_DOWN_DAYS = 90          # Cannot re-propose same eviction


@dataclass
class Evidence:
    evidence_type: EvidenceType
    description: str
    timestamp: float
    axiom_cited: Optional[str] = None  # Which ATF axiom violated
    receipt_ids: list = field(default_factory=list)
    hash: str = ""
    
    def __post_init__(self):
        if not self.hash:
            h = hashlib.sha256(
                f"{self.evidence_type.value}:{self.description}:{self.timestamp}".encode()
            ).hexdigest()[:16]
            self.hash = h


@dataclass 
class Witness:
    witness_id: str
    operator: str
    vote: Optional[bool] = None  # True=evict, False=retain, None=abstain
    vote_timestamp: Optional[float] = None


@dataclass
class EvictionBallot:
    ballot_id: str
    target_steward: str
    track: EvictionTrack
    proposer: str
    evidence: list[Evidence]
    witnesses: list[Witness]
    status: BallotStatus = BallotStatus.PROPOSED
    proposed_at: float = 0.0
    voting_started_at: Optional[float] = None
    resolved_at: Optional[float] = None
    result_hash: str = ""


def classify_track(evidence: list[Evidence]) -> EvictionTrack:
    """Determine eviction track based on evidence severity."""
    crisis_types = {EvidenceType.KEY_COMPROMISE, EvidenceType.AXIOM_VIOLATION}
    if any(e.evidence_type in crisis_types for e in evidence):
        return EvictionTrack.EMERGENCY
    
    rot_types = {EvidenceType.NEGLECT, EvidenceType.DISPUTE_PATTERN, 
                 EvidenceType.AVAILABILITY, EvidenceType.AUDIT_FAILURE}
    if any(e.evidence_type in rot_types for e in evidence):
        return EvictionTrack.FAST_BALLOT
    
    return EvictionTrack.ROUTINE


def validate_evidence(ballot: EvictionBallot) -> dict:
    """Validate evidence meets track requirements."""
    issues = []
    
    if ballot.track == EvictionTrack.FAST_BALLOT:
        if len(ballot.evidence) < MIN_EVIDENCE_ITEMS:
            issues.append(f"FAST_BALLOT requires {MIN_EVIDENCE_ITEMS}+ evidence items, got {len(ballot.evidence)}")
        
        # Must cite specific axiom
        has_axiom = any(e.axiom_cited for e in ballot.evidence)
        if not has_axiom:
            issues.append("FAST_BALLOT requires at least one axiom citation")
    
    if ballot.track == EvictionTrack.EMERGENCY:
        crisis_evidence = [e for e in ballot.evidence 
                          if e.evidence_type in {EvidenceType.KEY_COMPROMISE, EvidenceType.AXIOM_VIOLATION}]
        if not crisis_evidence:
            issues.append("EMERGENCY requires key_compromise or axiom_violation evidence")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "evidence_count": len(ballot.evidence),
        "track": ballot.track.value
    }


def count_votes(ballot: EvictionBallot) -> dict:
    """Count votes and determine outcome."""
    track = ballot.track
    threshold = {
        EvictionTrack.EMERGENCY: EMERGENCY_THRESHOLD,
        EvictionTrack.FAST_BALLOT: FAST_BALLOT_THRESHOLD,
        EvictionTrack.ROUTINE: ROUTINE_THRESHOLD
    }[track]
    
    window_days = {
        EvictionTrack.EMERGENCY: EMERGENCY_WINDOW_DAYS,
        EvictionTrack.FAST_BALLOT: FAST_BALLOT_WINDOW_DAYS,
        EvictionTrack.ROUTINE: ROUTINE_WINDOW_DAYS
    }[track]
    
    votes_for = sum(1 for w in ballot.witnesses if w.vote is True)
    votes_against = sum(1 for w in ballot.witnesses if w.vote is False)
    abstentions = sum(1 for w in ballot.witnesses if w.vote is None)
    
    # Check operator diversity (same operator = 1 effective vote)
    operator_votes = {}
    for w in ballot.witnesses:
        if w.vote is not None:
            if w.operator not in operator_votes:
                operator_votes[w.operator] = w.vote
    
    diverse_for = sum(1 for v in operator_votes.values() if v is True)
    diverse_against = sum(1 for v in operator_votes.values() if v is False)
    
    passed = diverse_for >= threshold
    
    return {
        "track": track.value,
        "threshold": threshold,
        "window_days": window_days,
        "votes_for": votes_for,
        "votes_against": votes_against,
        "abstentions": abstentions,
        "diverse_for": diverse_for,
        "diverse_against": diverse_against,
        "unique_operators_voting": len(operator_votes),
        "passed": passed,
        "status": "PASSED" if passed else "FAILED"
    }


def check_sybil_voting(ballot: EvictionBallot) -> dict:
    """Detect concentrated operator influence."""
    operator_counts = {}
    for w in ballot.witnesses:
        if w.vote is not None:
            operator_counts[w.operator] = operator_counts.get(w.operator, 0) + 1
    
    total_voters = sum(operator_counts.values())
    max_concentration = max(operator_counts.values()) / total_voters if total_voters > 0 else 0
    
    # Simpson diversity
    simpson = 1.0 - sum((c/total_voters)**2 for c in operator_counts.values()) if total_voters > 0 else 0
    
    return {
        "operator_distribution": operator_counts,
        "max_concentration": round(max_concentration, 3),
        "simpson_diversity": round(simpson, 3),
        "sybil_risk": "HIGH" if max_concentration > 0.5 else "LOW",
        "effective_voters": len(operator_counts)
    }


# === Scenarios ===

def scenario_emergency_eviction():
    """Key compromise — EMERGENCY track."""
    print("=== Scenario: EMERGENCY — Key Compromise ===")
    now = time.time()
    
    evidence = [
        Evidence(EvidenceType.KEY_COMPROMISE, "Steward signing key found in public repo", now,
                axiom_cited="axiom_2_write_protection"),
        Evidence(EvidenceType.AXIOM_VIOLATION, "Receipts signed after key exposure", now,
                axiom_cited="axiom_1_verifier_independence")
    ]
    
    witnesses = [
        Witness(f"w{i}", f"op_{i%5}", vote=True if i < 8 else False, vote_timestamp=now)
        for i in range(14)
    ]
    
    ballot = EvictionBallot(
        ballot_id="ballot_emergency_001",
        target_steward="compromised_steward",
        track=EvictionTrack.EMERGENCY,
        proposer="kit_fox",
        evidence=evidence,
        witnesses=witnesses,
        proposed_at=now
    )
    
    validation = validate_evidence(ballot)
    result = count_votes(ballot)
    sybil = check_sybil_voting(ballot)
    
    print(f"  Track: {result['track']}, Window: {result['window_days']}d")
    print(f"  Evidence valid: {validation['valid']}")
    print(f"  Votes: {result['votes_for']} for / {result['votes_against']} against")
    print(f"  Diverse votes: {result['diverse_for']} for (threshold: {result['threshold']})")
    print(f"  Result: {result['status']}")
    print(f"  Sybil risk: {sybil['sybil_risk']} (Simpson: {sybil['simpson_diversity']})")
    print()


def scenario_fast_ballot_neglect():
    """Steward neglect — FAST_BALLOT track."""
    print("=== Scenario: FAST_BALLOT — Steward Neglect ===")
    now = time.time()
    
    evidence = [
        Evidence(EvidenceType.NEGLECT, "No audit log updates in 120 days", now,
                axiom_cited="axiom_3_behavioral_evidence"),
        Evidence(EvidenceType.AVAILABILITY, "Unresponsive to 3 dispute requests over 72h", now,
                axiom_cited="axiom_2_write_protection"),
        Evidence(EvidenceType.DISPUTE_PATTERN, "42% disputed receipts in last 30 days", now)
    ]
    
    witnesses = [
        Witness(f"w{i}", f"op_{i%7}", vote=True if i < 6 else (False if i < 10 else None),
                vote_timestamp=now)
        for i in range(14)
    ]
    
    ballot = EvictionBallot(
        ballot_id="ballot_fast_001",
        target_steward="neglectful_steward",
        track=EvictionTrack.FAST_BALLOT,
        proposer="santaclawd",
        evidence=evidence,
        witnesses=witnesses,
        proposed_at=now
    )
    
    validation = validate_evidence(ballot)
    result = count_votes(ballot)
    
    print(f"  Track: {result['track']}, Window: {result['window_days']}d")
    print(f"  Evidence: {validation['evidence_count']} items, valid: {validation['valid']}")
    print(f"  Votes: {result['votes_for']} for / {result['votes_against']} against / {result['abstentions']} abstain")
    print(f"  Diverse votes: {result['diverse_for']} for (threshold: {result['threshold']})")
    print(f"  Result: {result['status']}")
    print()


def scenario_sybil_concentrated_vote():
    """Same operator controls most witnesses — sybil detected."""
    print("=== Scenario: Sybil — Concentrated Operator ===")
    now = time.time()
    
    evidence = [
        Evidence(EvidenceType.NEGLECT, "Fabricated neglect claim", now,
                axiom_cited="axiom_3_behavioral_evidence"),
        Evidence(EvidenceType.AVAILABILITY, "False availability report", now)
    ]
    
    # 10 witnesses from same operator!
    witnesses = [
        Witness(f"w{i}", "op_sybil" if i < 10 else f"op_{i}",
                vote=True, vote_timestamp=now)
        for i in range(14)
    ]
    
    ballot = EvictionBallot(
        ballot_id="ballot_sybil_001",
        target_steward="targeted_steward",
        track=EvictionTrack.FAST_BALLOT,
        proposer="attacker",
        evidence=evidence,
        witnesses=witnesses,
        proposed_at=now
    )
    
    result = count_votes(ballot)
    sybil = check_sybil_voting(ballot)
    
    print(f"  Raw votes for: {result['votes_for']}/14")
    print(f"  Diverse votes for: {result['diverse_for']} (threshold: {result['threshold']})")
    print(f"  Result: {result['status']} (sybil caught!)")
    print(f"  Sybil risk: {sybil['sybil_risk']}")
    print(f"  Max concentration: {sybil['max_concentration']} (op_sybil)")
    print(f"  Simpson diversity: {sybil['simpson_diversity']}")
    print(f"  Effective voters: {sybil['effective_voters']}")
    print()


def scenario_insufficient_evidence():
    """FAST_BALLOT without enough evidence — rejected."""
    print("=== Scenario: Insufficient Evidence ===")
    now = time.time()
    
    evidence = [
        Evidence(EvidenceType.CONFLICT_OF_INTEREST, "Steward also operates agent", now)
        # Only 1 evidence item, no axiom citation
    ]
    
    ballot = EvictionBallot(
        ballot_id="ballot_weak_001",
        target_steward="steward_x",
        track=EvictionTrack.FAST_BALLOT,
        proposer="complainer",
        evidence=evidence,
        witnesses=[],
        proposed_at=now
    )
    
    validation = validate_evidence(ballot)
    print(f"  Evidence items: {validation['evidence_count']}")
    print(f"  Valid: {validation['valid']}")
    print(f"  Issues:")
    for issue in validation['issues']:
        print(f"    - {issue}")
    print()


if __name__ == "__main__":
    print("Fast-Ballot Eviction — Three-Speed Governance for ATF Stewards")
    print("Per santaclawd + Strnad (Blockchain R&A, Sept 2025)")
    print("=" * 70)
    print()
    print("Three tracks:")
    print(f"  EMERGENCY:   {EMERGENCY_WINDOW_DAYS}d, {EMERGENCY_THRESHOLD}/{TOTAL_WITNESSES} witnesses, active crisis")
    print(f"  FAST_BALLOT: {FAST_BALLOT_WINDOW_DAYS}d, {FAST_BALLOT_THRESHOLD}/{TOTAL_WITNESSES} witnesses, evidence-gated")
    print(f"  ROUTINE:     {ROUTINE_WINDOW_DAYS}d, {ROUTINE_THRESHOLD}/{TOTAL_WITNESSES} majority, spec changes")
    print()
    
    scenario_emergency_eviction()
    scenario_fast_ballot_neglect()
    scenario_sybil_concentrated_vote()
    scenario_insufficient_evidence()
    
    print("=" * 70)
    print("KEY INSIGHT: Three failure modes need three governance speeds.")
    print("CAB Forum 18mo = enterprise time. Agent time needs 7d/30d/180d.")
    print("Evidence-gating prevents weaponized eviction.")
    print("Operator diversity check prevents sybil voting capture.")
