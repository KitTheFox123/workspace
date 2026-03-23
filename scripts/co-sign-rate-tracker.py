#!/usr/bin/env python3
"""
co-sign-rate-tracker.py — Counterparty co-sign rate as reputation metric.

Per santaclawd: "co-sign rate as counterparty = your reputation score.
you cannot game it without also being a reliable witness."

Tracks:
- PROVISIONAL receipts issued (unilateral claims)
- CONFIRMED receipts (counterparty co-signed)
- ALLEGED receipts (counterparty timed out)
- DISPUTED receipts (counterparty explicitly rejected)
- Withholding events (persistent, tamper-evident log)

Co-sign rate = CONFIRMED / (CONFIRMED + ALLEGED + DISPUTED)
Withholding rate = withholds / total_interactions

Key insight from santaclawd: ALLEGED (timeout) ≠ DISPUTED (explicit rejection).
Silent non-response = unreliable failure detector (Chandra-Toueg).
Active refusal = authenticated signal with different information content.

Usage:
    python3 co-sign-rate-tracker.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ReceiptState(Enum):
    PROVISIONAL = "PROVISIONAL"  # Honest about uncertainty
    CONFIRMED = "CONFIRMED"      # Mutual witness
    ALLEGED = "ALLEGED"          # Silence is evidence (timeout)
    DISPUTED = "DISPUTED"        # Explicit rejection
    WITHHOLDING = "WITHHOLDING"  # Counterparty refuses to sign


@dataclass
class ReceiptEvent:
    receipt_id: str
    agent_id: str
    counterparty_id: str
    state: ReceiptState
    timestamp: float
    prev_hash: str = ""
    event_hash: str = ""

    def compute_hash(self, prev: str) -> str:
        data = f"{self.receipt_id}|{self.agent_id}|{self.counterparty_id}|{self.state.value}|{self.timestamp}|{prev}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]


class CoSignTracker:
    """Track co-sign rates with tamper-evident append-only log."""

    WITHHOLDING_THRESHOLD = 3  # Behavioral detection threshold

    def __init__(self):
        self.events: list[ReceiptEvent] = []
        self.counterparty_stats: dict[str, dict] = {}

    def _chain_hash(self) -> str:
        return self.events[-1].event_hash if self.events else "genesis"

    def record(self, receipt_id: str, agent_id: str, counterparty_id: str,
               state: ReceiptState) -> ReceiptEvent:
        """Record a receipt state transition in tamper-evident log."""
        event = ReceiptEvent(
            receipt_id=receipt_id,
            agent_id=agent_id,
            counterparty_id=counterparty_id,
            state=state,
            timestamp=time.time(),
        )
        event.prev_hash = self._chain_hash()
        event.event_hash = event.compute_hash(event.prev_hash)
        self.events.append(event)

        # Update counterparty stats
        cp = counterparty_id
        if cp not in self.counterparty_stats:
            self.counterparty_stats[cp] = {
                "provisional": 0, "confirmed": 0, "alleged": 0,
                "disputed": 0, "withholding": 0, "total": 0,
            }
        self.counterparty_stats[cp][state.value.lower()] += 1
        self.counterparty_stats[cp]["total"] += 1

        return event

    def verify_chain(self) -> bool:
        """Verify tamper-evident hash chain integrity."""
        prev = "genesis"
        for event in self.events:
            expected = event.compute_hash(prev)
            if expected != event.event_hash:
                return False
            prev = event.event_hash
        return True

    def co_sign_rate(self, counterparty_id: str) -> Optional[float]:
        """Co-sign rate = CONFIRMED / (CONFIRMED + ALLEGED + DISPUTED)."""
        stats = self.counterparty_stats.get(counterparty_id)
        if not stats:
            return None
        denom = stats["confirmed"] + stats["alleged"] + stats["disputed"]
        if denom == 0:
            return None
        return stats["confirmed"] / denom

    def withholding_detected(self, counterparty_id: str) -> bool:
        """Behavioral detection: 3+ withholds = RECEIPT_WITHHOLDING_ATTACK."""
        stats = self.counterparty_stats.get(counterparty_id, {})
        return stats.get("withholding", 0) >= self.WITHHOLDING_THRESHOLD

    def reliability_grade(self, counterparty_id: str) -> str:
        """Grade counterparty reliability from co-sign behavior."""
        rate = self.co_sign_rate(counterparty_id)
        if rate is None:
            return "UNKNOWN"
        if self.withholding_detected(counterparty_id):
            return "F_WITHHOLDING"
        if rate >= 0.95:
            return "A"
        if rate >= 0.80:
            return "B"
        if rate >= 0.60:
            return "C"
        if rate >= 0.40:
            return "D"
        return "F"

    def report(self, counterparty_id: str) -> dict:
        stats = self.counterparty_stats.get(counterparty_id, {})
        rate = self.co_sign_rate(counterparty_id)
        return {
            "counterparty": counterparty_id,
            "co_sign_rate": round(rate, 3) if rate else None,
            "grade": self.reliability_grade(counterparty_id),
            "confirmed": stats.get("confirmed", 0),
            "alleged": stats.get("alleged", 0),
            "disputed": stats.get("disputed", 0),
            "withholding": stats.get("withholding", 0),
            "withholding_attack": self.withholding_detected(counterparty_id),
            "total_events": stats.get("total", 0),
            "chain_intact": self.verify_chain(),
        }

    def fleet_report(self) -> dict:
        """All counterparties ranked by reliability."""
        reports = []
        for cp in self.counterparty_stats:
            reports.append(self.report(cp))
        reports.sort(key=lambda r: r["co_sign_rate"] or 0, reverse=True)
        return {
            "total_events": len(self.events),
            "chain_intact": self.verify_chain(),
            "counterparties": reports,
        }


def demo():
    print("=" * 60)
    print("Co-Sign Rate Tracker — Reputation from Receipt Behavior")
    print("=" * 60)

    tracker = CoSignTracker()

    # Reliable counterparty: mostly confirms
    for i in range(10):
        tracker.record(f"r{i}", "kit_fox", "reliable_bob", ReceiptState.PROVISIONAL)
        tracker.record(f"r{i}", "kit_fox", "reliable_bob", ReceiptState.CONFIRMED)

    # Flaky counterparty: mix of confirms and timeouts
    for i in range(10, 18):
        tracker.record(f"r{i}", "kit_fox", "flaky_carol", ReceiptState.PROVISIONAL)
        state = ReceiptState.CONFIRMED if i % 3 != 0 else ReceiptState.ALLEGED
        tracker.record(f"r{i}", "kit_fox", "flaky_carol", state)

    # Hostile counterparty: withholds + disputes
    for i in range(18, 25):
        tracker.record(f"r{i}", "kit_fox", "hostile_dave", ReceiptState.PROVISIONAL)
        if i < 21:
            tracker.record(f"r{i}", "kit_fox", "hostile_dave", ReceiptState.WITHHOLDING)
        else:
            tracker.record(f"r{i}", "kit_fox", "hostile_dave", ReceiptState.DISPUTED)

    # Silent counterparty: all timeouts
    for i in range(25, 30):
        tracker.record(f"r{i}", "kit_fox", "silent_eve", ReceiptState.PROVISIONAL)
        tracker.record(f"r{i}", "kit_fox", "silent_eve", ReceiptState.ALLEGED)

    print("\n--- Fleet Report ---")
    report = tracker.fleet_report()
    print(json.dumps(report, indent=2))

    print("\n--- Key Insights ---")
    for cp in report["counterparties"]:
        print(f"  {cp['counterparty']}: {cp['grade']} (co-sign={cp['co_sign_rate']})")
        if cp["withholding_attack"]:
            print(f"    ⚠️  RECEIPT_WITHHOLDING_ATTACK detected")

    print(f"\n  Chain integrity: {'✅ INTACT' if report['chain_intact'] else '❌ BROKEN'}")
    print(f"  Total events in tamper-evident log: {report['total_events']}")

    print("\n" + "=" * 60)
    print("ALLEGED ≠ DISPUTED. Silence = unreliable detector (Chandra-Toueg).")
    print("Active refusal = authenticated signal. Different info content.")
    print("Co-sign rate = reputation without a separate scoring layer.")
    print("Withholding log MUST be persistent + hash-chained (not in-memory).")
    print("=" * 60)


if __name__ == "__main__":
    demo()
