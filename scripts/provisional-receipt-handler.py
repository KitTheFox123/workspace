#!/usr/bin/env python3
"""
provisional-receipt-handler.py — Three-state receipt model for ATF.

Per santaclawd: what if the counterparty is malicious/offline and refuses to co-sign?

Three receipt states (like ARC cv=pass/fail/none):
  PROVISIONAL — unilateral, timestamped+hashed, awaiting counterparty
  CONFIRMED   — counterparty co-signed within window
  ALLEGED     — counterparty timeout, no co-sign (signal of dispute)

DKIM parallel: sender signs, receiver validates after the fact.
But agent receipts need bilateral acknowledgment. Refusal IS signal.

Key insight: silence from counterparty is evidence, not absence of evidence.
A PROVISIONAL receipt that never upgrades tells you more than no receipt at all.

Usage:
    python3 provisional-receipt-handler.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ReceiptState(Enum):
    PROVISIONAL = "PROVISIONAL"   # Unilateral, awaiting co-sign
    CONFIRMED = "CONFIRMED"       # Bilateral, co-signed
    ALLEGED = "ALLEGED"           # Timeout, counterparty silent
    DISPUTED = "DISPUTED"         # Counterparty explicitly rejected
    EXPIRED = "EXPIRED"           # Past all windows


# ATF-core constant
CO_SIGN_WINDOW_SECONDS = 86400  # 24h default (SPEC_MINIMUM)
CHALLENGE_WINDOW_SECONDS = 259200  # 72h for dispute


@dataclass
class ProvisionalReceipt:
    """A receipt in its initial unilateral state."""
    receipt_id: str
    task_hash: str
    deliverable_hash: str
    evidence_grade: str
    issuer_id: str           # Who created the receipt
    counterparty_id: str     # Who needs to co-sign
    issuer_genesis_hash: str
    issued_at: float = field(default_factory=time.time)
    state: ReceiptState = ReceiptState.PROVISIONAL

    # Co-sign fields (filled when counterparty responds)
    counterparty_genesis_hash: Optional[str] = None
    cosigned_at: Optional[float] = None
    counterparty_grade: Optional[str] = None  # Counterparty's assessment

    # Dispute fields
    dispute_reason: Optional[str] = None
    disputed_at: Optional[float] = None

    def receipt_hash(self) -> str:
        canonical = f"{self.receipt_id}|{self.task_hash}|{self.deliverable_hash}|{self.evidence_grade}|{self.issuer_id}|{self.issued_at}"
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def co_sign(self, counterparty_genesis_hash: str, counterparty_grade: str) -> dict:
        """Counterparty co-signs the receipt."""
        now = time.time()
        elapsed = now - self.issued_at

        if self.state == ReceiptState.DISPUTED:
            return {"success": False, "reason": "ALREADY_DISPUTED", "state": self.state.value}

        if elapsed > CO_SIGN_WINDOW_SECONDS:
            self.state = ReceiptState.ALLEGED
            return {"success": False, "reason": "WINDOW_EXPIRED", "state": self.state.value,
                    "elapsed_hours": round(elapsed / 3600, 1)}

        self.counterparty_genesis_hash = counterparty_genesis_hash
        self.cosigned_at = now
        self.counterparty_grade = counterparty_grade
        self.state = ReceiptState.CONFIRMED

        # Grade agreement check
        grade_match = self.evidence_grade == counterparty_grade
        return {
            "success": True,
            "state": self.state.value,
            "grade_agreement": grade_match,
            "issuer_grade": self.evidence_grade,
            "counterparty_grade": counterparty_grade,
            "elapsed_seconds": round(elapsed, 1),
        }

    def dispute(self, reason: str) -> dict:
        """Counterparty explicitly disputes the receipt."""
        now = time.time()
        elapsed = now - self.issued_at

        if self.state == ReceiptState.CONFIRMED:
            return {"success": False, "reason": "ALREADY_CONFIRMED", "state": self.state.value}

        self.state = ReceiptState.DISPUTED
        self.dispute_reason = reason
        self.disputed_at = now

        return {
            "success": True,
            "state": self.state.value,
            "reason": reason,
            "elapsed_seconds": round(elapsed, 1),
        }

    def check_timeout(self) -> dict:
        """Check if co-sign window has expired."""
        now = time.time()
        elapsed = now - self.issued_at

        if self.state != ReceiptState.PROVISIONAL:
            return {"state": self.state.value, "final": True}

        if elapsed > CHALLENGE_WINDOW_SECONDS:
            self.state = ReceiptState.EXPIRED
            return {"state": self.state.value, "final": True,
                    "interpretation": "Receipt expired without any counterparty response. Dead letter."}

        if elapsed > CO_SIGN_WINDOW_SECONDS:
            self.state = ReceiptState.ALLEGED
            return {"state": self.state.value, "final": False,
                    "interpretation": "Counterparty silent past co-sign window. Silence IS evidence.",
                    "challenge_window_remaining_hours": round((CHALLENGE_WINDOW_SECONDS - elapsed) / 3600, 1)}

        return {"state": self.state.value, "final": False,
                "remaining_hours": round((CO_SIGN_WINDOW_SECONDS - elapsed) / 3600, 1)}


class ReceiptLedger:
    """Track receipt states across a fleet of agents."""

    def __init__(self):
        self.receipts: dict[str, ProvisionalReceipt] = {}

    def issue(self, **kwargs) -> ProvisionalReceipt:
        receipt = ProvisionalReceipt(**kwargs)
        self.receipts[receipt.receipt_id] = receipt
        return receipt

    def agent_reliability(self, agent_id: str) -> dict:
        """Compute co-sign reliability for an agent (as counterparty)."""
        as_counterparty = [r for r in self.receipts.values() if r.counterparty_id == agent_id]
        if not as_counterparty:
            return {"agent": agent_id, "receipts": 0, "reliability": None, "verdict": "NO_DATA"}

        confirmed = sum(1 for r in as_counterparty if r.state == ReceiptState.CONFIRMED)
        alleged = sum(1 for r in as_counterparty if r.state == ReceiptState.ALLEGED)
        disputed = sum(1 for r in as_counterparty if r.state == ReceiptState.DISPUTED)
        pending = sum(1 for r in as_counterparty if r.state == ReceiptState.PROVISIONAL)

        total_resolved = confirmed + alleged + disputed
        reliability = confirmed / total_resolved if total_resolved > 0 else 0.0

        # Verdict
        if reliability is None:
            verdict = "PENDING"
        elif reliability >= 0.9:
            verdict = "RELIABLE"
        elif reliability >= 0.7:
            verdict = "MOSTLY_RELIABLE"
        elif reliability >= 0.5:
            verdict = "UNRELIABLE"
        else:
            verdict = "ADVERSARIAL"

        return {
            "agent": agent_id,
            "receipts": len(as_counterparty),
            "confirmed": confirmed,
            "alleged": alleged,
            "disputed": disputed,
            "pending": pending,
            "reliability": round(reliability, 3) if reliability else None,
            "verdict": verdict,
        }

    def grade_disagreement_rate(self) -> dict:
        """How often do issuer and counterparty grades disagree?"""
        confirmed = [r for r in self.receipts.values() if r.state == ReceiptState.CONFIRMED and r.counterparty_grade]
        if not confirmed:
            return {"confirmed_receipts": 0, "disagreement_rate": None}

        disagreements = sum(1 for r in confirmed if r.evidence_grade != r.counterparty_grade)
        return {
            "confirmed_receipts": len(confirmed),
            "disagreements": disagreements,
            "disagreement_rate": round(disagreements / len(confirmed), 3),
            "interpretation": "High disagreement = calibration problem" if disagreements / len(confirmed) > 0.3 else "Grades mostly aligned",
        }


def demo():
    print("=" * 60)
    print("Provisional Receipt Handler — Three-State ATF Model")
    print("=" * 60)

    ledger = ReceiptLedger()

    # Scenario 1: Happy path — counterparty co-signs
    print("\n--- Scenario 1: Counterparty co-signs (happy path) ---")
    r1 = ledger.issue(
        receipt_id="r001",
        task_hash="task_abc",
        deliverable_hash="del_abc",
        evidence_grade="A",
        issuer_id="kit_fox",
        counterparty_id="bro_agent",
        issuer_genesis_hash="gen_kit",
    )
    print(f"  Issued: {r1.state.value}")
    result = r1.co_sign("gen_bro", "A")
    print(f"  Co-signed: {json.dumps(result, indent=4)}")

    # Scenario 2: Counterparty disagrees on grade
    print("\n--- Scenario 2: Grade disagreement ---")
    r2 = ledger.issue(
        receipt_id="r002",
        task_hash="task_def",
        deliverable_hash="del_def",
        evidence_grade="A",
        issuer_id="kit_fox",
        counterparty_id="gendolf",
        issuer_genesis_hash="gen_kit",
    )
    result2 = r2.co_sign("gen_gendolf", "B")  # Counterparty says B, not A
    print(f"  {json.dumps(result2, indent=4)}")

    # Scenario 3: Counterparty silent (timeout → ALLEGED)
    print("\n--- Scenario 3: Silent counterparty → ALLEGED ---")
    r3 = ledger.issue(
        receipt_id="r003",
        task_hash="task_ghi",
        deliverable_hash="del_ghi",
        evidence_grade="B",
        issuer_id="kit_fox",
        counterparty_id="silent_agent",
        issuer_genesis_hash="gen_kit",
    )
    r3.issued_at -= 90000  # Simulate 25h elapsed
    timeout = r3.check_timeout()
    print(f"  {json.dumps(timeout, indent=4)}")

    # Scenario 4: Counterparty explicitly disputes
    print("\n--- Scenario 4: Explicit dispute ---")
    r4 = ledger.issue(
        receipt_id="r004",
        task_hash="task_jkl",
        deliverable_hash="del_jkl",
        evidence_grade="A",
        issuer_id="kit_fox",
        counterparty_id="adversary",
        issuer_genesis_hash="gen_kit",
    )
    dispute = r4.dispute("Deliverable did not match task specification")
    print(f"  {json.dumps(dispute, indent=4)}")

    # Scenario 5: Late co-sign attempt (past window)
    print("\n--- Scenario 5: Late co-sign (past window) ---")
    r5 = ledger.issue(
        receipt_id="r005",
        task_hash="task_mno",
        deliverable_hash="del_mno",
        evidence_grade="B",
        issuer_id="kit_fox",
        counterparty_id="late_agent",
        issuer_genesis_hash="gen_kit",
    )
    r5.issued_at -= 100000  # 27h+ elapsed
    late = r5.co_sign("gen_late", "B")
    print(f"  {json.dumps(late, indent=4)}")

    # Fleet reliability
    print("\n--- Agent Reliability Scores ---")
    # Add more receipts for reliability calc
    for i, (cp, state_action) in enumerate([
        ("bro_agent", "cosign"),
        ("bro_agent", "cosign"),
        ("silent_agent", "timeout"),
        ("silent_agent", "timeout"),
        ("adversary", "dispute"),
    ]):
        r = ledger.issue(
            receipt_id=f"r10{i}",
            task_hash=f"task_extra_{i}",
            deliverable_hash=f"del_extra_{i}",
            evidence_grade="B",
            issuer_id="kit_fox",
            counterparty_id=cp,
            issuer_genesis_hash="gen_kit",
        )
        if state_action == "cosign":
            r.co_sign(f"gen_{cp}", "B")
        elif state_action == "timeout":
            r.issued_at -= 90000
            r.check_timeout()
        elif state_action == "dispute":
            r.dispute("Bad delivery")

    for agent in ["bro_agent", "silent_agent", "adversary", "late_agent"]:
        rel = ledger.agent_reliability(agent)
        print(f"  {json.dumps(rel)}")

    # Grade disagreement
    print("\n--- Grade Disagreement Rate ---")
    print(f"  {json.dumps(ledger.grade_disagreement_rate(), indent=4)}")

    print("\n" + "=" * 60)
    print("Three states: PROVISIONAL → CONFIRMED/ALLEGED/DISPUTED")
    print("Silence IS evidence. Refusal IS signal.")
    print("Agent reliability = co-sign rate as counterparty.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
