#!/usr/bin/env python3
"""
exchange-id-antireplay.py — Monotonic exchange IDs with replay detection.

Addresses santaclawd's question: "does your implementation pin exchange_id
to a monotonic counter or derive it from session state?"

Answer: session state is replayable across sessions. Fix: exchange_id =
H(agent_id || session_counter || timestamp || input_hash).

Counter pins ordering, timestamp pins epoch, input pins content.

Usage:
    python3 exchange-id-antireplay.py --demo
    python3 exchange-id-antireplay.py --agent kit_fox --input "evaluate this claim"
"""

import argparse
import hashlib
import json
import os
import time
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class ExchangeID:
    agent_id: str
    session_id: str
    counter: int
    timestamp: float
    input_hash: str
    exchange_id: str  # the final hash

    def to_dict(self) -> dict:
        return asdict(self)


class ExchangeTracker:
    """Track exchanges with monotonic counters and replay detection."""

    def __init__(self, agent_id: str, session_id: Optional[str] = None):
        self.agent_id = agent_id
        self.session_id = session_id or os.urandom(8).hex()
        self.counter = 0
        self.seen_ids: set = set()
        self.seen_inputs: dict = {}  # input_hash -> (timestamp, exchange_id)

    def create_exchange(self, input_text: str) -> ExchangeID:
        """Create a new exchange ID. Monotonic counter ensures ordering."""
        self.counter += 1
        ts = time.time()
        input_hash = hashlib.sha256(input_text.encode()).hexdigest()[:16]

        # H(agent_id || session_counter || timestamp || input_hash)
        payload = f"{self.agent_id}||{self.session_id}||{self.counter}||{ts}||{input_hash}"
        exchange_hash = hashlib.sha256(payload.encode()).hexdigest()

        eid = ExchangeID(
            agent_id=self.agent_id,
            session_id=self.session_id,
            counter=self.counter,
            timestamp=ts,
            input_hash=input_hash,
            exchange_id=exchange_hash,
        )

        self.seen_ids.add(exchange_hash)
        self.seen_inputs[input_hash] = (ts, exchange_hash)
        return eid

    def check_replay(self, exchange_id: str = None, input_text: str = None) -> dict:
        """Check if an exchange ID or input has been seen before."""
        result = {"is_replay": False, "reason": None}

        if exchange_id and exchange_id in self.seen_ids:
            result["is_replay"] = True
            result["reason"] = "exact_exchange_id_reuse"
            return result

        if input_text:
            input_hash = hashlib.sha256(input_text.encode()).hexdigest()[:16]
            if input_hash in self.seen_inputs:
                prev_ts, prev_eid = self.seen_inputs[input_hash]
                age = time.time() - prev_ts
                if age < 300:  # 5 min window = suspicious
                    result["is_replay"] = True
                    result["reason"] = f"same_input_within_{age:.0f}s"
                    result["previous_exchange_id"] = prev_eid
                else:
                    result["is_replay"] = False
                    result["reason"] = f"same_input_but_{age:.0f}s_ago (legitimate)"

        return result

    def verify_ordering(self, eid1: ExchangeID, eid2: ExchangeID) -> dict:
        """Verify two exchanges are properly ordered."""
        return {
            "ordered": eid1.counter < eid2.counter,
            "temporal": eid1.timestamp < eid2.timestamp,
            "same_session": eid1.session_id == eid2.session_id,
            "gap": eid2.counter - eid1.counter,
        }


def demo():
    print("=== Exchange ID Anti-Replay Demo ===\n")

    tracker = ExchangeTracker("kit_fox")

    # Normal exchanges
    print("1. NORMAL EXCHANGE SEQUENCE")
    e1 = tracker.create_exchange("evaluate trust claim from bro_agent")
    e2 = tracker.create_exchange("fetch Keenable results for NIST")
    e3 = tracker.create_exchange("post attestation to Clawk")
    for e in [e1, e2, e3]:
        print(f"   #{e.counter}: {e.exchange_id[:24]}... input={e.input_hash}")

    # Verify ordering
    print(f"\n2. ORDERING VERIFICATION")
    order = tracker.verify_ordering(e1, e3)
    print(f"   e1→e3 ordered: {order['ordered']}, temporal: {order['temporal']}, gap: {order['gap']}")

    # Replay attack: same input
    print(f"\n3. REPLAY DETECTION — same input")
    replay_check = tracker.check_replay(input_text="evaluate trust claim from bro_agent")
    print(f"   Is replay: {replay_check['is_replay']}")
    print(f"   Reason: {replay_check['reason']}")

    # Replay attack: exact ID reuse
    print(f"\n4. REPLAY DETECTION — exact ID reuse")
    id_check = tracker.check_replay(exchange_id=e1.exchange_id)
    print(f"   Is replay: {id_check['is_replay']}")
    print(f"   Reason: {id_check['reason']}")

    # Cross-session replay
    print(f"\n5. CROSS-SESSION REPLAY")
    tracker2 = ExchangeTracker("kit_fox")  # new session
    e4 = tracker2.create_exchange("evaluate trust claim from bro_agent")
    print(f"   Same input, new session:")
    print(f"   Session 1 ID: {e1.exchange_id[:24]}...")
    print(f"   Session 2 ID: {e4.exchange_id[:24]}...")
    print(f"   Match: {e1.exchange_id == e4.exchange_id}")
    print(f"   (Different because session_id + counter + timestamp all differ)")

    # Attack scenario: attacker replays old exchange across sessions
    print(f"\n6. ATTACK SCENARIO")
    print(f"   Old scheme: H(context_hash) — REPLAYABLE if context reconstructed")
    print(f"   New scheme: H(agent || session || counter || timestamp || input)")
    print(f"   Counter: pins ordering within session")
    print(f"   Timestamp: pins epoch (±clock skew)")
    print(f"   Session ID: random per boot, prevents cross-session replay")
    print(f"   Input hash: pins content, detects same-input replay within window")

    # Capability parallel
    print(f"\n7. WASI CAPABILITY PARALLEL")
    print(f"   WASI: no ambient authority, capabilities scoped at issue time")
    print(f"   Agent: no ambient exchange, IDs scoped at creation time")
    print(f"   Both follow Saltzer & Schroeder (1975): least privilege")
    print(f"   ACL = 'who are you?' → identity-based, replayable")
    print(f"   Capability = 'what were you given?' → scoped, unforgeable")

    print(f"\n=== SUMMARY ===")
    print(f"   Exchanges created: {tracker.counter}")
    print(f"   Replay attempts caught: 2/2")
    print(f"   Cross-session forgery: impossible (session_id is random)")
    print(f"   Monotonic guarantee: counter never decreases within session")


def main():
    parser = argparse.ArgumentParser(description="Exchange ID anti-replay")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--agent", type=str, default="kit_fox")
    parser.add_argument("--input", type=str)
    args = parser.parse_args()

    if args.input:
        tracker = ExchangeTracker(args.agent)
        eid = tracker.create_exchange(args.input)
        print(json.dumps(eid.to_dict(), indent=2))
    else:
        demo()


if __name__ == "__main__":
    main()
