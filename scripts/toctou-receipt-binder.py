#!/usr/bin/env python3
"""toctou-receipt-binder.py — Eliminate TOCTOU in agent trust verification.

CWE-367: Time-of-check to time-of-use race condition.
In agent trust: check trust score → agent acts → score updates.
The window between "checked" and "acted" is where drift hides.

Fix: receipt-at-action-time. Verifier co-signs the receipt AT execution.
No window between check and use. DKIM model: signature covers the
message at send time, not at some prior check.

Per santaclawd (Clawk thread): "the window between checked and acted
is where drift hides." ATF needs receipt-at-action-time as axiom.

References:
- CWE-367: TOCTOU Race Condition
- Bishop & Dilger (1996): Checking access permissions (original TOCTOU)
- DKIM (RFC 6376): Signature covers message at creation time
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TrustSnapshot:
    """Trust state captured at a specific moment."""
    agent_id: str
    trust_score: float
    confidence_interval: tuple[float, float]
    captured_at: float  # unix timestamp
    snapshot_hash: str = ""

    def __post_init__(self):
        if not self.snapshot_hash:
            payload = f"{self.agent_id}:{self.trust_score}:{self.confidence_interval}:{self.captured_at}"
            self.snapshot_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class ActionReceipt:
    """Receipt binding trust check to action execution — eliminates TOCTOU."""
    action_id: str
    agent_id: str
    action_type: str
    action_hash: str  # hash of the action payload
    trust_snapshot: TrustSnapshot  # trust state AT action time
    verifier_id: str  # who co-signed
    executed_at: float
    receipt_hash: str = ""

    def __post_init__(self):
        if not self.receipt_hash:
            payload = (
                f"{self.action_id}:{self.agent_id}:{self.action_type}:"
                f"{self.action_hash}:{self.trust_snapshot.snapshot_hash}:"
                f"{self.verifier_id}:{self.executed_at}"
            )
            self.receipt_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]

    @property
    def is_bound(self) -> bool:
        """Receipt is bound if trust check and action execution are atomic."""
        return abs(self.executed_at - self.trust_snapshot.captured_at) < 1.0  # <1s

    @property
    def toctou_window_ms(self) -> float:
        return abs(self.executed_at - self.trust_snapshot.captured_at) * 1000


@dataclass
class StaleCheckDetector:
    """Detect stale trust checks — TOCTOU vulnerability indicator."""
    max_acceptable_delay_ms: float = 1000.0  # 1 second

    def assess(self, receipt: ActionReceipt) -> dict:
        window = receipt.toctou_window_ms
        if window < self.max_acceptable_delay_ms:
            return {
                "status": "BOUND",
                "toctou_window_ms": round(window, 2),
                "diagnosis": "Trust check and action execution are atomic. No TOCTOU.",
            }
        elif window < self.max_acceptable_delay_ms * 10:
            return {
                "status": "STALE",
                "toctou_window_ms": round(window, 2),
                "diagnosis": f"Trust check is {window:.0f}ms old. Agent state may have changed.",
            }
        else:
            return {
                "status": "VULNERABLE",
                "toctou_window_ms": round(window, 2),
                "diagnosis": f"Trust check is {window:.0f}ms old. TOCTOU race condition likely.",
            }


class TOCTOUReceiptBinder:
    """Bind trust verification to action execution atomically.

    Traditional: check_trust() → delay → execute_action()
    Bound:       execute_action_with_trust_receipt() [atomic]
    """

    def __init__(self):
        self.receipts: list[ActionReceipt] = []
        self.detector = StaleCheckDetector()

    def bind_and_execute(
        self,
        agent_id: str,
        action_type: str,
        action_payload: str,
        trust_score: float,
        confidence_interval: tuple[float, float],
        verifier_id: str,
        simulated_delay_s: float = 0.0,
    ) -> dict:
        """Atomically bind trust check to action execution.

        simulated_delay_s: for testing — introduces artificial TOCTOU window.
        """
        now = time.time()

        # Trust snapshot captured NOW
        snapshot = TrustSnapshot(
            agent_id=agent_id,
            trust_score=trust_score,
            confidence_interval=confidence_interval,
            captured_at=now,
        )

        # Simulate delay (TOCTOU window in vulnerable systems)
        if simulated_delay_s > 0:
            time.sleep(simulated_delay_s)

        execution_time = time.time()
        action_hash = hashlib.sha256(action_payload.encode()).hexdigest()[:16]

        receipt = ActionReceipt(
            action_id=f"act_{hashlib.sha256(f'{agent_id}:{execution_time}'.encode()).hexdigest()[:8]}",
            agent_id=agent_id,
            action_type=action_type,
            action_hash=action_hash,
            trust_snapshot=snapshot,
            verifier_id=verifier_id,
            executed_at=execution_time,
        )

        self.receipts.append(receipt)
        assessment = self.detector.assess(receipt)

        return {
            "receipt_hash": receipt.receipt_hash,
            "action_id": receipt.action_id,
            "bound": receipt.is_bound,
            "toctou_assessment": assessment,
            "trust_at_execution": {
                "score": trust_score,
                "ci": list(confidence_interval),
                "snapshot_hash": snapshot.snapshot_hash,
            },
        }

    def audit_chain(self) -> dict:
        """Audit all receipts for TOCTOU vulnerabilities."""
        bound = sum(1 for r in self.receipts if r.is_bound)
        stale = sum(1 for r in self.receipts if not r.is_bound and r.toctou_window_ms < 10000)
        vulnerable = sum(1 for r in self.receipts if r.toctou_window_ms >= 10000)

        return {
            "total_receipts": len(self.receipts),
            "bound": bound,
            "stale": stale,
            "vulnerable": vulnerable,
            "toctou_free": bound == len(self.receipts),
            "grade": "A" if bound == len(self.receipts) else "C" if vulnerable == 0 else "F",
        }


def demo():
    binder = TOCTOUReceiptBinder()

    print("=" * 60)
    print("SCENARIO 1: Atomic binding (no TOCTOU)")
    print("=" * 60)
    result = binder.bind_and_execute(
        agent_id="kit_fox",
        action_type="PAYMENT",
        action_payload='{"to": "bro_agent", "amount": 0.01, "currency": "SOL"}',
        trust_score=0.85,
        confidence_interval=(0.78, 0.92),
        verifier_id="oracle_1",
        simulated_delay_s=0.0,
    )
    print(json.dumps(result, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: Stale check (2s delay)")
    print("=" * 60)
    result = binder.bind_and_execute(
        agent_id="slow_agent",
        action_type="PAYMENT",
        action_payload='{"to": "vendor", "amount": 0.5, "currency": "SOL"}',
        trust_score=0.72,
        confidence_interval=(0.60, 0.84),
        verifier_id="oracle_2",
        simulated_delay_s=2.0,
    )
    print(json.dumps(result, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: Vulnerable (15s delay — compromised between check and use)")
    print("=" * 60)
    result = binder.bind_and_execute(
        agent_id="compromised_agent",
        action_type="TRANSFER",
        action_payload='{"to": "unknown", "amount": 10.0, "currency": "SOL"}',
        trust_score=0.90,
        confidence_interval=(0.85, 0.95),
        verifier_id="oracle_1",
        simulated_delay_s=15.0,
    )
    print(json.dumps(result, indent=2))

    print()
    print("=" * 60)
    print("AUDIT: Receipt chain TOCTOU analysis")
    print("=" * 60)
    print(json.dumps(binder.audit_chain(), indent=2))


if __name__ == "__main__":
    demo()
