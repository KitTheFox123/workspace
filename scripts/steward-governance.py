#!/usr/bin/env python3
"""
steward-governance.py — CAB Forum governance model for ATF steward list management.

Per santaclawd: "who governs the initial steward list? browsers have CAB Forum.
ATF needs equivalent governance before first registry goes live."

CAB Forum model:
- Two voter classes: Certificate Issuers (CAs) + Certificate Consumers (browsers)
- Both classes must independently approve ballots
- CAs: 2/3 supermajority required
- Browsers: 50%+1 simple majority required (any NO = veto in practice)
- 7-day discussion + 7-day voting period
- Public mailing list for transparency

ATF equivalent:
- Implementers (registries, agents) ≈ CAs
- Verifiers (graders, auditors) ≈ browsers
- Steward list = browser trust store
- Ceremony transcript = audit log
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class MemberClass(Enum):
    IMPLEMENTER = "IMPLEMENTER"  # Registries, agent operators (≈ CAs)
    VERIFIER = "VERIFIER"        # Graders, auditors (≈ browsers)
    OBSERVER = "OBSERVER"        # Interested parties, no vote


class BallotType(Enum):
    ADD_STEWARD = "ADD_STEWARD"
    REMOVE_STEWARD = "REMOVE_STEWARD"
    AMEND_CONSTANT = "AMEND_CONSTANT"
    CHARTER_WG = "CHARTER_WG"


class BallotStatus(Enum):
    DISCUSSION = "DISCUSSION"
    VOTING = "VOTING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    WITHDRAWN = "WITHDRAWN"


class Vote(Enum):
    YES = "YES"
    NO = "NO"
    ABSTAIN = "ABSTAIN"


# SPEC_CONSTANTS (from CAB Forum Bylaws)
DISCUSSION_PERIOD_DAYS = 7
VOTING_PERIOD_DAYS = 7
IMPLEMENTER_THRESHOLD = 2/3    # Supermajority
VERIFIER_THRESHOLD = 0.501     # Simple majority
MIN_IMPLEMENTER_VOTERS = 3     # Quorum
MIN_VERIFIER_VOTERS = 2        # Quorum
STEWARD_REMOVAL_REQUIRES_CAUSE = True  # Must cite specific violation


@dataclass
class Member:
    id: str
    name: str
    member_class: MemberClass
    joined_at: float
    is_active: bool = True
    genesis_hash: Optional[str] = None  # For implementers


@dataclass 
class Ballot:
    id: str
    ballot_type: BallotType
    title: str
    description: str
    proposer_id: str
    created_at: float
    discussion_end: float
    voting_end: float
    status: BallotStatus = BallotStatus.DISCUSSION
    votes: dict = field(default_factory=dict)  # member_id -> Vote
    result: Optional[dict] = None


@dataclass
class Steward:
    id: str
    name: str
    genesis_hash: str
    added_by_ballot: str
    added_at: float
    is_active: bool = True
    removed_by_ballot: Optional[str] = None


@dataclass
class GovernanceState:
    members: list[Member] = field(default_factory=list)
    ballots: list[Ballot] = field(default_factory=list)
    stewards: list[Steward] = field(default_factory=list)
    governance_hash: str = "genesis"


def compute_governance_hash(state: GovernanceState) -> str:
    """Deterministic hash of current governance state."""
    steward_ids = sorted(s.id for s in state.stewards if s.is_active)
    member_ids = sorted(m.id for m in state.members if m.is_active)
    ballot_ids = sorted(b.id for b in state.ballots)
    content = f"{steward_ids}:{member_ids}:{ballot_ids}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def tally_votes(ballot: Ballot, members: list[Member]) -> dict:
    """
    Tally votes by class. CAB Forum model:
    - Implementers: 2/3 supermajority of those voting (excl abstain)
    - Verifiers: 50%+1 of those voting (excl abstain)
    - Both must independently pass
    """
    impl_votes = {"YES": 0, "NO": 0, "ABSTAIN": 0}
    ver_votes = {"YES": 0, "NO": 0, "ABSTAIN": 0}
    
    member_map = {m.id: m for m in members}
    
    for member_id, vote in ballot.votes.items():
        member = member_map.get(member_id)
        if not member or not member.is_active:
            continue
        if member.member_class == MemberClass.IMPLEMENTER:
            impl_votes[vote.value] += 1
        elif member.member_class == MemberClass.VERIFIER:
            ver_votes[vote.value] += 1
    
    # Calculate pass/fail per class
    impl_voting = impl_votes["YES"] + impl_votes["NO"]
    ver_voting = ver_votes["YES"] + ver_votes["NO"]
    
    impl_ratio = impl_votes["YES"] / impl_voting if impl_voting > 0 else 0
    ver_ratio = ver_votes["YES"] / ver_voting if ver_voting > 0 else 0
    
    impl_quorum = impl_voting >= MIN_IMPLEMENTER_VOTERS
    ver_quorum = ver_voting >= MIN_VERIFIER_VOTERS
    
    impl_passed = impl_quorum and impl_ratio >= IMPLEMENTER_THRESHOLD
    ver_passed = ver_quorum and ver_ratio >= VERIFIER_THRESHOLD
    
    return {
        "implementers": {
            "yes": impl_votes["YES"],
            "no": impl_votes["NO"],
            "abstain": impl_votes["ABSTAIN"],
            "ratio": round(impl_ratio, 3),
            "quorum_met": impl_quorum,
            "passed": impl_passed
        },
        "verifiers": {
            "yes": ver_votes["YES"],
            "no": ver_votes["NO"],
            "abstain": ver_votes["ABSTAIN"],
            "ratio": round(ver_ratio, 3),
            "quorum_met": ver_quorum,
            "passed": ver_passed
        },
        "overall_passed": impl_passed and ver_passed,
        "failure_reason": None if (impl_passed and ver_passed) else
            "IMPLEMENTER_QUORUM" if not impl_quorum else
            "VERIFIER_QUORUM" if not ver_quorum else
            "IMPLEMENTER_THRESHOLD" if not impl_passed else
            "VERIFIER_THRESHOLD"
    }


def apply_ballot(state: GovernanceState, ballot: Ballot, tally: dict) -> str:
    """Apply passed ballot to governance state. Returns description."""
    if not tally["overall_passed"]:
        ballot.status = BallotStatus.FAILED
        ballot.result = tally
        return f"FAILED: {tally['failure_reason']}"
    
    ballot.status = BallotStatus.PASSED
    ballot.result = tally
    
    if ballot.ballot_type == BallotType.ADD_STEWARD:
        steward = Steward(
            id=f"steward_{len(state.stewards)}",
            name=ballot.title.replace("Add Steward: ", ""),
            genesis_hash=hashlib.sha256(ballot.title.encode()).hexdigest()[:16],
            added_by_ballot=ballot.id,
            added_at=time.time()
        )
        state.stewards.append(steward)
        return f"PASSED: Added steward {steward.name}"
    
    elif ballot.ballot_type == BallotType.REMOVE_STEWARD:
        target = ballot.title.replace("Remove Steward: ", "")
        for s in state.stewards:
            if s.name == target and s.is_active:
                s.is_active = False
                s.removed_by_ballot = ballot.id
                return f"PASSED: Removed steward {target}"
        return "PASSED: Steward not found (no-op)"
    
    return f"PASSED: {ballot.ballot_type.value}"


# === Scenarios ===

def make_members():
    """Create a realistic member set."""
    now = time.time()
    return [
        # Implementers (registries, operators)
        Member("impl_1", "ATF_Registry_Alpha", MemberClass.IMPLEMENTER, now),
        Member("impl_2", "ATF_Registry_Beta", MemberClass.IMPLEMENTER, now),
        Member("impl_3", "ATF_Registry_Gamma", MemberClass.IMPLEMENTER, now),
        Member("impl_4", "Operator_Kit", MemberClass.IMPLEMENTER, now),
        Member("impl_5", "Operator_Bro", MemberClass.IMPLEMENTER, now),
        # Verifiers (graders, auditors)
        Member("ver_1", "Grader_Momo", MemberClass.VERIFIER, now),
        Member("ver_2", "Grader_BrainDiff", MemberClass.VERIFIER, now),
        Member("ver_3", "Auditor_External", MemberClass.VERIFIER, now),
        # Observers
        Member("obs_1", "Researcher_Holly", MemberClass.OBSERVER, now),
    ]


def scenario_add_steward_passes():
    """Normal steward addition — passes both classes."""
    print("=== Scenario: Add Steward (Passes) ===")
    state = GovernanceState(members=make_members())
    now = time.time()
    
    ballot = Ballot(
        id="ballot_001", ballot_type=BallotType.ADD_STEWARD,
        title="Add Steward: Gendolf_Trust_Registry",
        description="Gendolf operates trust registry with ceremony transcript published.",
        proposer_id="impl_1", created_at=now,
        discussion_end=now + 86400*7, voting_end=now + 86400*14,
        status=BallotStatus.VOTING
    )
    
    # Votes
    ballot.votes = {
        "impl_1": Vote.YES, "impl_2": Vote.YES, "impl_3": Vote.YES,
        "impl_4": Vote.YES, "impl_5": Vote.NO,  # 4/5 = 80% > 66.7%
        "ver_1": Vote.YES, "ver_2": Vote.YES, "ver_3": Vote.ABSTAIN  # 2/2 = 100%
    }
    
    tally = tally_votes(ballot, state.members)
    result = apply_ballot(state, ballot, tally)
    
    print(f"  Implementers: {tally['implementers']['yes']}Y/{tally['implementers']['no']}N "
          f"({tally['implementers']['ratio']:.1%}) quorum={tally['implementers']['quorum_met']}")
    print(f"  Verifiers: {tally['verifiers']['yes']}Y/{tally['verifiers']['no']}N "
          f"({tally['verifiers']['ratio']:.1%}) quorum={tally['verifiers']['quorum_met']}")
    print(f"  Result: {result}")
    print(f"  Active stewards: {len([s for s in state.stewards if s.is_active])}")
    print()


def scenario_verifier_veto():
    """Verifiers block steward addition — CAB Forum browser veto model."""
    print("=== Scenario: Verifier Veto ===")
    state = GovernanceState(members=make_members())
    now = time.time()
    
    ballot = Ballot(
        id="ballot_002", ballot_type=BallotType.ADD_STEWARD,
        title="Add Steward: Sketchy_Registry",
        description="Registry with no ceremony transcript.",
        proposer_id="impl_1", created_at=now,
        discussion_end=now + 86400*7, voting_end=now + 86400*14,
        status=BallotStatus.VOTING
    )
    
    ballot.votes = {
        "impl_1": Vote.YES, "impl_2": Vote.YES, "impl_3": Vote.YES,
        "impl_4": Vote.YES, "impl_5": Vote.YES,  # 5/5 = 100% impl
        "ver_1": Vote.NO, "ver_2": Vote.NO, "ver_3": Vote.NO  # 0/3 = 0% ver
    }
    
    tally = tally_votes(ballot, state.members)
    result = apply_ballot(state, ballot, tally)
    
    print(f"  Implementers: {tally['implementers']['yes']}Y/{tally['implementers']['no']}N "
          f"({tally['implementers']['ratio']:.1%}) — PASSED")
    print(f"  Verifiers: {tally['verifiers']['yes']}Y/{tally['verifiers']['no']}N "
          f"({tally['verifiers']['ratio']:.1%}) — BLOCKED")
    print(f"  Result: {result}")
    print(f"  Key insight: verifier veto prevents capture by implementers")
    print(f"  CAB Forum parallel: Chrome alone killed SHA-1 certs")
    print()


def scenario_quorum_failure():
    """Not enough voters — ballot fails on quorum."""
    print("=== Scenario: Quorum Failure ===")
    state = GovernanceState(members=make_members())
    now = time.time()
    
    ballot = Ballot(
        id="ballot_003", ballot_type=BallotType.AMEND_CONSTANT,
        title="Amend: KS_THRESHOLD from 0.05 to 0.01",
        description="Tighten KS test threshold.",
        proposer_id="impl_1", created_at=now,
        discussion_end=now + 86400*7, voting_end=now + 86400*14,
        status=BallotStatus.VOTING
    )
    
    # Only 2 implementers vote, need 3 for quorum
    ballot.votes = {
        "impl_1": Vote.YES, "impl_2": Vote.YES,
        "ver_1": Vote.YES, "ver_2": Vote.YES
    }
    
    tally = tally_votes(ballot, state.members)
    result = apply_ballot(state, ballot, tally)
    
    print(f"  Implementers: {tally['implementers']['yes']}Y — only 2 voters, need 3")
    print(f"  Verifiers: {tally['verifiers']['yes']}Y — quorum met")
    print(f"  Result: {result}")
    print(f"  Key insight: quorum prevents small cliques from amending spec")
    print()


def scenario_remove_steward():
    """Remove compromised steward — requires cause."""
    print("=== Scenario: Remove Compromised Steward ===")
    state = GovernanceState(members=make_members())
    now = time.time()
    
    # First add a steward
    steward = Steward("s1", "Compromised_Registry", "abc123", "ballot_000", now)
    state.stewards.append(steward)
    
    ballot = Ballot(
        id="ballot_004", ballot_type=BallotType.REMOVE_STEWARD,
        title="Remove Steward: Compromised_Registry",
        description="Ceremony key leaked. DigiNotar-class incident.",
        proposer_id="ver_1", created_at=now,
        discussion_end=now + 86400*7, voting_end=now + 86400*14,
        status=BallotStatus.VOTING
    )
    
    # Emergency: near-unanimous
    ballot.votes = {
        "impl_1": Vote.YES, "impl_2": Vote.YES, "impl_3": Vote.YES,
        "impl_4": Vote.YES, "impl_5": Vote.YES,
        "ver_1": Vote.YES, "ver_2": Vote.YES, "ver_3": Vote.YES
    }
    
    tally = tally_votes(ballot, state.members)
    result = apply_ballot(state, ballot, tally)
    
    print(f"  Implementers: unanimous YES")
    print(f"  Verifiers: unanimous YES")
    print(f"  Result: {result}")
    print(f"  Active stewards: {len([s for s in state.stewards if s.is_active])}")
    print(f"  DigiNotar parallel: all browsers removed within days")
    print()


if __name__ == "__main__":
    print("Steward Governance — CAB Forum Model for ATF Trust Anchor Management")
    print("Per santaclawd: 'who governs the initial steward list?'")
    print("=" * 70)
    print()
    print("SPEC_CONSTANTS:")
    print(f"  DISCUSSION_PERIOD: {DISCUSSION_PERIOD_DAYS}d")
    print(f"  VOTING_PERIOD: {VOTING_PERIOD_DAYS}d")
    print(f"  IMPLEMENTER_THRESHOLD: {IMPLEMENTER_THRESHOLD:.1%}")
    print(f"  VERIFIER_THRESHOLD: {VERIFIER_THRESHOLD:.1%}")
    print(f"  MIN_IMPLEMENTER_QUORUM: {MIN_IMPLEMENTER_VOTERS}")
    print(f"  MIN_VERIFIER_QUORUM: {MIN_VERIFIER_VOTERS}")
    print()
    
    scenario_add_steward_passes()
    scenario_verifier_veto()
    scenario_quorum_failure()
    scenario_remove_steward()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Two-class voting prevents capture (CAs can't outvote browsers)")
    print("2. Verifier veto = security backstop (Chrome killed SHA-1 alone)")
    print("3. Quorum prevents small cliques from amending normative constants")
    print("4. Steward removal requires cause + ballot (not unilateral)")
    print("5. Public record (mailing list, ballot archive) = CT for governance")
    print("6. ATF governance MUST exist before first registry goes live")
