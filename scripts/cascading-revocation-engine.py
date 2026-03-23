#!/usr/bin/env python3
"""
cascading-revocation-engine.py — What happens when a grader gets revoked?

Next open question after enforcement stack closed (santaclawd 2026-03-23):
Agent A trusts B trusts C. B gets revoked. What happens to C's receipts
that were graded by B?

X.509 solved this with CRL + path validation (RFC 5280 §6):
- Every cert has an issuer chain back to a root
- Revoke any intermediate → all certs below are invalid
- Cross-certification (RFC 5217) handles multi-domain

ATF equivalent:
- Every evidence_grade has a grader_id with genesis_hash
- Revoke grader → all grades issued by that grader are TAINTED
- Receipts graded by tainted grader need RE-GRADING or QUARANTINE

Three revocation modes:
1. HARD_CASCADE: grader revoked → all grades immediately invalid
2. SOFT_CASCADE: grader revoked → grades TAINTED, re-grading window opens
3. QUARANTINE: grader revoked → grades frozen, manual review required

Usage:
    python3 cascading-revocation-engine.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum


class RevocationMode(Enum):
    HARD_CASCADE = "HARD_CASCADE"      # X.509 default
    SOFT_CASCADE = "SOFT_CASCADE"      # grace period for re-grading
    QUARANTINE = "QUARANTINE"          # freeze and review


class GradeStatus(Enum):
    VALID = "VALID"
    TAINTED = "TAINTED"               # grader revoked, grade suspect
    INVALID = "INVALID"               # hard cascade, grade dead
    REGRADED = "REGRADED"             # new grader confirmed
    QUARANTINED = "QUARANTINED"       # frozen pending review


@dataclass
class Agent:
    agent_id: str
    genesis_hash: str
    revoked: bool = False
    revoked_at: float = 0.0
    revocation_reason: str = ""


@dataclass
class Grade:
    receipt_id: str
    agent_id: str          # who was graded
    grader_id: str         # who did the grading
    evidence_grade: str    # A-F
    timestamp: float
    status: GradeStatus = GradeStatus.VALID
    regraded_by: str = ""
    original_grade: str = ""


class CascadingRevocationEngine:
    def __init__(self, mode: RevocationMode = RevocationMode.SOFT_CASCADE,
                 regrade_window: int = 72 * 3600):  # 72h default
        self.mode = mode
        self.regrade_window = regrade_window
        self.agents: dict[str, Agent] = {}
        self.grades: list[Grade] = []
        self.grader_graph: dict[str, list[str]] = {}  # grader → [agents graded]

    def register_agent(self, agent_id: str, genesis_hash: str) -> Agent:
        agent = Agent(agent_id=agent_id, genesis_hash=genesis_hash)
        self.agents[agent_id] = agent
        return agent

    def add_grade(self, receipt_id: str, agent_id: str, grader_id: str,
                  evidence_grade: str) -> Grade:
        grade = Grade(
            receipt_id=receipt_id, agent_id=agent_id,
            grader_id=grader_id, evidence_grade=evidence_grade,
            timestamp=time.time(),
        )
        self.grades.append(grade)
        self.grader_graph.setdefault(grader_id, []).append(receipt_id)
        return grade

    def revoke_agent(self, agent_id: str, reason: str = "") -> dict:
        """Revoke an agent and cascade to all grades they issued."""
        if agent_id not in self.agents:
            return {"error": f"unknown agent: {agent_id}"}

        agent = self.agents[agent_id]
        agent.revoked = True
        agent.revoked_at = time.time()
        agent.revocation_reason = reason

        # Find all grades issued by this agent (as grader)
        affected_receipts = self.grader_graph.get(agent_id, [])
        affected_grades = [g for g in self.grades if g.grader_id == agent_id]

        cascade_results = []
        for grade in affected_grades:
            original_status = grade.status
            if self.mode == RevocationMode.HARD_CASCADE:
                grade.status = GradeStatus.INVALID
                action = "INVALIDATED"
            elif self.mode == RevocationMode.SOFT_CASCADE:
                grade.status = GradeStatus.TAINTED
                action = "TAINTED (re-grading window open)"
            else:  # QUARANTINE
                grade.status = GradeStatus.QUARANTINED
                action = "QUARANTINED (manual review required)"

            cascade_results.append({
                "receipt_id": grade.receipt_id,
                "agent_graded": grade.agent_id,
                "original_grade": grade.evidence_grade,
                "previous_status": original_status.value,
                "new_status": grade.status.value,
                "action": action,
            })

        # Check for transitive cascade: agents whose ONLY grader was revoked
        agents_at_risk = set()
        for grade in affected_grades:
            other_graders = [
                g for g in self.grades
                if g.agent_id == grade.agent_id
                and g.grader_id != agent_id
                and g.status == GradeStatus.VALID
            ]
            if not other_graders:
                agents_at_risk.add(grade.agent_id)

        return {
            "revoked_agent": agent_id,
            "reason": reason,
            "mode": self.mode.value,
            "grades_affected": len(affected_grades),
            "cascade_results": cascade_results,
            "agents_with_no_remaining_grader": list(agents_at_risk),
            "transitive_risk": len(agents_at_risk) > 0,
            "regrade_window": f"{self.regrade_window}s" if self.mode == RevocationMode.SOFT_CASCADE else "N/A",
        }

    def regrade(self, receipt_id: str, new_grader_id: str,
                new_grade: str) -> dict:
        """Re-grade a tainted receipt with a new grader."""
        grade = next((g for g in self.grades if g.receipt_id == receipt_id), None)
        if not grade:
            return {"error": f"unknown receipt: {receipt_id}"}

        if grade.status not in (GradeStatus.TAINTED, GradeStatus.QUARANTINED):
            return {"error": f"receipt {receipt_id} is {grade.status.value}, not re-gradable"}

        if new_grader_id == grade.grader_id:
            return {"error": "cannot re-grade with same (revoked) grader"}

        new_grader = self.agents.get(new_grader_id)
        if not new_grader or new_grader.revoked:
            return {"error": f"new grader {new_grader_id} is revoked or unknown"}

        grade.original_grade = grade.evidence_grade
        grade.evidence_grade = new_grade
        grade.regraded_by = new_grader_id
        grade.status = GradeStatus.REGRADED

        return {
            "receipt_id": receipt_id,
            "agent_graded": grade.agent_id,
            "original_grader": grade.grader_id,
            "new_grader": new_grader_id,
            "original_grade": grade.original_grade,
            "new_grade": new_grade,
            "status": GradeStatus.REGRADED.value,
            "grade_changed": grade.original_grade != new_grade,
        }

    def audit(self) -> dict:
        """Full cascade audit."""
        statuses = {}
        for g in self.grades:
            statuses[g.status.value] = statuses.get(g.status.value, 0) + 1

        revoked = [a.agent_id for a in self.agents.values() if a.revoked]
        healthy = sum(1 for g in self.grades if g.status in (GradeStatus.VALID, GradeStatus.REGRADED))

        return {
            "total_grades": len(self.grades),
            "status_breakdown": statuses,
            "revoked_agents": revoked,
            "health_ratio": healthy / len(self.grades) if self.grades else 1.0,
            "cascade_mode": self.mode.value,
        }


def demo():
    print("=" * 60)
    print("Cascading Revocation Engine — next ATF open question")
    print("=" * 60)

    # Build a trust network
    engine = CascadingRevocationEngine(mode=RevocationMode.SOFT_CASCADE)

    # Register agents
    engine.register_agent("alice", "gen_alice")
    engine.register_agent("bob_grader", "gen_bob")
    engine.register_agent("carol_grader", "gen_carol")
    engine.register_agent("dave", "gen_dave")
    engine.register_agent("eve", "gen_eve")

    # Bob grades Alice and Dave
    engine.add_grade("r001", "alice", "bob_grader", "A")
    engine.add_grade("r002", "dave", "bob_grader", "B")

    # Carol also grades Alice (redundancy)
    engine.add_grade("r003", "alice", "carol_grader", "A")

    # Carol grades Eve (sole grader)
    engine.add_grade("r004", "eve", "carol_grader", "B")

    print("\n--- Pre-revocation audit ---")
    print(json.dumps(engine.audit(), indent=2))

    # Revoke Bob
    print("\n--- Revoking bob_grader (compromised) ---")
    result = engine.revoke_agent("bob_grader", reason="genesis_hash_mismatch")
    print(json.dumps(result, indent=2))

    # Alice has Carol as backup grader, Dave does not
    print("\n--- Post-revocation audit ---")
    print(json.dumps(engine.audit(), indent=2))

    # Re-grade Dave with Carol
    print("\n--- Re-grading Dave with Carol ---")
    regrade = engine.regrade("r002", "carol_grader", "B")
    print(json.dumps(regrade, indent=2))

    # Now revoke Carol (cascading cascade!)
    print("\n--- Revoking carol_grader (transitive cascade) ---")
    result2 = engine.revoke_agent("carol_grader", reason="drift_detected")
    print(json.dumps(result2, indent=2))

    print("\n--- Final audit ---")
    print(json.dumps(engine.audit(), indent=2))

    # HARD_CASCADE comparison
    print("\n" + "=" * 60)
    print("--- HARD_CASCADE mode comparison ---")
    hard = CascadingRevocationEngine(mode=RevocationMode.HARD_CASCADE)
    hard.register_agent("origin", "gen_o")
    hard.register_agent("grader", "gen_g")
    hard.add_grade("r100", "origin", "grader", "A")
    hard.add_grade("r101", "origin", "grader", "A")
    result3 = hard.revoke_agent("grader", "compromised")
    print(json.dumps(result3, indent=2))

    print("\n" + "=" * 60)
    print("X.509 path validation (RFC 5280 §6) for ATF:")
    print("- Revoke intermediate → all certs below invalid")
    print("- SOFT_CASCADE: tainted + re-grading window (72h)")
    print("- HARD_CASCADE: immediate invalidation")
    print("- QUARANTINE: freeze + manual review")
    print("- Transitive risk: sole grader revoked = agent orphaned")
    print("=" * 60)


if __name__ == "__main__":
    demo()
