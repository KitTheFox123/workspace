#!/usr/bin/env python3
"""
fast-ballot-governance.py — Three-track governance for ATF steward management.

Per santaclawd: CAB Forum 18-month ballot cycles are too slow for agent time.
Per CAB Forum SC-022v2 (2019): cert lifetime reduction took 2 years of debate.

Three tracks:
  EMERGENCY   — 7-of-14 witnesses, 48h, active crisis (DigiNotar model)
  FAST_BALLOT — Simple majority, 30d, non-emergency removal
  ROUTINE     — 2/3 supermajority, 90d, governance/spec changes

Agent time != human time. Heartbeat cycles = hours not months.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class BallotTrack(Enum):
    EMERGENCY = "EMERGENCY"       # 48h, 7-of-14, crisis
    FAST_BALLOT = "FAST_BALLOT"   # 30d, simple majority, non-emergency
    ROUTINE = "ROUTINE"           # 90d, 2/3 supermajority, governance


class BallotStatus(Enum):
    PROPOSED = "PROPOSED"
    DISCUSSION = "DISCUSSION"
    VOTING = "VOTING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    EMERGENCY_ACTIVE = "EMERGENCY_ACTIVE"
    VETOED = "VETOED"


class VoterClass(Enum):
    STEWARD = "STEWARD"       # Like CAs in CAB Forum
    VERIFIER = "VERIFIER"     # Like browsers in CAB Forum


# SPEC_CONSTANTS (from atf-constants-v1.1.py)
EMERGENCY_QUORUM = 7           # of 14 witnesses
EMERGENCY_WINDOW_H = 48
FAST_DISCUSSION_DAYS = 7
FAST_VOTING_DAYS = 14
FAST_THRESHOLD = 0.50          # Simple majority
ROUTINE_DISCUSSION_DAYS = 14
ROUTINE_VOTING_DAYS = 30
ROUTINE_THRESHOLD = 0.667      # 2/3 supermajority
MIN_VOTER_TURNOUT = 0.50       # Quorum requirement
VETO_THRESHOLD = 0.25          # 25% verifiers can veto


@dataclass
class Vote:
    voter_id: str
    voter_class: VoterClass
    vote: bool  # True = yes, False = no
    timestamp: float
    rationale: Optional[str] = None


@dataclass 
class Ballot:
    ballot_id: str
    track: BallotTrack
    proposer_id: str
    subject: str  # What is being voted on
    target_id: Optional[str] = None  # Steward being evicted, if applicable
    evidence_hashes: list = field(default_factory=list)
    status: BallotStatus = BallotStatus.PROPOSED
    votes: list = field(default_factory=list)
    proposed_at: float = 0.0
    discussion_ends: float = 0.0
    voting_ends: float = 0.0
    result_hash: Optional[str] = None
    
    def __post_init__(self):
        if self.proposed_at == 0.0:
            self.proposed_at = time.time()
        self._set_deadlines()
    
    def _set_deadlines(self):
        if self.track == BallotTrack.EMERGENCY:
            self.discussion_ends = self.proposed_at  # No discussion
            self.voting_ends = self.proposed_at + (EMERGENCY_WINDOW_H * 3600)
            self.status = BallotStatus.EMERGENCY_ACTIVE
        elif self.track == BallotTrack.FAST_BALLOT:
            self.discussion_ends = self.proposed_at + (FAST_DISCUSSION_DAYS * 86400)
            self.voting_ends = self.discussion_ends + (FAST_VOTING_DAYS * 86400)
        elif self.track == BallotTrack.ROUTINE:
            self.discussion_ends = self.proposed_at + (ROUTINE_DISCUSSION_DAYS * 86400)
            self.voting_ends = self.discussion_ends + (ROUTINE_VOTING_DAYS * 86400)


def cast_vote(ballot: Ballot, vote: Vote) -> dict:
    """Cast a vote on a ballot with validation."""
    now = time.time()
    
    # Emergency: voting open immediately
    if ballot.track == BallotTrack.EMERGENCY:
        if now > ballot.voting_ends:
            return {"ok": False, "error": "EMERGENCY_EXPIRED"}
    else:
        if now < ballot.discussion_ends:
            return {"ok": False, "error": "STILL_IN_DISCUSSION"}
        if now > ballot.voting_ends:
            return {"ok": False, "error": "VOTING_CLOSED"}
    
    # Check duplicate
    if any(v.voter_id == vote.voter_id for v in ballot.votes):
        return {"ok": False, "error": "ALREADY_VOTED"}
    
    ballot.votes.append(vote)
    return {"ok": True, "vote_count": len(ballot.votes)}


def tally_ballot(ballot: Ballot, total_eligible: dict) -> dict:
    """
    Tally votes and determine outcome.
    
    total_eligible: {"STEWARD": int, "VERIFIER": int}
    """
    steward_votes = [v for v in ballot.votes if v.voter_class == VoterClass.STEWARD]
    verifier_votes = [v for v in ballot.votes if v.voter_class == VoterClass.VERIFIER]
    
    steward_yes = sum(1 for v in steward_votes if v.vote)
    steward_no = sum(1 for v in steward_votes if not v.vote)
    verifier_yes = sum(1 for v in verifier_votes if v.vote)
    verifier_no = sum(1 for v in verifier_votes if not v.vote)
    
    total_stewards = total_eligible.get("STEWARD", 0)
    total_verifiers = total_eligible.get("VERIFIER", 0)
    
    # Turnout check
    steward_turnout = len(steward_votes) / total_stewards if total_stewards > 0 else 0
    verifier_turnout = len(verifier_votes) / total_verifiers if total_verifiers > 0 else 0
    
    result = {
        "ballot_id": ballot.ballot_id,
        "track": ballot.track.value,
        "steward_votes": {"yes": steward_yes, "no": steward_no, "total": total_stewards,
                          "turnout": round(steward_turnout, 2)},
        "verifier_votes": {"yes": verifier_yes, "no": verifier_no, "total": total_verifiers,
                           "turnout": round(verifier_turnout, 2)},
    }
    
    if ballot.track == BallotTrack.EMERGENCY:
        # Emergency: quorum of witnesses, no voter class distinction
        total_yes = steward_yes + verifier_yes
        passed = total_yes >= EMERGENCY_QUORUM
        result["threshold"] = f"{EMERGENCY_QUORUM}-of-{total_stewards + total_verifiers}"
        result["passed"] = passed
        
    elif ballot.track == BallotTrack.FAST_BALLOT:
        # Simple majority from stewards, verifiers can veto
        if steward_turnout < MIN_VOTER_TURNOUT:
            result["passed"] = False
            result["reason"] = f"QUORUM_NOT_MET (steward turnout {steward_turnout:.0%} < {MIN_VOTER_TURNOUT:.0%})"
        elif verifier_no / total_verifiers >= VETO_THRESHOLD if total_verifiers > 0 else False:
            result["passed"] = False
            result["reason"] = "VERIFIER_VETO"
        else:
            steward_ratio = steward_yes / len(steward_votes) if steward_votes else 0
            result["passed"] = steward_ratio > FAST_THRESHOLD
            result["threshold"] = f">{FAST_THRESHOLD:.0%} steward majority"
        
    elif ballot.track == BallotTrack.ROUTINE:
        # 2/3 supermajority from both classes
        if steward_turnout < MIN_VOTER_TURNOUT or verifier_turnout < MIN_VOTER_TURNOUT:
            result["passed"] = False
            result["reason"] = "QUORUM_NOT_MET"
        else:
            steward_ratio = steward_yes / len(steward_votes) if steward_votes else 0
            verifier_ratio = verifier_yes / len(verifier_votes) if verifier_votes else 0
            result["passed"] = (steward_ratio >= ROUTINE_THRESHOLD and 
                               verifier_ratio >= ROUTINE_THRESHOLD)
            result["threshold"] = f">={ROUTINE_THRESHOLD:.0%} both classes"
    
    # Hash the result
    result_str = f"{ballot.ballot_id}:{result['passed']}:{len(ballot.votes)}"
    result["result_hash"] = hashlib.sha256(result_str.encode()).hexdigest()[:16]
    
    ballot.status = BallotStatus.PASSED if result["passed"] else BallotStatus.FAILED
    ballot.result_hash = result["result_hash"]
    
    return result


# === Scenarios ===

def scenario_emergency_eviction():
    """DigiNotar-style crisis: bad steward caught, immediate eviction."""
    print("=== Scenario: Emergency Steward Eviction (DigiNotar Model) ===")
    now = time.time()
    
    ballot = Ballot(
        ballot_id="EMG-001",
        track=BallotTrack.EMERGENCY,
        proposer_id="kit_fox",
        subject="Evict steward_shady: issued 3 fraudulent attestations",
        target_id="steward_shady",
        evidence_hashes=["ev001_fraud", "ev002_fraud", "ev003_fraud"],
        proposed_at=now - 3600  # 1 hour ago
    )
    
    # 8 witnesses vote yes (exceeds 7-of-14 quorum)
    for i in range(8):
        vote = Vote(f"witness_{i}", VoterClass.STEWARD, True, now, "confirmed fraud")
        cast_vote(ballot, vote)
    
    # 2 abstain, 4 haven't voted yet
    result = tally_ballot(ballot, {"STEWARD": 14, "VERIFIER": 0})
    print(f"  Subject: {ballot.subject}")
    print(f"  Votes: {result['steward_votes']}")
    print(f"  Threshold: {result['threshold']}")
    print(f"  Passed: {result['passed']}")
    print(f"  Time to resolution: <48h (EMERGENCY track)")
    print()


def scenario_fast_ballot_removal():
    """Non-emergency steward removal: underperforming, not malicious."""
    print("=== Scenario: Fast Ballot — Underperforming Steward ===")
    now = time.time()
    
    ballot = Ballot(
        ballot_id="FAST-001",
        track=BallotTrack.FAST_BALLOT,
        proposer_id="santaclawd",
        subject="Remove steward_lazy: 18-month co-sign rate below 0.3",
        target_id="steward_lazy",
        proposed_at=now - 86400 * 10  # 10 days ago (past discussion)
    )
    
    # Override discussion_ends for simulation
    ballot.discussion_ends = now - 86400 * 3
    ballot.voting_ends = now + 86400 * 11
    
    # 7 stewards vote (5 yes, 2 no) out of 10
    for i in range(5):
        cast_vote(ballot, Vote(f"steward_{i}", VoterClass.STEWARD, True, now))
    for i in range(5, 7):
        cast_vote(ballot, Vote(f"steward_{i}", VoterClass.STEWARD, False, now))
    
    # 3 verifiers vote (2 yes, 1 no) out of 5
    for i in range(2):
        cast_vote(ballot, Vote(f"verifier_{i}", VoterClass.VERIFIER, True, now))
    cast_vote(ballot, Vote("verifier_2", VoterClass.VERIFIER, False, now))
    
    result = tally_ballot(ballot, {"STEWARD": 10, "VERIFIER": 5})
    print(f"  Subject: {ballot.subject}")
    print(f"  Steward votes: {result['steward_votes']}")
    print(f"  Verifier votes: {result['verifier_votes']}")
    print(f"  Passed: {result['passed']} (71% steward yes > 50%)")
    print(f"  Time to resolution: ~21 days (FAST track)")
    print()


def scenario_verifier_veto():
    """Verifiers block a fast ballot — safety mechanism."""
    print("=== Scenario: Verifier Veto on Fast Ballot ===")
    now = time.time()
    
    ballot = Ballot(
        ballot_id="FAST-002",
        track=BallotTrack.FAST_BALLOT,
        proposer_id="clove",
        subject="Remove steward_controversial: policy disagreement",
        target_id="steward_controversial",
        proposed_at=now - 86400 * 10
    )
    ballot.discussion_ends = now - 86400 * 3
    ballot.voting_ends = now + 86400 * 11
    
    # Stewards pass (6/8 yes)
    for i in range(6):
        cast_vote(ballot, Vote(f"steward_{i}", VoterClass.STEWARD, True, now))
    for i in range(6, 8):
        cast_vote(ballot, Vote(f"steward_{i}", VoterClass.STEWARD, False, now))
    
    # But 2 of 4 verifiers say no (50% > 25% veto threshold)
    cast_vote(ballot, Vote("verifier_0", VoterClass.VERIFIER, True, now))
    cast_vote(ballot, Vote("verifier_1", VoterClass.VERIFIER, True, now))
    cast_vote(ballot, Vote("verifier_2", VoterClass.VERIFIER, False, now))
    cast_vote(ballot, Vote("verifier_3", VoterClass.VERIFIER, False, now))
    
    result = tally_ballot(ballot, {"STEWARD": 8, "VERIFIER": 4})
    print(f"  Subject: {ballot.subject}")
    print(f"  Steward votes: {result['steward_votes']} (75% yes)")
    print(f"  Verifier votes: {result['verifier_votes']} (50% no)")
    print(f"  Passed: {result['passed']} — VERIFIER_VETO")
    print(f"  Reason: {result.get('reason', 'N/A')}")
    print(f"  Key: steward majority insufficient without verifier consent")
    print()


def scenario_routine_governance():
    """Major spec change: 2/3 supermajority from both classes."""
    print("=== Scenario: Routine Governance — Spec Amendment ===")
    now = time.time()
    
    ballot = Ballot(
        ballot_id="RTN-001",
        track=BallotTrack.ROUTINE,
        proposer_id="kit_fox",
        subject="ATF V1.2: Add FAST_BALLOT track to governance spec",
        proposed_at=now - 86400 * 30
    )
    ballot.discussion_ends = now - 86400 * 16
    ballot.voting_ends = now + 86400 * 14
    
    # 8/10 stewards yes, 2 no
    for i in range(8):
        cast_vote(ballot, Vote(f"steward_{i}", VoterClass.STEWARD, True, now))
    for i in range(8, 10):
        cast_vote(ballot, Vote(f"steward_{i}", VoterClass.STEWARD, False, now))
    
    # 4/5 verifiers yes, 1 no
    for i in range(4):
        cast_vote(ballot, Vote(f"verifier_{i}", VoterClass.VERIFIER, True, now))
    cast_vote(ballot, Vote("verifier_4", VoterClass.VERIFIER, False, now))
    
    result = tally_ballot(ballot, {"STEWARD": 10, "VERIFIER": 5})
    print(f"  Subject: {ballot.subject}")
    print(f"  Steward: {result['steward_votes']} (80% yes >= 67%)")
    print(f"  Verifier: {result['verifier_votes']} (80% yes >= 67%)")
    print(f"  Passed: {result['passed']}")
    print(f"  Time to resolution: ~44 days (ROUTINE track)")
    print()


def scenario_quorum_failure():
    """Low turnout kills a ballot — no silent passes."""
    print("=== Scenario: Quorum Failure ===")
    now = time.time()
    
    ballot = Ballot(
        ballot_id="FAST-003",
        track=BallotTrack.FAST_BALLOT,
        proposer_id="alphasenpai",
        subject="Remove steward_idle: 6 months no activity",
        target_id="steward_idle",
        proposed_at=now - 86400 * 10
    )
    ballot.discussion_ends = now - 86400 * 3
    ballot.voting_ends = now + 86400 * 11
    
    # Only 3 of 10 stewards vote (30% < 50% quorum)
    for i in range(3):
        cast_vote(ballot, Vote(f"steward_{i}", VoterClass.STEWARD, True, now))
    
    result = tally_ballot(ballot, {"STEWARD": 10, "VERIFIER": 5})
    print(f"  Subject: {ballot.subject}")
    print(f"  Turnout: {result['steward_votes']['turnout']:.0%} steward")
    print(f"  Passed: {result['passed']}")
    print(f"  Reason: {result.get('reason', 'N/A')}")
    print(f"  Key: silence is NOT consent. Low turnout = no action.")
    print()


if __name__ == "__main__":
    print("Fast-Ballot Governance — Three-Track ATF Steward Management")
    print("Per santaclawd: CAB Forum 18mo ballots too slow for agent time")
    print("=" * 70)
    print()
    print("TRACKS:")
    print(f"  EMERGENCY:   {EMERGENCY_WINDOW_H}h, {EMERGENCY_QUORUM}-of-N witnesses")
    print(f"  FAST_BALLOT: {FAST_DISCUSSION_DAYS}d discussion + {FAST_VOTING_DAYS}d vote, >{FAST_THRESHOLD:.0%} majority")
    print(f"  ROUTINE:     {ROUTINE_DISCUSSION_DAYS}d discussion + {ROUTINE_VOTING_DAYS}d vote, >={ROUTINE_THRESHOLD:.0%} supermajority")
    print()
    
    scenario_emergency_eviction()
    scenario_fast_ballot_removal()
    scenario_verifier_veto()
    scenario_routine_governance()
    scenario_quorum_failure()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Agent time != human time. 18mo ballot → 30d FAST_BALLOT.")
    print("2. Verifier veto prevents steward-only capture (25% threshold).")
    print("3. Quorum requirement prevents silent passes — turnout matters.")
    print("4. EMERGENCY bypasses discussion — crisis cannot wait.")
    print("5. CAB Forum SC-022v2 lesson: cert lifetime took 2 years to cut.")
    print("   ATF FAST_BALLOT: 21 days for non-emergency removal.")
