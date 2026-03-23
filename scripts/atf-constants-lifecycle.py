#!/usr/bin/env python3
"""
atf-constants-lifecycle.py — ATF constants amendment governance.

Per santaclawd: "constants get specified, but who amends them?"
X.509 SHA-1 deprecation took 10 years because upgrade paths
were not normative at spec time.

Each ATF constant gets:
  - amendment_track: FROZEN | NORMATIVE_AMENDMENT | DEPRECATED
  - effective_date: when the constant becomes active
  - migration_window: how long old value remains valid
  - deprecation_date: when old value becomes REJECTED

Inspired by:
  - IETF RFC lifecycle (Proposed → Standard → Historic)
  - CA/Browser Forum Ballot process
  - TLS cipher suite deprecation model

Usage:
    python3 atf-constants-lifecycle.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AmendmentTrack(Enum):
    FROZEN = "FROZEN"              # Cannot be changed (like HTTP status codes)
    NORMATIVE = "NORMATIVE"        # Active, may be amended via ballot
    DEPRECATED = "DEPRECATED"      # Scheduled for removal
    HISTORIC = "HISTORIC"          # Removed, kept for reference


class BallotStatus(Enum):
    PROPOSED = "PROPOSED"
    DISCUSSION = "DISCUSSION"      # 14-day discussion period
    VOTING = "VOTING"              # 7-day voting period  
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


@dataclass
class ATFConstant:
    """An ATF spec constant with full lifecycle metadata."""
    name: str
    value: object
    track: AmendmentTrack
    effective_date: float                      # Unix timestamp
    migration_window_days: int = 90            # How long old value valid
    deprecation_date: Optional[float] = None
    rationale: str = ""
    predecessor: Optional[str] = None          # Previous value
    ballot_id: Optional[str] = None            # Which ballot created this


@dataclass
class Ballot:
    """CA/Browser Forum-style ballot for constant amendments."""
    id: str
    constant_name: str
    proposed_value: object
    proposer: str
    rationale: str
    status: BallotStatus = BallotStatus.PROPOSED
    discussion_start: Optional[float] = None
    voting_start: Optional[float] = None
    votes_for: list = field(default_factory=list)
    votes_against: list = field(default_factory=list)
    abstentions: list = field(default_factory=list)
    migration_window_days: int = 90
    effective_date: Optional[float] = None


class ATFConstantsLifecycle:
    """Manage ATF constants with amendment governance."""

    # ATF-core constants with tracks
    CONSTANTS = {
        # FROZEN: cannot change without major version bump
        "MIN_WITNESSES": ATFConstant(
            "MIN_WITNESSES", 3, AmendmentTrack.FROZEN,
            effective_date=time.time(),
            rationale="CA/Browser Ballot 187: 'reasonable' left impl-defined caused failures"
        ),
        "SPEC_MINIMUM_WINDOW": ATFConstant(
            "SPEC_MINIMUM_WINDOW", 86400, AmendmentTrack.FROZEN,  # 24h in seconds
            effective_date=time.time(),
            rationale="Minimum key migration window. Floor, not ceiling."
        ),
        "ATF_MUST_FIELD_COUNT": ATFConstant(
            "ATF_MUST_FIELD_COUNT", 14, AmendmentTrack.FROZEN,
            effective_date=time.time(),
            rationale="Fields whose absence breaks verification"
        ),
        
        # NORMATIVE: can be amended via ballot
        "COLD_START_Z": ATFConstant(
            "COLD_START_Z", 1.96, AmendmentTrack.NORMATIVE,
            effective_date=time.time(),
            rationale="95% CI anchor for Wilson score. SPEC_NORMATIVE per santaclawd."
        ),
        "JS_DIVERGENCE_FLOOR": ATFConstant(
            "JS_DIVERGENCE_FLOOR", 0.3, AmendmentTrack.NORMATIVE,
            effective_date=time.time(),
            rationale="Minimum JS divergence for OP_DRIFT detection"
        ),
        "CORRECTION_RANGE_MIN": ATFConstant(
            "CORRECTION_RANGE_MIN", 0.05, AmendmentTrack.NORMATIVE,
            effective_date=time.time(),
            rationale="Healthy correction frequency floor"
        ),
        "CORRECTION_RANGE_MAX": ATFConstant(
            "CORRECTION_RANGE_MAX", 0.40, AmendmentTrack.NORMATIVE,
            effective_date=time.time(),
            rationale="Healthy correction frequency ceiling"
        ),
        "DECAY_HALFLIFE_DAYS": ATFConstant(
            "DECAY_HALFLIFE_DAYS", 30, AmendmentTrack.NORMATIVE,
            effective_date=time.time(),
            rationale="Trust decay half-life"
        ),
        "COLD_START_CEILING": ATFConstant(
            "COLD_START_CEILING", 0.89, AmendmentTrack.NORMATIVE,
            effective_date=time.time(),
            rationale="Max trust at n=30. Spec-normative per santaclawd."
        ),
        
        # ERROR ENUM: frozen core, extensible
        "ERROR_ENUM_CORE": ATFConstant(
            "ERROR_ENUM_CORE", [
                "TIMEOUT", "MALFORMED_INPUT", "CAPABILITY_EXCEEDED",
                "DEPENDENCY_FAILURE", "INTERNAL", "SCOPE_VIOLATION",
                "RESOURCE_EXHAUSTED", "UNAUTHORIZED", "REVOKED"
            ],
            AmendmentTrack.FROZEN,
            effective_date=time.time(),
            rationale="Core error types frozen. Extensions via ext:v2:TYPE"
        ),
    }

    def __init__(self):
        self.ballots: dict[str, Ballot] = {}
        self.amendment_log: list[dict] = []

    def propose_amendment(
        self,
        constant_name: str,
        new_value: object,
        proposer: str,
        rationale: str,
        migration_days: int = 90,
    ) -> dict:
        """Propose a constant amendment (CA/Browser Ballot style)."""
        if constant_name not in self.CONSTANTS:
            return {"status": "REJECTED", "reason": f"Unknown constant: {constant_name}"}

        const = self.CONSTANTS[constant_name]
        
        if const.track == AmendmentTrack.FROZEN:
            return {
                "status": "REJECTED",
                "reason": f"{constant_name} is FROZEN. Requires major version bump (ATF v2.0).",
                "lesson": "X.509 SHA-1 was 'normative' — changing it took 10 years. FROZEN prevents this."
            }

        if const.track == AmendmentTrack.HISTORIC:
            return {"status": "REJECTED", "reason": f"{constant_name} is HISTORIC. Cannot amend."}

        ballot_id = f"BAL-{hashlib.sha256(f'{constant_name}{new_value}{time.time()}'.encode()).hexdigest()[:8]}"
        
        ballot = Ballot(
            id=ballot_id,
            constant_name=constant_name,
            proposed_value=new_value,
            proposer=proposer,
            rationale=rationale,
            status=BallotStatus.PROPOSED,
            discussion_start=time.time(),
            migration_window_days=migration_days,
        )
        
        self.ballots[ballot_id] = ballot
        return {
            "status": "PROPOSED",
            "ballot_id": ballot_id,
            "constant": constant_name,
            "current_value": const.value,
            "proposed_value": new_value,
            "discussion_period": "14 days",
            "voting_period": "7 days",
            "migration_window": f"{migration_days} days",
        }

    def vote(self, ballot_id: str, voter: str, vote: str) -> dict:
        """Vote on a ballot. vote = 'for' | 'against' | 'abstain'."""
        if ballot_id not in self.ballots:
            return {"status": "ERROR", "reason": "Unknown ballot"}
        
        ballot = self.ballots[ballot_id]
        if ballot.status not in (BallotStatus.PROPOSED, BallotStatus.DISCUSSION, BallotStatus.VOTING):
            return {"status": "ERROR", "reason": f"Ballot is {ballot.status.value}"}

        ballot.status = BallotStatus.VOTING
        if vote == "for":
            ballot.votes_for.append(voter)
        elif vote == "against":
            ballot.votes_against.append(voter)
        else:
            ballot.abstentions.append(voter)

        return {
            "ballot_id": ballot_id,
            "voter": voter,
            "vote": vote,
            "tally": {
                "for": len(ballot.votes_for),
                "against": len(ballot.votes_against),
                "abstain": len(ballot.abstentions),
            }
        }

    def resolve_ballot(self, ballot_id: str) -> dict:
        """Resolve a ballot. Requires 2/3 majority to pass."""
        if ballot_id not in self.ballots:
            return {"status": "ERROR", "reason": "Unknown ballot"}

        ballot = self.ballots[ballot_id]
        total = len(ballot.votes_for) + len(ballot.votes_against)
        
        if total < 3:  # MIN_WITNESSES applies to governance too
            return {
                "status": "INSUFFICIENT_QUORUM",
                "reason": f"Need ≥3 votes, got {total}",
                "min_witnesses": 3,
            }

        ratio = len(ballot.votes_for) / total if total > 0 else 0
        passed = ratio >= 2/3

        if passed:
            ballot.status = BallotStatus.ACCEPTED
            ballot.effective_date = time.time() + (ballot.migration_window_days * 86400)
            
            # Update constant
            const = self.CONSTANTS[ballot.constant_name]
            old_value = const.value
            
            self.amendment_log.append({
                "ballot_id": ballot_id,
                "constant": ballot.constant_name,
                "old_value": old_value,
                "new_value": ballot.proposed_value,
                "effective_date": ballot.effective_date,
                "migration_window_days": ballot.migration_window_days,
                "votes": {"for": len(ballot.votes_for), "against": len(ballot.votes_against)},
            })

            return {
                "status": "ACCEPTED",
                "ballot_id": ballot_id,
                "constant": ballot.constant_name,
                "old_value": old_value,
                "new_value": ballot.proposed_value,
                "effective_in_days": ballot.migration_window_days,
                "vote_ratio": f"{ratio:.1%}",
                "migration": f"Old value valid for {ballot.migration_window_days} days",
            }
        else:
            ballot.status = BallotStatus.REJECTED
            return {
                "status": "REJECTED",
                "ballot_id": ballot_id,
                "vote_ratio": f"{ratio:.1%}",
                "reason": "Did not reach 2/3 majority",
            }

    def audit(self) -> dict:
        """Audit all constants for governance health."""
        frozen = []
        normative = []
        deprecated = []
        issues = []

        for name, const in self.CONSTANTS.items():
            entry = {"name": name, "value": const.value, "track": const.track.value}
            
            if const.track == AmendmentTrack.FROZEN:
                frozen.append(entry)
            elif const.track == AmendmentTrack.NORMATIVE:
                normative.append(entry)
            elif const.track == AmendmentTrack.DEPRECATED:
                deprecated.append(entry)

            # Check for constants without rationale
            if not const.rationale:
                issues.append(f"{name}: missing rationale")

        # Governance health
        total = len(self.CONSTANTS)
        frozen_pct = len(frozen) / total if total > 0 else 0
        
        if frozen_pct > 0.8:
            issues.append("WARNING: >80% constants frozen — spec may be too rigid")
        if frozen_pct < 0.2:
            issues.append("WARNING: <20% constants frozen — spec may be too fluid")

        grade = "A" if not issues else "B" if len(issues) <= 2 else "C"

        return {
            "total_constants": total,
            "frozen": len(frozen),
            "normative": len(normative),
            "deprecated": len(deprecated),
            "frozen_ratio": f"{frozen_pct:.1%}",
            "issues": issues,
            "grade": grade,
            "amendment_log": self.amendment_log,
            "frozen_constants": frozen,
            "normative_constants": normative,
        }


def demo():
    print("=" * 60)
    print("ATF Constants Lifecycle — Amendment Governance")
    print("=" * 60)

    lcm = ATFConstantsLifecycle()

    # Scenario 1: Try to amend a FROZEN constant
    print("\n--- Scenario 1: Amend FROZEN constant (should fail) ---")
    result = lcm.propose_amendment(
        "MIN_WITNESSES", 5, "optimistic_agent",
        "Let's increase to 5 for more security"
    )
    print(json.dumps(result, indent=2))

    # Scenario 2: Amend a NORMATIVE constant (succeeds with ballot)
    print("\n--- Scenario 2: Amend NORMATIVE constant (ballot process) ---")
    result = lcm.propose_amendment(
        "DECAY_HALFLIFE_DAYS", 45, "research_agent",
        "30 days too aggressive for low-activity agents. Warmsley 2025 suggests longer windows.",
        migration_days=60,
    )
    print(json.dumps(result, indent=2))
    ballot_id = result["ballot_id"]

    # Vote
    print("\n--- Voting ---")
    lcm.vote(ballot_id, "kit_fox", "for")
    lcm.vote(ballot_id, "santaclawd", "for")
    lcm.vote(ballot_id, "augur", "for")
    result = lcm.vote(ballot_id, "neondrift", "against")
    print(json.dumps(result, indent=2))

    # Resolve
    print("\n--- Resolve ballot ---")
    result = lcm.resolve_ballot(ballot_id)
    print(json.dumps(result, indent=2))

    # Scenario 3: Rejected ballot
    print("\n--- Scenario 3: Rejected ballot (no quorum) ---")
    result2 = lcm.propose_amendment(
        "JS_DIVERGENCE_FLOOR", 0.5, "loose_agent",
        "0.3 too strict"
    )
    lcm.vote(result2["ballot_id"], "agent_a", "for")
    lcm.vote(result2["ballot_id"], "agent_b", "against")
    resolve = lcm.resolve_ballot(result2["ballot_id"])
    print(json.dumps(resolve, indent=2))

    # Audit
    print("\n--- Governance Audit ---")
    audit = lcm.audit()
    print(json.dumps(audit, indent=2, default=str))

    print("\n" + "=" * 60)
    print("X.509 SHA-1 took 10 years because no amendment track.")
    print("ATF constants: FROZEN (major bump) or NORMATIVE (ballot).")
    print("Every amendment: 14d discussion + 7d voting + migration window.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
