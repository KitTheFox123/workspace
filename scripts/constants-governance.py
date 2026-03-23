#!/usr/bin/env python3
"""
constants-governance.py — CAB Forum-style governance for ATF spec constants.

Per santaclawd: "constants get specified, but who amends them?"
X.509 lesson: SHA-1 deprecation took 10 years because upgrade paths
weren't normative at spec time.

CAB Forum Ballot 187 model:
  - CAs vote (implementers) + browsers vote (verifiers)
  - 2/3 CA majority + 50%+1 browser majority
  - 7-day discussion + 7-day vote + 30-day review
  - Effective date explicitly set (Ballot 187: Sept 8, 2017)

ATF equivalent:
  - Implementers = agents who emit receipts
  - Verifiers = counterparties who check receipts
  - Amendment requires both classes to agree
  - Migration window per constant change

Usage:
    python3 constants-governance.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class VoterClass(Enum):
    IMPLEMENTER = "implementer"  # Agents emitting ATF receipts (like CAs)
    VERIFIER = "verifier"        # Counterparties checking receipts (like browsers)


class BallotStatus(Enum):
    DRAFT = "draft"
    DISCUSSION = "discussion"
    VOTING = "voting"
    REVIEW = "review"
    EFFECTIVE = "effective"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class ConstantType(Enum):
    CRYPTOGRAPHIC = "cryptographic"    # Hash algorithms, key sizes
    THRESHOLD = "threshold"            # Trust floors, ceilings
    TEMPORAL = "temporal"              # Timeouts, windows, TTLs
    QUORUM = "quorum"                  # Witness counts, BFT bounds
    STRUCTURAL = "structural"          # Field counts, layer counts


@dataclass
class SpecConstant:
    name: str
    value: str
    constant_type: ConstantType
    rationale: str
    effective_since: str  # Version or date
    amendment_track: Optional[str] = None  # Which ballot changed it


@dataclass
class Vote:
    voter_id: str
    voter_class: VoterClass
    vote: str  # "yes", "no", "abstain"
    timestamp: float = field(default_factory=time.time)


@dataclass
class Ballot:
    ballot_id: str
    title: str
    constant_name: str
    old_value: str
    new_value: str
    rationale: str
    proposer: str
    endorsers: list[str]  # Need 2 endorsers (CAB Forum rule)
    status: BallotStatus = BallotStatus.DRAFT
    votes: list[Vote] = field(default_factory=list)
    discussion_start: Optional[float] = None
    vote_start: Optional[float] = None
    vote_end: Optional[float] = None
    effective_date: Optional[str] = None
    migration_window_days: int = 30  # Default 30-day review

    def _hash(self) -> str:
        canonical = f"{self.ballot_id}|{self.constant_name}|{self.old_value}|{self.new_value}"
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


class ConstantsGovernance:
    """CAB Forum-style governance for ATF constants."""

    # Thresholds (from Ballot 187 bylaws)
    IMPLEMENTER_THRESHOLD = 2 / 3  # 2/3 majority
    VERIFIER_THRESHOLD = 0.501      # 50% + 1
    MIN_ENDORSERS = 2
    DISCUSSION_DAYS = 7
    VOTING_DAYS = 7
    REVIEW_DAYS = 30

    def __init__(self):
        self.constants: dict[str, SpecConstant] = {}
        self.ballots: list[Ballot] = []
        self._init_constants()

    def _init_constants(self):
        """Initialize ATF spec constants (from atf-constants.py)."""
        defaults = [
            ("MIN_WITNESSES", "3", ConstantType.QUORUM,
             "Minimum independent witnesses for ceremony. BFT f<n/3 requires n≥3."),
            ("SPEC_MINIMUM_WINDOW", "86400", ConstantType.TEMPORAL,
             "24h minimum migration window. TLS cipher suite model."),
            ("COLD_START_Z", "1.96", ConstantType.THRESHOLD,
             "Wilson CI z-score. 95% confidence interval."),
            ("JS_DIVERGENCE_FLOOR", "0.3", ConstantType.THRESHOLD,
             "Jensen-Shannon divergence floor for drift detection."),
            ("CORRECTION_RANGE_LOW", "0.05", ConstantType.THRESHOLD,
             "Minimum healthy correction frequency."),
            ("CORRECTION_RANGE_HIGH", "0.40", ConstantType.THRESHOLD,
             "Maximum healthy correction frequency."),
            ("DECAY_HALFLIFE_DAYS", "30", ConstantType.TEMPORAL,
             "Trust decay half-life in days."),
            ("HASH_ALGORITHM", "sha256", ConstantType.CRYPTOGRAPHIC,
             "Default hash algorithm. SHA-256."),
            ("MIN_COUNTERPARTIES", "3", ConstantType.QUORUM,
             "Minimum counterparties before migration."),
            ("MUST_FIELD_COUNT", "13", ConstantType.STRUCTURAL,
             "Number of MUST fields in ATF-core."),
        ]
        for name, value, ctype, rationale in defaults:
            self.constants[name] = SpecConstant(
                name=name, value=value, constant_type=ctype,
                rationale=rationale, effective_since="v1.0.0",
            )

    def propose_ballot(
        self, ballot_id: str, title: str, constant_name: str,
        new_value: str, rationale: str, proposer: str,
        endorsers: list[str], migration_window_days: int = 30,
    ) -> dict:
        """Propose a ballot to amend a constant."""
        if constant_name not in self.constants:
            return {"status": "REJECTED", "reason": "unknown_constant"}

        if len(endorsers) < self.MIN_ENDORSERS:
            return {"status": "REJECTED", "reason": f"need_{self.MIN_ENDORSERS}_endorsers"}

        old = self.constants[constant_name]
        ballot = Ballot(
            ballot_id=ballot_id, title=title,
            constant_name=constant_name,
            old_value=old.value, new_value=new_value,
            rationale=rationale, proposer=proposer,
            endorsers=endorsers,
            migration_window_days=migration_window_days,
            discussion_start=time.time(),
            status=BallotStatus.DISCUSSION,
        )
        self.ballots.append(ballot)
        return {
            "status": "DISCUSSION",
            "ballot_id": ballot_id,
            "ballot_hash": ballot._hash(),
            "constant": constant_name,
            "old_value": old.value,
            "new_value": new_value,
            "discussion_days": self.DISCUSSION_DAYS,
            "voting_days": self.VOTING_DAYS,
            "review_days": self.REVIEW_DAYS,
        }

    def cast_vote(self, ballot_id: str, voter_id: str,
                  voter_class: VoterClass, vote: str) -> dict:
        """Cast a vote on a ballot."""
        ballot = next((b for b in self.ballots if b.ballot_id == ballot_id), None)
        if not ballot:
            return {"status": "REJECTED", "reason": "unknown_ballot"}

        if vote not in ("yes", "no", "abstain"):
            return {"status": "REJECTED", "reason": "invalid_vote"}

        # Replace existing vote from same voter
        ballot.votes = [v for v in ballot.votes if v.voter_id != voter_id]
        ballot.votes.append(Vote(
            voter_id=voter_id, voter_class=voter_class, vote=vote,
        ))
        return {"status": "RECORDED", "voter": voter_id, "vote": vote}

    def tally_ballot(self, ballot_id: str) -> dict:
        """Tally votes and determine outcome."""
        ballot = next((b for b in self.ballots if b.ballot_id == ballot_id), None)
        if not ballot:
            return {"status": "REJECTED", "reason": "unknown_ballot"}

        impl_votes = [v for v in ballot.votes if v.voter_class == VoterClass.IMPLEMENTER]
        ver_votes = [v for v in ballot.votes if v.voter_class == VoterClass.VERIFIER]

        def tally(votes):
            yes = sum(1 for v in votes if v.vote == "yes")
            no = sum(1 for v in votes if v.vote == "no")
            abstain = sum(1 for v in votes if v.vote == "abstain")
            total = yes + no  # Abstains don't count for threshold
            ratio = yes / total if total > 0 else 0
            return {"yes": yes, "no": no, "abstain": abstain, "ratio": ratio}

        impl_tally = tally(impl_votes)
        ver_tally = tally(ver_votes)

        impl_pass = impl_tally["ratio"] >= self.IMPLEMENTER_THRESHOLD
        ver_pass = ver_tally["ratio"] >= self.VERIFIER_THRESHOLD

        # Both classes must have at least 1 yes vote
        impl_represented = impl_tally["yes"] > 0
        ver_represented = ver_tally["yes"] > 0

        passed = impl_pass and ver_pass and impl_represented and ver_represented

        if passed:
            ballot.status = BallotStatus.REVIEW
            effective = f"v1.1.0 (+{ballot.migration_window_days}d)"
            ballot.effective_date = effective
        else:
            ballot.status = BallotStatus.REJECTED

        return {
            "ballot_id": ballot_id,
            "constant": ballot.constant_name,
            "old_value": ballot.old_value,
            "new_value": ballot.new_value,
            "implementer_tally": impl_tally,
            "verifier_tally": ver_tally,
            "implementer_threshold": f"{self.IMPLEMENTER_THRESHOLD:.0%}",
            "verifier_threshold": f"{self.VERIFIER_THRESHOLD:.0%}",
            "implementer_pass": impl_pass,
            "verifier_pass": ver_pass,
            "passed": passed,
            "status": ballot.status.value,
            "effective_date": ballot.effective_date,
            "migration_window_days": ballot.migration_window_days,
        }


def demo():
    print("=" * 60)
    print("Constants Governance — CAB Forum Model for ATF")
    print("=" * 60)

    gov = ConstantsGovernance()

    # Show current constants
    print("\n--- Current ATF Constants ---")
    for name, const in sorted(gov.constants.items()):
        print(f"  {name} = {const.value} ({const.constant_type.value})")

    # Scenario 1: Propose upgrading hash algorithm
    print("\n--- Ballot 1: Upgrade HASH_ALGORITHM to sha3-256 ---")
    result = gov.propose_ballot(
        ballot_id="ATF-B001",
        title="Upgrade default hash to SHA3-256",
        constant_name="HASH_ALGORITHM",
        new_value="sha3-256",
        rationale="SHA-256 quantum vulnerability timeline shortening. SHA3-256 provides post-quantum margin.",
        proposer="kit_fox",
        endorsers=["santaclawd", "augur"],
        migration_window_days=90,
    )
    print(json.dumps(result, indent=2))

    # Cast votes
    votes = [
        ("kit_fox", VoterClass.IMPLEMENTER, "yes"),
        ("santaclawd", VoterClass.IMPLEMENTER, "yes"),
        ("augur", VoterClass.IMPLEMENTER, "yes"),
        ("bro_agent", VoterClass.IMPLEMENTER, "no"),
        ("clove", VoterClass.VERIFIER, "yes"),
        ("neondrift", VoterClass.VERIFIER, "yes"),
        ("sighter", VoterClass.VERIFIER, "abstain"),
    ]
    for voter, vclass, vote in votes:
        gov.cast_vote("ATF-B001", voter, vclass, vote)

    tally = gov.tally_ballot("ATF-B001")
    print("\n--- Ballot 1 Tally ---")
    print(json.dumps(tally, indent=2))

    # Scenario 2: Try to change MIN_WITNESSES without enough endorsers
    print("\n--- Ballot 2: Reduce MIN_WITNESSES (should fail — 1 endorser) ---")
    result2 = gov.propose_ballot(
        ballot_id="ATF-B002",
        title="Reduce MIN_WITNESSES to 2",
        constant_name="MIN_WITNESSES",
        new_value="2",
        rationale="Reduce ceremony overhead",
        proposer="lazy_agent",
        endorsers=["only_one"],
    )
    print(json.dumps(result2, indent=2))

    # Scenario 3: Ballot that fails verifier threshold
    print("\n--- Ballot 3: Change JS_DIVERGENCE_FLOOR (verifiers reject) ---")
    gov.propose_ballot(
        ballot_id="ATF-B003",
        title="Lower JS divergence floor",
        constant_name="JS_DIVERGENCE_FLOOR",
        new_value="0.15",
        rationale="Current floor too aggressive for small agents",
        proposer="small_agent",
        endorsers=["friend1", "friend2"],
    )

    # Implementers say yes, verifiers say no
    for v in ["small_agent", "friend1", "friend2"]:
        gov.cast_vote("ATF-B003", v, VoterClass.IMPLEMENTER, "yes")
    gov.cast_vote("ATF-B003", "clove", VoterClass.VERIFIER, "no")
    gov.cast_vote("ATF-B003", "neondrift", VoterClass.VERIFIER, "no")

    tally3 = gov.tally_ballot("ATF-B003")
    print(json.dumps(tally3, indent=2))

    print("\n" + "=" * 60)
    print("CAB Forum model: implementers (2/3) + verifiers (50%+1).")
    print("Both classes must be represented. Migration window per change.")
    print("SHA-1 took 10 years. ATF won't repeat that mistake.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
