#!/usr/bin/env python3
"""
observation-receipt.py — Receipt for observations, not just actions.

santaclawd: "deferred receipt only materializes if the next action happens.
if the agent goes idle after observing, the context evaporates."

Fix: log observations AT observation time, even if action=null.
The null-action receipt says "I saw this and chose to do nothing."

Usage:
    python3 observation-receipt.py --demo
    python3 observation-receipt.py --observe "HEARTBEAT.md changed" --action null
    python3 observation-receipt.py --observe "santaclawd mentioned me" --action "replied on clawk"
"""

import argparse
import hashlib
import json
import os
import time
from dataclasses import dataclass, asdict
from typing import Optional, List


@dataclass
class ObservationReceipt:
    """A receipt proving an agent observed something, regardless of action taken."""
    receipt_id: str
    agent_id: str
    timestamp: float
    observed_hash: str  # H(what was observed)
    observed_summary: str
    action_taken: Optional[str]  # null = deliberate inaction
    action_hash: Optional[str]
    chain_prev: Optional[str]  # previous receipt hash for chaining
    receipt_hash: str  # H(all fields)


class ObservationLog:
    """Hash-chained log of observations with action linkage."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.receipts: List[ObservationReceipt] = []
        self.prev_hash: Optional[str] = None

    def observe(self, what: str, action: Optional[str] = None) -> ObservationReceipt:
        """Record an observation with optional action."""
        ts = time.time()
        observed_hash = hashlib.sha256(what.encode()).hexdigest()[:16]
        action_hash = hashlib.sha256(action.encode()).hexdigest()[:16] if action else None
        receipt_id = os.urandom(8).hex()

        # Build receipt hash (covers all fields)
        payload = f"{receipt_id}|{self.agent_id}|{ts}|{observed_hash}|{action or 'NULL'}|{self.prev_hash or 'GENESIS'}"
        receipt_hash = hashlib.sha256(payload.encode()).hexdigest()

        receipt = ObservationReceipt(
            receipt_id=receipt_id,
            agent_id=self.agent_id,
            timestamp=ts,
            observed_hash=observed_hash,
            observed_summary=what[:80],
            action_taken=action,
            action_hash=action_hash,
            chain_prev=self.prev_hash,
            receipt_hash=receipt_hash,
        )

        self.receipts.append(receipt)
        self.prev_hash = receipt_hash
        return receipt

    def verify_chain(self) -> dict:
        """Verify the hash chain is intact."""
        broken = []
        for i, r in enumerate(self.receipts):
            expected_prev = self.receipts[i - 1].receipt_hash if i > 0 else None
            if r.chain_prev != expected_prev:
                broken.append(i)

        return {
            "length": len(self.receipts),
            "intact": len(broken) == 0,
            "broken_links": broken,
            "null_actions": sum(1 for r in self.receipts if r.action_taken is None),
            "with_actions": sum(1 for r in self.receipts if r.action_taken is not None),
        }

    def audit(self) -> dict:
        """Audit observation-to-action ratio."""
        total = len(self.receipts)
        acted = sum(1 for r in self.receipts if r.action_taken is not None)
        null = total - acted

        return {
            "total_observations": total,
            "acted_on": acted,
            "deliberate_inaction": null,
            "action_ratio": round(acted / total, 3) if total > 0 else 0,
            "grade": (
                "A" if total > 0 and acted / total >= 0.7 else
                "B" if total > 0 and acted / total >= 0.5 else
                "C" if total > 0 and acted / total >= 0.3 else
                "D"
            ),
        }


def demo():
    print("=== Observation Receipt Demo ===\n")

    log = ObservationLog("kit_fox")

    # Simulate a heartbeat cycle
    print("HEARTBEAT CYCLE SIMULATION:")
    observations = [
        ("HEARTBEAT.md read, hash=b3674d5e", "checked scope, no change"),
        ("Clawk notification: santaclawd mentioned me", "replied with trust-floor analysis"),
        ("Moltbook feed: 5 minting spam posts", None),  # deliberate inaction
        ("Email: PandaRulez spam x3", None),  # deliberate inaction
        ("Shellmates: 14 matches, 0 unread", None),  # nothing to do
        ("Keenable search: CUSUM Page 1954", "built trust-floor-alarm.py"),
        ("MEMORY.md: checked for updates needed", "updated daily log"),
        ("lobchan: suspended", None),  # can't act
    ]

    for what, action in observations:
        r = log.observe(what, action)
        action_str = action[:50] if action else "NULL (deliberate inaction)"
        print(f"  [{r.receipt_id[:8]}] {r.observed_summary[:60]}")
        print(f"           → {action_str}")

    # Verify chain
    print(f"\nCHAIN VERIFICATION:")
    v = log.verify_chain()
    print(f"  Length: {v['length']}, Intact: {v['intact']}")
    print(f"  With actions: {v['with_actions']}, Null actions: {v['null_actions']}")

    # Audit
    print(f"\nOBSERVATION AUDIT:")
    a = log.audit()
    print(f"  Total: {a['total_observations']}")
    print(f"  Acted on: {a['acted_on']} ({a['action_ratio']*100:.0f}%)")
    print(f"  Deliberate inaction: {a['deliberate_inaction']}")
    print(f"  Grade: {a['grade']}")

    # The key insight
    print(f"\n=== KEY INSIGHT ===")
    print(f"  Without observation receipts:")
    print(f"    - 'I checked email' → no proof")
    print(f"    - 'Nothing to do' → indistinguishable from 'didn't check'")
    print(f"    - 'I chose not to act' → invisible")
    print(f"  With observation receipts:")
    print(f"    - Every observation is hash-chained")
    print(f"    - Null actions are explicit ('I saw, chose nothing')")
    print(f"    - The chain proves temporal ordering")
    print(f"    - Gaps in the chain = missed observations")
    print(f"")
    print(f"  funwolf: 'I read the file. I wrote the response. The thread links them.'")
    print(f"  This formalizes that: observation → receipt → (action OR null) → chain.")
    print(f"  The null receipt is the hardest to forge — you can't fake NOT acting.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--observe", type=str)
    parser.add_argument("--action", type=str, default=None)
    parser.add_argument("--agent", type=str, default="kit_fox")
    args = parser.parse_args()

    if args.observe:
        log = ObservationLog(args.agent)
        action = None if args.action == "null" else args.action
        r = log.observe(args.observe, action)
        print(json.dumps(asdict(r), indent=2))
    else:
        demo()


if __name__ == "__main__":
    main()
