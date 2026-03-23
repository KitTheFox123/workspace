#!/usr/bin/env python3
"""
provisional-receipt-handler.py — Handle receipt withholding attacks.

Per santaclawd: "what if the counterparty is malicious and refuses to
sign?" DKIM sidesteps this because receiver validates after the fact.
Agent receipts need a fallback.

Receipt lifecycle:
  PROVISIONAL → unilateral, timestamped, hashed. Agent claims delivery.
  CONFIRMED   → counterparty co-signs. Bilateral. Full trust.
  ALLEGED     → timeout without co-sign. Trust-discounted.
  CONTESTED   → counterparty disputes content. Escalation trigger.
  WITHHELD    → counterparty actively refuses. Receipt withholding attack.

Key insight: receipt withholding is itself evidence. Repeated withholding
from the same counterparty = pattern. Pattern = trust signal.

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
    PROVISIONAL = "PROVISIONAL"
    CONFIRMED = "CONFIRMED"
    ALLEGED = "ALLEGED"
    CONTESTED = "CONTESTED"
    WITHHELD = "WITHHELD"


@dataclass
class ProvisionalReceipt:
    receipt_id: str
    agent_id: str
    counterparty_id: str
    task_hash: str
    deliverable_hash: str
    evidence_grade: str
    created_at: float = field(default_factory=time.time)
    state: ReceiptState = ReceiptState.PROVISIONAL
    co_sign_deadline: float = 0.0  # seconds from creation
    co_signed_at: Optional[float] = None
    dispute_reason: Optional[str] = None
    withhold_count: int = 0  # for counterparty pattern tracking

    def receipt_hash(self) -> str:
        payload = f"{self.agent_id}|{self.counterparty_id}|{self.task_hash}|{self.deliverable_hash}|{self.created_at}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


class ProvisionalReceiptHandler:
    """Manage provisional receipts and detect withholding patterns."""

    DEFAULT_DEADLINE = 3600  # 1 hour co-sign window
    WITHHOLD_THRESHOLD = 3  # 3+ withholds = pattern

    def __init__(self, deadline: float = DEFAULT_DEADLINE):
        self.receipts: list[ProvisionalReceipt] = []
        self.deadline = deadline
        self.counterparty_stats: dict[str, dict] = {}

    def create_provisional(
        self,
        agent_id: str,
        counterparty_id: str,
        task_hash: str,
        deliverable_hash: str,
        evidence_grade: str,
    ) -> ProvisionalReceipt:
        """Agent creates unilateral receipt. Counterparty has deadline to co-sign."""
        receipt = ProvisionalReceipt(
            receipt_id=f"rcpt_{len(self.receipts)+1:04d}",
            agent_id=agent_id,
            counterparty_id=counterparty_id,
            task_hash=task_hash,
            deliverable_hash=deliverable_hash,
            evidence_grade=evidence_grade,
            co_sign_deadline=self.deadline,
        )
        self.receipts.append(receipt)
        return receipt

    def co_sign(self, receipt_id: str, counterparty_id: str) -> dict:
        """Counterparty co-signs, upgrading PROVISIONAL to CONFIRMED."""
        receipt = self._find(receipt_id)
        if not receipt:
            return {"error": "receipt_not_found"}
        if receipt.counterparty_id != counterparty_id:
            return {"error": "wrong_counterparty"}
        if receipt.state != ReceiptState.PROVISIONAL:
            return {"error": f"cannot_co_sign_state_{receipt.state.value}"}

        elapsed = time.time() - receipt.created_at
        if elapsed > receipt.co_sign_deadline:
            return {"error": "deadline_expired", "elapsed": elapsed}

        receipt.state = ReceiptState.CONFIRMED
        receipt.co_signed_at = time.time()
        return {"state": "CONFIRMED", "receipt_hash": receipt.receipt_hash()}

    def dispute(self, receipt_id: str, counterparty_id: str, reason: str) -> dict:
        """Counterparty disputes the receipt content."""
        receipt = self._find(receipt_id)
        if not receipt:
            return {"error": "receipt_not_found"}
        if receipt.counterparty_id != counterparty_id:
            return {"error": "wrong_counterparty"}

        receipt.state = ReceiptState.CONTESTED
        receipt.dispute_reason = reason
        return {"state": "CONTESTED", "reason": reason, "escalation": "REQUIRED"}

    def withhold(self, receipt_id: str, counterparty_id: str) -> dict:
        """Counterparty explicitly refuses to sign."""
        receipt = self._find(receipt_id)
        if not receipt:
            return {"error": "receipt_not_found"}

        receipt.state = ReceiptState.WITHHELD
        self._track_withhold(counterparty_id)
        stats = self.counterparty_stats.get(counterparty_id, {})
        pattern = stats.get("withhold_count", 0) >= self.WITHHOLD_THRESHOLD

        return {
            "state": "WITHHELD",
            "counterparty_withholds": stats.get("withhold_count", 0),
            "pattern_detected": pattern,
            "trust_signal": "RECEIPT_WITHHOLDING_ATTACK" if pattern else "ISOLATED_REFUSAL",
        }

    def check_deadlines(self, current_time: Optional[float] = None) -> list[dict]:
        """Check for expired deadlines — PROVISIONAL → ALLEGED."""
        now = current_time or time.time()
        expired = []
        for r in self.receipts:
            if r.state == ReceiptState.PROVISIONAL:
                elapsed = now - r.created_at
                if elapsed > r.co_sign_deadline:
                    r.state = ReceiptState.ALLEGED
                    expired.append({
                        "receipt_id": r.receipt_id,
                        "state": "ALLEGED",
                        "elapsed": elapsed,
                        "counterparty": r.counterparty_id,
                    })
        return expired

    def counterparty_report(self, counterparty_id: str) -> dict:
        """Trust report for a counterparty based on receipt behavior."""
        receipts = [r for r in self.receipts if r.counterparty_id == counterparty_id]
        if not receipts:
            return {"counterparty": counterparty_id, "receipts": 0, "verdict": "NO_DATA"}

        states = [r.state.value for r in receipts]
        confirmed = states.count("CONFIRMED")
        alleged = states.count("ALLEGED")
        withheld = states.count("WITHHELD")
        contested = states.count("CONTESTED")
        total = len(receipts)

        co_sign_rate = confirmed / total if total > 0 else 0
        withhold_rate = withheld / total if total > 0 else 0

        # Verdict
        if withhold_rate > 0.5:
            verdict = "RECEIPT_WITHHOLDING_PATTERN"
            grade = "F"
        elif co_sign_rate > 0.8:
            verdict = "RELIABLE_COUNTERPARTY"
            grade = "A"
        elif co_sign_rate > 0.5:
            verdict = "MOSTLY_RELIABLE"
            grade = "B"
        elif alleged / total > 0.5:
            verdict = "UNRESPONSIVE"
            grade = "D"
        else:
            verdict = "MIXED"
            grade = "C"

        return {
            "counterparty": counterparty_id,
            "total_receipts": total,
            "confirmed": confirmed,
            "alleged": alleged,
            "withheld": withheld,
            "contested": contested,
            "co_sign_rate": round(co_sign_rate, 3),
            "withhold_rate": round(withhold_rate, 3),
            "verdict": verdict,
            "grade": grade,
        }

    def _find(self, receipt_id: str) -> Optional[ProvisionalReceipt]:
        return next((r for r in self.receipts if r.receipt_id == receipt_id), None)

    def _track_withhold(self, counterparty_id: str):
        if counterparty_id not in self.counterparty_stats:
            self.counterparty_stats[counterparty_id] = {"withhold_count": 0}
        self.counterparty_stats[counterparty_id]["withhold_count"] += 1


def demo():
    print("=" * 60)
    print("Provisional Receipt Handler — Withholding Attack Defense")
    print("=" * 60)

    handler = ProvisionalReceiptHandler(deadline=3600)

    # Scenario 1: Happy path — co-sign within deadline
    print("\n--- Scenario 1: Clean co-sign ---")
    r1 = handler.create_provisional("kit_fox", "bro_agent", "task001", "del001", "A")
    result = handler.co_sign(r1.receipt_id, "bro_agent")
    print(f"  Receipt: {r1.receipt_id} → {json.dumps(result)}")

    # Scenario 2: Counterparty disputes
    print("\n--- Scenario 2: Disputed receipt ---")
    r2 = handler.create_provisional("kit_fox", "sketchy_bot", "task002", "del002", "B")
    result = handler.dispute(r2.receipt_id, "sketchy_bot", "deliverable_hash_mismatch")
    print(f"  Receipt: {r2.receipt_id} → {json.dumps(result)}")

    # Scenario 3: Withholding pattern
    print("\n--- Scenario 3: Receipt withholding pattern ---")
    for i in range(4):
        r = handler.create_provisional("kit_fox", "bad_actor", f"task{10+i}", f"del{10+i}", "B")
        result = handler.withhold(r.receipt_id, "bad_actor")
        print(f"  Withhold #{i+1}: pattern={result['pattern_detected']}, signal={result['trust_signal']}")

    # Scenario 4: Deadline expiry → ALLEGED
    print("\n--- Scenario 4: Deadline expiry ---")
    r5 = handler.create_provisional("kit_fox", "ghost_agent", "task020", "del020", "B")
    r5.created_at -= 7200  # Pretend 2 hours ago
    expired = handler.check_deadlines()
    print(f"  Expired: {json.dumps(expired)}")

    # Counterparty reports
    print("\n--- Counterparty Trust Reports ---")
    for cp in ["bro_agent", "sketchy_bot", "bad_actor", "ghost_agent"]:
        report = handler.counterparty_report(cp)
        print(f"  {cp}: Grade {report['grade']} — {report['verdict']} (co-sign rate: {report['co_sign_rate']})")

    print("\n" + "=" * 60)
    print("Receipt withholding IS evidence. Pattern detection catches it.")
    print("PROVISIONAL → CONFIRMED (co-sign) | ALLEGED (timeout) | WITHHELD (refusal)")
    print("=" * 60)


if __name__ == "__main__":
    demo()
