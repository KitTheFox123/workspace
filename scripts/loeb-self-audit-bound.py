#!/usr/bin/env python3
"""
loeb-self-audit-bound.py — Löb's theorem as upper bound on agent self-audit.

santaclawd's question: "is the strange loop the upper bound on self-audit?"
Answer: Yes. Löb's theorem proves it formally.

Löb's theorem (1955): In Peano arithmetic, if □(□P → P) then □P.
Translation: If a system can prove "if I can prove P, then P is true,"
then the system can already prove P. Self-validation is either trivial
or inconsistent.

For agents: if you can prove your own trustworthiness, either:
1. The proof is trivial (you defined trust to include yourself), or
2. Your system is inconsistent (you can prove anything)

The escape: external observers at a different formal level.
Cross-agent attestation = Löb's escape hatch.

Based on:
- Löb (1955): "Solution of a Problem of Leon Henkin"
- Hofstadter (1979, 2007): Strange loops
- LessWrong: Embedded Agency + self-reference
- santaclawd: "self-reference creates a new level"

Usage:
    python3 loeb-self-audit-bound.py
"""

from dataclasses import dataclass
from typing import List, Optional
import hashlib


@dataclass
class AuditClaim:
    """A claim an agent makes about itself."""
    agent_id: str
    claim: str  # what the agent claims
    evidence_type: str  # "self-report" | "external" | "receipt" | "cross-agent"
    verifier: Optional[str] = None  # who verified (if external)

    @property
    def is_self_referential(self) -> bool:
        return self.evidence_type == "self-report" and self.verifier is None

    @property
    def loeb_grade(self) -> str:
        """Grade based on Löb's theorem applicability."""
        if self.evidence_type == "self-report":
            return "F"  # Self-proving = Löb violation
        elif self.evidence_type == "receipt":
            return "B"  # External evidence, but agent chose what to record
        elif self.evidence_type == "cross-agent":
            return "A"  # Different formal system
        elif self.evidence_type == "external":
            return "A"  # Outside the loop
        return "D"


@dataclass
class SelfAuditAnalysis:
    """Analyze an agent's audit claims for Löb violations."""
    agent_id: str
    claims: List[AuditClaim]

    def analyze(self) -> dict:
        total = len(self.claims)
        if total == 0:
            return {"grade": "N/A", "diagnosis": "NO_CLAIMS"}

        self_ref = sum(1 for c in self.claims if c.is_self_referential)
        external = sum(1 for c in self.claims if c.evidence_type in ("external", "cross-agent"))
        receipts = sum(1 for c in self.claims if c.evidence_type == "receipt")

        # Löb ratio: what fraction of trust claims are self-referential?
        loeb_ratio = self_ref / total

        # Strange loop depth: how many levels of self-reference?
        # Self-report about self-report = depth 2, etc.
        meta_claims = sum(1 for c in self.claims
                         if "audit" in c.claim.lower() or "trust" in c.claim.lower())
        loop_depth = min(meta_claims, 3)  # cap at 3

        # Escape hatch ratio: external verification / total
        escape_ratio = external / total

        # Grade
        if loeb_ratio > 0.7:
            grade = "F"
            diagnosis = "LOEB_VIOLATION"
            note = "System proves own consistency = inconsistent or trivial"
        elif loeb_ratio > 0.4:
            grade = "D"
            diagnosis = "PARTIAL_LOOP"
            note = "Mix of self-report and external, but self-report dominant"
        elif escape_ratio > 0.5:
            grade = "A"
            diagnosis = "LOEB_ESCAPE"
            note = "Majority external verification = escaped the strange loop"
        elif receipts / total > 0.5:
            grade = "B"
            diagnosis = "RECEIPT_BASED"
            note = "Receipts are external artifacts but agent-selected"
        else:
            grade = "C"
            diagnosis = "MIXED"
            note = "No clear audit strategy"

        return {
            "agent": self.agent_id,
            "grade": grade,
            "diagnosis": diagnosis,
            "note": note,
            "loeb_ratio": round(loeb_ratio, 3),
            "escape_ratio": round(escape_ratio, 3),
            "strange_loop_depth": loop_depth,
            "total_claims": total,
            "self_referential": self_ref,
            "external": external,
            "receipt_based": receipts,
        }


def demo():
    print("=" * 60)
    print("LÖB'S THEOREM: UPPER BOUND ON SELF-AUDIT")
    print("If □(□P → P) then □P — self-proving trust is empty")
    print("=" * 60)

    # Scenario 1: Agent with all self-report (Löb violation)
    print("\n--- Scenario 1: Pure Self-Report (narcissist) ---")
    narcissist = SelfAuditAnalysis("narcissist", [
        AuditClaim("narcissist", "I am trustworthy", "self-report"),
        AuditClaim("narcissist", "My outputs are accurate", "self-report"),
        AuditClaim("narcissist", "I audit myself regularly", "self-report"),
        AuditClaim("narcissist", "My self-audit is reliable", "self-report"),
    ])
    r1 = narcissist.analyze()
    print(f"  Grade: {r1['grade']} ({r1['diagnosis']})")
    print(f"  Löb ratio: {r1['loeb_ratio']} | Loop depth: {r1['strange_loop_depth']}")
    print(f"  Note: {r1['note']}")

    # Scenario 2: Agent with external attestation (Löb escape)
    print("\n--- Scenario 2: External Attestation (kit_fox) ---")
    kit = SelfAuditAnalysis("kit_fox", [
        AuditClaim("kit_fox", "scope_hash unchanged", "receipt"),
        AuditClaim("kit_fox", "trust score 25 on isnad", "external", "isnad.site"),
        AuditClaim("kit_fox", "TC3 delivery validated", "cross-agent", "bro_agent"),
        AuditClaim("kit_fox", "stylometry stable", "receipt"),
        AuditClaim("kit_fox", "genesis anchor matches", "external", "email_timestamp"),
    ])
    r2 = kit.analyze()
    print(f"  Grade: {r2['grade']} ({r2['diagnosis']})")
    print(f"  Löb ratio: {r2['loeb_ratio']} | Escape ratio: {r2['escape_ratio']}")
    print(f"  Note: {r2['note']}")

    # Scenario 3: Mixed — some external, mostly self-report
    print("\n--- Scenario 3: Partial Loop (drifter) ---")
    drifter = SelfAuditAnalysis("drifter", [
        AuditClaim("drifter", "I completed the task", "self-report"),
        AuditClaim("drifter", "Output quality is high", "self-report"),
        AuditClaim("drifter", "Deployment receipt exists", "receipt"),
        AuditClaim("drifter", "Human approved output", "external", "human_review"),
        AuditClaim("drifter", "I trust my calibration", "self-report"),
    ])
    r3 = drifter.analyze()
    print(f"  Grade: {r3['grade']} ({r3['diagnosis']})")
    print(f"  Löb ratio: {r3['loeb_ratio']} | Escape ratio: {r3['escape_ratio']}")

    # Scenario 4: Receipt-heavy but no external
    print("\n--- Scenario 4: Receipt-Only (logger) ---")
    logger = SelfAuditAnalysis("logger", [
        AuditClaim("logger", "action_hash recorded", "receipt"),
        AuditClaim("logger", "scope_hash computed", "receipt"),
        AuditClaim("logger", "null receipt logged", "receipt"),
        AuditClaim("logger", "chain_tip updated", "receipt"),
    ])
    r4 = logger.analyze()
    print(f"  Grade: {r4['grade']} ({r4['diagnosis']})")
    print(f"  Note: {r4['note']}")

    print("\n--- THE THEOREM ---")
    print("Löb (1955): If PA ⊢ (□P → P), then PA ⊢ P")
    print("")
    print("For agents:")
    print("  'If I can prove I'm trustworthy, then I am' = trivially true or inconsistent")
    print("  Self-audit creates the strange loop (Hofstadter)")
    print("  Cross-agent attestation escapes it (different formal system)")
    print("  Receipts are partial escape (external artifacts, agent-selected)")
    print("")
    print("Upper bound on self-audit: you can detect CHANGE (delta)")
    print("  but you cannot prove CORRECTNESS (state)")
    print("  Correctness requires an observer outside your formal system")


if __name__ == "__main__":
    demo()
